"""
matching_engine.py
──────────────────
Phase 3 of the JD-Resume Matching Pipeline.

Feeds the structured JD_SKILL_REQUIREMENT and CANDIDATE_SKILL_PROFILE
into the LLM, prompting it to act as a Senior Technical Recruiter.
The LLM evaluates the mathematical overlap (Composite Candidate Scores
vs. JD Required Weights) and outputs a final Match Results TOON format.
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from app.parsing.token_logger import telemetry

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MATCHING_PROMPT = """
You are an Elite Senior Technical Recruiter and Data Analyst.

You will be provided with two highly structured, mathematically scored profiles:
1. The Job Description Skill Requirements (Target)
2. The Candidate Skill Profile (Scored Candidate)

Your objective is to deeply analyze the mathematical overlap between the Candidate's composite scores, career trajectory metrics, and the JD's requirements.

RETURN ONLY VALID JSON matching this exact 1.0 schema structure:

{
  "match_result": {
    "schema_version": "1.0",
    "overall_match_score": float (0.0 to 100.0),
    "match_band": "string ('Excellent', 'Good', 'Average', 'Poor')",
    "decision_recommendation": "string ('Interview', 'Screen', 'Reject')",
    "confidence_score": float (0.0 to 1.0)
  },
  "score_breakdown": {
    "skill_match_score": float,
    "category_fit_score": float,
    "seniority_alignment_score": float,
    "domain_alignment_score": float,
    "recency_score": float
  },
  "skill_match_analysis": {
    "mandatory_skills": [
      {
        "skill_name": "string",
        "jd_required_years": float,
        "candidate_years": float,
        "jd_required_proficiency": int,
        "candidate_proficiency": int,
        "match_score": float (0.0 to 1.0),
        "gap_flag": boolean
      }
    ],
    "optional_skills": [
      {
        "skill_name": "string",
        "match_score": float
      }
    ],
    "missing_skills": [
      {
        "skill_name": "string",
        "importance_weight": float
      }
    ],
    "adjacent_skills_detected": [
      {
        "required_skill": "string",
        "candidate_adjacent_skill": "string",
        "semantic_similarity_score": float
      }
    ]
  },
  "category_fit": {
    "backend_fit_score": float,
    "frontend_fit_score": float,
    "cloud_fit_score": float,
    "database_fit_score": float,
    "devops_fit_score": float,
    "overall_category_alignment": float
  },
  "seniority_alignment": {
    "jd_seniority_level": "string",
    "candidate_inferred_seniority": "string",
    "alignment_score": float
  },
  "experience_risk_analysis": {
    "currently_employed": boolean,
    "recency_score": float,
    "average_tenure_months": int,
    "job_hop_risk_flag": boolean,
    "career_gap_risk_flag": boolean
  },
  "domain_alignment": {
    "jd_required_domains": ["string"],
    "candidate_domains": ["string"],
    "domain_overlap_score": float
  },
  "skill_gap_analysis": {
    "critical_gaps": [{"skill_name": "string", "gap_severity_score": float}],
    "moderate_gaps": [{"skill_name": "string", "gap_severity_score": float}],
    "minor_gaps": []
  },
  "interview_focus_recommendations": [
    {"area": "string", "reason": "string", "priority": "High|Medium|Low"}
  ],
  "explainability": {
    "top_positive_factors": ["string"],
    "top_negative_factors": ["string"],
    "mandatory_skill_penalty_applied": boolean,
    "score_contribution_breakdown": {
      "skills": float,
      "seniority": float,
      "domain": float,
      "recency": float,
      "category_alignment": float,
      "stability": float
    }
  },
  "audit_trail": {
    "matching_algorithm": "hybrid_weighted_semantic_v3",
    "embedding_model_version": "domain-tuned-slm-v2",
    "skill_taxonomy_version": "internal_taxonomy_v5.1",
    "decay_lambda": 0.2,
    "mandatory_threshold": 0.7
  }
}
"""

def dict_to_toon(data, indent_level=0) -> list:
    """Recursively converts a JSON dictionary to a custom TOON string line-by-line format."""
    lines = []
    base_indent = "    " * indent_level
    if isinstance(data, dict):
        for k, v in data.items():
            k_upper = str(k).upper()
            if isinstance(v, dict):
                lines.append(f"{base_indent}{k_upper}:")
                lines.extend(dict_to_toon(v, indent_level + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{base_indent}{k_upper}: NONE")
                else:
                    lines.append(f"{base_indent}{k_upper}:")
                    for item in v:
                        if isinstance(item, dict):
                            first = True
                            for ik, iv in item.items():
                                ik_upper = str(ik).upper()
                                if first:
                                    lines.append(f"{base_indent}    - {ik_upper}: {iv}")
                                    first = False
                                else:
                                    lines.append(f"{base_indent}      {ik_upper}: {iv}")
                        else:
                            lines.append(f"{base_indent}    - {item}")
            else:
                lines.append(f"{base_indent}{k_upper}: {v}")
    return lines


def evaluate_match(jd_req_toon: str, candidate_prof_toon: str) -> str:
    """
    Passes both the structured JD requirements and Candidate profiles to the LLM
    to calculate the final Match metrics based on the composite math.
    Returns the mapped data converted back to TOON format.
    """
    user_prompt = f"--- JD REQUIREMENTS ---\n{jd_req_toon}\n\n--- CANDIDATE PROFILE ---\n{candidate_prof_toon}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": MATCHING_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0
    )
    
    text = response.choices[0].message.content.strip()
    telemetry.log(response.usage, MATCHING_PROMPT + user_prompt, text)
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Verify JSON and convert to TOON
    try:
        data = json.loads(text)
        toon_lines = dict_to_toon(data)
        return "\n".join(toon_lines)
    except Exception as e:
        print(f"Failed to decode LLM JSON: {e}")
        return f"MATCH_RESULT\n    ERROR: Failed to generate valid match TOON\n"
