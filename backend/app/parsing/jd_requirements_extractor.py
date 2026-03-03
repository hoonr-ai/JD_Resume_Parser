"""
jd_requirements_extractor.py
────────────────────────────
Phase 1 of the JD-Resume Matching Pipeline.

Prompts the LLM to extract a highly structured schema from a raw JD `.TOON` file.
Converts the LLM's JSON response into the Phase 1 `.TOON` output schema:

TOON FORMAT EXPECTED:
JD_SKILL_REQUIREMENT
    JD_ID: <string>
    REQUIRED_SKILLS:
        - SKILL_ID: <string>
          CANONICAL_NAME: <string>
          MINIMUM_YEARS: <float>
          REQUIRED_PROFICIENCY_LEVEL: <1-5>
          MANDATORY: <boolean>
          WEIGHT: <float>
    OPTIONAL_SKILLS:
        - <string>
        ...
    CATEGORY_DISTRIBUTION:
        <category>: <percentage>
        ...
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
# Initialize the OpenAI client (requires OPENAI_API_KEY in environment)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

JD_EXTRACTION_PROMPT = """
You are a Senior Technical Recruiter and Expert Ontologist.

You will be given a Job Description formatted as a TOON file.
Your task is to extract the exact skill requirements, domains, and seniority levels, outputting them as a JSON object matching the exact schema below.

RETURN ONLY VALID JSON. Do not return markdown blocks or any other text.

JSON SCHEMA EXPECTED:
{
    "jd_id": "string (the Job ID)",
    "required_domains": [
        "string (industry or domain, e.g., 'FinTech', 'SaaS', 'Healthcare')"
    ],
    "seniority_level": "string (e.g., 'Junior', 'Mid-Level', 'Senior Engineer', 'Lead', 'Manager')",
    "required_skills": [
        {
            "skill_id": "string (snake_case representation of the skill)",
            "canonical_name": "string (normalized name, e.g., 'Python', 'AWS')",
            "minimum_years": float (0.0 if not specified),
            "required_proficiency_level": int (1=Beginner, 2=Intermediate, 3=Advanced, 4=Expert, 5=Master),
            "mandatory": boolean (true if strictly required, false if preferred/nice-to-have),
            "weight": float (1.0 to 10.0 based on importance to the role)
        }
    ],
    "optional_skills": [
        "string (skill names that are nice-to-have)"
    ],
    "category_distribution": {
        "string (Name of the category, e.g. Backend)": "integer (percentage weighting, e.g. 50)",
        "string (Name of the category, e.g. DevOps)": "integer (percentage weighting, e.g. 30)"
        // Categories must be dynamically generated based on the JD. 
        // Distribution of skill categories should add up to exactly 100.
    }
}
"""

from app.parsing.token_logger import telemetry

def extract_jd_requirements(jd_toon_content: str, jd_id: str) -> str:
    """
    Passes the JD TOON data to the LLM to extract the targeted JSON schema, 
    and returns the constructed JD_SKILL_REQUIREMENT TOON payload.
    """
    user_prompt = f"JD ID: {jd_id}\n\n{jd_toon_content}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": JD_EXTRACTION_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0
    )
    
    text = response.choices[0].message.content.strip()
    telemetry.log(response.usage, JD_EXTRACTION_PROMPT + user_prompt, text)
    
    # Clean possible markdown formatting
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
        # Return fallback TOON
        return f"JD_SKILL_REQUIREMENT\n    JD_ID: {jd_id}\n    ERROR: JSON Decode Failed\n"
    
    # Format as TOON
    out = []
    out.append("JD_SKILL_REQUIREMENT")
    out.append(f"    JD_ID: {jd_id}")
    
    # New Meta Data
    seniority = data.get("seniority_level", "Not Specified")
    out.append(f"    SENIORITY_LEVEL: {seniority}")
    
    domains = data.get("required_domains", [])
    if domains:
        out.append("    REQUIRED_DOMAINS:")
        for d in domains:
            out.append(f"        - {d}")
    else:
        out.append("    REQUIRED_DOMAINS: NONE")
    
    # Required Skills
    req_skills = data.get("required_skills", [])
    if req_skills:
        out.append("    REQUIRED_SKILLS:")
        for skill in req_skills:
            out.append(f"        - SKILL_ID: {skill.get('skill_id', '')}")
            out.append(f"          CANONICAL_NAME: {skill.get('canonical_name', '')}")
            out.append(f"          MINIMUM_YEARS: {skill.get('minimum_years', 0.0)}")
            out.append(f"          REQUIRED_PROFICIENCY_LEVEL: {skill.get('required_proficiency_level', 1)}")
            out.append(f"          MANDATORY: {skill.get('mandatory', True)}")
            out.append(f"          WEIGHT: {skill.get('weight', 1.0)}")
    else:
        out.append("    REQUIRED_SKILLS: NONE")
        
    # Optional Skills
    opt_skills = data.get("optional_skills", [])
    if opt_skills:
        out.append("    OPTIONAL_SKILLS:")
        for os_skill in opt_skills:
            out.append(f"        - {os_skill}")
    else:
        out.append("    OPTIONAL_SKILLS: NONE")
        
    # Category Distribution
    cat_dist = data.get("category_distribution", {})
    if cat_dist:
        out.append("    CATEGORY_DISTRIBUTION:")
        for cat, weight in cat_dist.items():
            out.append(f"        {cat}: {weight}")
    else:
        out.append("    CATEGORY_DISTRIBUTION: NONE")
        
    return "\n".join(out)
