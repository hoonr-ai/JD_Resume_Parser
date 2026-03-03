"""
candidate_profile_builder.py
────────────────────────────
Phase 2 of the JD-Resume Matching Pipeline.

Uses a hybrid approach:
1. Prompts the LLM to extract qualitative metrics for every skill found in the Resume TOON file.
2. Uses pure Python `math` module to mathematically calculate:
   recency_weight = math.exp(-0.2 * (current_year - last_used_year))
   composite_skill_score = ((years_total * 0.25) + (years_recent_3 * 0.25) + (proficiency_score * 0.2) + (impact_weight * 0.15) + (seniority_weight * 0.15)) * recency_weight

Then formats output into a final CANDIDATE_SKILL_PROFILE TOON schema.
"""

import os
import json
import math
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CANDIDATE_EXTRACTION_PROMPT = """
You are a Senior Technical Recruiter and Expert Ontologist.

You will be given a Resume formatted as a TOON file.
Extract EVERY skill mentioned or implied in the resume, as well as qualitative metrics about the candidate's career trajectory.

RETURN ONLY VALID JSON matching this exact schema:

{
    "candidate_name": "string (the person's name)",
    "inferred_seniority": "string (e.g., 'Senior Engineer', 'Mid-Level', 'Lead')",
    "candidate_domains": ["string (e.g., 'FinTech', 'Healthcare', 'SaaS')"],
    "currently_employed": boolean (true if their most recent job does not have an end date or ends in the current year/Present),
    "average_tenure_months": int (average number of months spent at each company),
    "job_hop_risk_flag": boolean (true if average tenure < 18 months),
    "career_gap_risk_flag": boolean (true if there are significant unexplained gaps > 6 months between roles),
    "skills": [
        {
            "canonical_name": "string (normalized name, e.g., 'Python', 'AWS')",
            "years_total": float (0.0 if not specified),
            "years_recent_3": float (how many of the last 3 years did they use it? maximum 3.0),
            "last_used_date": "YYYY" (the string year they last used this skill, e.g. "2026"),
            "proficiency_score": int (1=Beginner, 2=Intermediate, 3=Advanced, 4=Expert, 5=Master),
            "frequency_score": float (1.0 to 5.0 based on how often they used it),
            "impact_weight": int (1=Low impact to 5=Critical business impact),
            "seniority_weight": int (1=Junior/Execution to 5=Architect/Leadership)
        }
    ]
}
"""

def build_candidate_profile(resume_toon_content: str, candidate_id: str) -> str:
    """
    Extracts the qualitative metrics via LLM, strictly performs deterministic 
    exponential decay and composite scoring in Python, and saves the TOON result.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CANDIDATE_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Candidate ID: {candidate_id}\n\n{resume_toon_content}"}
        ],
        temperature=0.0
    )
    
    text = response.choices[0].message.content.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except Exception as e:
        print(f"Failed to decode LLM JSON: {e}")
        return f"CANDIDATE_SKILL_PROFILE\n    CANDIDATE_ID: {candidate_id}\n    ERROR: JSON Decode Failed\n"
    
    current_year = datetime.now().year
    candidate_name = data.get("candidate_name", "Unknown")
    skills = data.get("skills", [])
    
    out = []
    out.append("CANDIDATE_SKILL_PROFILE")
    out.append(f"    CANDIDATE_ID: {candidate_id}")
    out.append(f"    CANDIDATE_NAME: {candidate_name}")
    
    # New Meta Data
    out.append(f"    INFERRED_SENIORITY: {data.get('inferred_seniority', 'Unknown')}")
    out.append(f"    CURRENTLY_EMPLOYED: {data.get('currently_employed', False)}")
    out.append(f"    AVERAGE_TENURE_MONTHS: {data.get('average_tenure_months', 0)}")
    out.append(f"    JOB_HOP_RISK_FLAG: {data.get('job_hop_risk_flag', False)}")
    out.append(f"    CAREER_GAP_RISK_FLAG: {data.get('career_gap_risk_flag', False)}")
    
    domains = data.get("candidate_domains", [])
    if domains:
        out.append("    CANDIDATE_DOMAINS:")
        for d in domains:
            out.append(f"        - {d}")
    else:
        out.append("    CANDIDATE_DOMAINS: NONE")
    
    if not skills:
        out.append("    SKILLS: NONE")
        return "\n".join(out)
        
    out.append("    SKILLS:")
    
    for skill in skills:
        canonical_name = skill.get('canonical_name', 'Unknown')
        years_total = float(skill.get('years_total', 0.0))
        years_recent_3 = float(skill.get('years_recent_3', 0.0))
        proficiency_score = float(skill.get('proficiency_score', 1.0))
        frequency_score = float(skill.get('frequency_score', 1.0))
        impact_weight = float(skill.get('impact_weight', 1.0))
        seniority_weight = float(skill.get('seniority_weight', 1.0))
        
        # Parse last used year safely
        last_used_str = str(skill.get('last_used_date', ''))
        last_used_year = current_year
        if len(last_used_str) == 4 and last_used_str.isdigit():
            last_used_year = int(last_used_str)
        elif len(last_used_str) > 4:
            # If they provided something like 'Feb 2026' or '2026-02'
            # Just extract the first 4 consecutive digits
            import re
            match = re.search(r'\d{4}', last_used_str)
            if match:
                last_used_year = int(match.group(0))

        # --- PYTHON MATHEMATICAL SCORING (NO LLM MATH) ---
        # 1. Recency Weight = math.exp(-0.2 * (current_year - last_used_year))
        diff_years = max(0, current_year - last_used_year)  # Prevent negative if future
        recency_weight = math.exp(-0.2 * diff_years)
        
        # 2. Composite Score = ((yt*0.25) + (yr3*0.25) + (ps*0.2) + (iw*0.15) + (sw*0.15)) * rw
        base_score = (
            (years_total * 0.25) +
            (years_recent_3 * 0.25) +
            (proficiency_score * 0.2) +
            (impact_weight * 0.15) +
            (seniority_weight * 0.15)
        )
        composite_skill_score = base_score * recency_weight
        
        # Output TOON payload
        out.append(f"        - CANONICAL_NAME: {canonical_name}")
        out.append(f"          YEARS_TOTAL: {years_total:.2f}")
        out.append(f"          YEARS_RECENT_3: {years_recent_3:.2f}")
        out.append(f"          LAST_USED: {last_used_year}")
        out.append(f"          PROFICIENCY_SCORE: {proficiency_score:.1f}")
        out.append(f"          FREQUENCY_SCORE: {frequency_score:.1f}")
        out.append(f"          IMPACT_WEIGHT: {impact_weight:.1f}")
        out.append(f"          SENIORITY_WEIGHT: {seniority_weight:.1f}")
        out.append(f"          RECENCY_WEIGHT: {recency_weight:.4f}")
        out.append(f"          COMPOSITE_SCORE: {composite_skill_score:.4f}")

    return "\n".join(out)
