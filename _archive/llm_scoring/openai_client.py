"""
openai_client.py — Async OpenAI GPT-4o-mini client for skill extraction.

Architecture:
  1. Python pre-computes temporal metrics (years_total, years_recent_3,
     last_used_date, recency_weight) via skill_date_calculator — accurate,
     deterministic, no LLM hallucination on date math.
  2. LLM is asked ONLY for qualitative scores:
       proficiency_score, frequency_score, impact_weight, seniority_weight
  3. composite_skill_score is computed in Python after the LLM call.
"""

import json
import logging
import os
from math import ceil

logger = logging.getLogger(__name__)


# ── Prompt templates ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a resume intelligence engine.
You receive a TOON-formatted candidate profile with pre-computed temporal metrics.
Your ONLY task is to assign subjective scores for each listed skill:
  proficiency_score  : integer 1–5 (depth of knowledge: 1=awareness, 3=working, 5=expert)
  frequency_score    : float   0–5 (how often used — 5=daily, 1=rarely)
  impact_weight      : integer 1–5 (business/project impact)
  seniority_weight   : integer 1–5 (5=led/architected, 1=assisted)

Rules:
  - Use DIFFERENTIATED scoring — do NOT give every skill the same score.
  - Base scores ONLY on evidence in EMPLOYMENT_HISTORY.
  - Skills used briefly or only in coursework score lower than skills used for years.
  - Output ONLY valid JSON matching the schema. No explanations. No extra keys.\
"""

_USER_PROMPT_TEMPLATE = """\
CANDIDATE_ID: {candidate_id}
CURRENT_DATE: {current_date}

TOON_INPUT:
{toon_script}

PRE_COMPUTED_SKILL_METRICS:
(Temporal values below are calculated from actual employment dates. Do NOT recompute.)
{metrics_table}

MANDATORY SKILL LIST — You MUST score EXACTLY these {skill_count} skills.
Do NOT add any other skill. Do NOT omit any skill from this list.
{mandatory_skill_list}

SCORING_TASK:
For each skill in the MANDATORY SKILL LIST above, assign:
  proficiency_score  (int 1-5)   : depth of expertise
  frequency_score    (float 0-5) : how frequently used across roles
  impact_weight      (int 1-5)   : business/project impact
  seniority_weight   (int 1-5)   : ownership level

Use CONSERVATIVE, DIFFERENTIATED scoring. Spread scores across the 1-5 range.
Base scores ONLY on evidence in EMPLOYMENT_HISTORY.

OUTPUT_SCHEMA:
{{
  "candidate_skill_profile": {{
    "candidate_id": "string",
    "skills": [
      {{
        "skill_id": "string",
        "canonical_name": "string (must match a skill from MANDATORY SKILL LIST exactly)",
        "proficiency_score": integer,
        "frequency_score": float,
        "impact_weight": integer,
        "seniority_weight": integer
      }}
    ]
  }}
}}

Return JSON only.\
"""


# ── Composite score formula ────────────────────────────────────────────────────

def _composite(
    years_total: float,
    years_recent_3: float,
    proficiency: int,
    impact: int,
    seniority: int,
    recency_weight: float,
) -> float:
    raw = (
        years_total    * 0.25
        + years_recent_3 * 0.25
        + proficiency    * 0.20
        + impact         * 0.15
        + seniority      * 0.15
    )
    return round(raw * recency_weight, 4)


# ── Client ─────────────────────────────────────────────────────────────────────

async def run_skill_extraction_llm(toon_script: str, candidate_id: str) -> dict:
    """
    1. Pre-compute temporal metrics per skill (pure Python — no LLM date math).
    2. Ask LLM only for proficiency / frequency / impact / seniority.
    3. Merge and compute composite_skill_score in Python.
    4. Return full candidate_skill_profile dict.
    """
    from openai import AsyncOpenAI
    from datetime import date
    from app.llm.skill_date_calculator import (
        compute_all_skill_metrics,
        filter_top_skills,
        format_metrics_table,
        MAX_SKILLS_PER_PROFILE,
    )

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. Add a valid key to backend/.env"
        )

    today        = date.today()
    current_date = today.isoformat()

    # ── Step 1: Python pre-computation ────────────────────────────────────────
    all_metrics   = compute_all_skill_metrics(toon_script, today)
    precomputed   = filter_top_skills(all_metrics)   # top-15 by evidence strength
    metrics_table = format_metrics_table(precomputed)

    print(
        f"\n  [SKILL DATE CALCULATOR] "
        f"{len(all_metrics)} skills computed → top {MAX_SKILLS_PER_PROFILE} selected:"
    )
    for skill, m in precomputed.items():
        print(
            f"    {skill:<40}  "
            f"total={m['years_total']:.2f}y  "
            f"recent3={m['years_recent_3']:.2f}y  "
            f"last={m['last_used_date']}  "
            f"rw={m['recency_weight']}"
        )

    # ── Step 2: Build prompt ───────────────────────────────────────────────────
    # Build numbered mandatory skill list so LLM can't add extras
    mandatory_skill_list = "\n".join(
        f"  {i+1}. {skill}" for i, skill in enumerate(precomputed.keys())
    )

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        candidate_id         = candidate_id,
        toon_script          = toon_script,
        current_date         = current_date,
        metrics_table        = metrics_table,
        skill_count          = len(precomputed),
        mandatory_skill_list = mandatory_skill_list,
    )

    client = AsyncOpenAI(api_key=api_key)

    # ── Telemetry (pre-call) ───────────────────────────────────────────────────
    input_chars   = len(user_prompt)
    approx_tokens = ceil(input_chars / 4)
    logger.info(
        "LLM_CALL\n"
        f"  FILE_NAME      {candidate_id}\n"
        f"  INPUT_CHARS    {input_chars}\n"
        f"  APPROX_TOKENS  {approx_tokens}"
    )

    # ── Step 3: LLM call ──────────────────────────────────────────────────────
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw_output = response.choices[0].message.content or "{}"

    # ── Telemetry (post-call) ─────────────────────────────────────────────────
    usage         = response.usage
    prompt_tokens = usage.prompt_tokens     if usage else approx_tokens
    output_tokens = usage.completion_tokens if usage else ceil(len(raw_output) / 4)
    total_tokens  = usage.total_tokens      if usage else prompt_tokens + output_tokens
    input_cost    = (prompt_tokens / 1_000_000) * 0.150
    output_cost   = (output_tokens / 1_000_000) * 0.600
    total_cost    = input_cost + output_cost

    print(
        f"\n  [LLM TELEMETRY]\n"
        f"  FILE_NAME      {candidate_id}\n"
        f"  PROMPT_TOKENS  {prompt_tokens}\n"
        f"  OUTPUT_TOKENS  {output_tokens}\n"
        f"  TOTAL_TOKENS   {total_tokens}\n"
        f"  COST_USD       ${total_cost:.6f}\n"
        f"  END"
    )
    logger.info(
        f"  PROMPT_TOKENS  {prompt_tokens}\n"
        f"  OUTPUT_TOKENS  {output_tokens}\n"
        f"  TOTAL_TOKENS   {total_tokens}\n"
        f"  COST_USD       ${total_cost:.6f}\n"
        "END"
    )

    # ── Step 4: Parse LLM JSON ────────────────────────────────────────────────
    try:
        llm_result = json.loads(raw_output)
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned non-JSON for {candidate_id}: {e}")
        raise ValueError(f"LLM response was not valid JSON: {e}") from e

    llm_skills: list[dict] = (
        llm_result
        .get("candidate_skill_profile", {})
        .get("skills", [])
    )

    # ── Step 5: Merge LLM scores with Python-computed temporal metrics ─────────
    merged_skills = []
    for idx, skill_entry in enumerate(llm_skills):
        canonical = skill_entry.get("canonical_name", "")

        # Case-insensitive lookup in precomputed
        pc = (
            precomputed.get(canonical)
            or precomputed.get(canonical.lower())
            or next(
                (v for k, v in precomputed.items()
                 if k.lower() == canonical.lower()),
                None
            )
        )

        if pc is None:
            # Not in precomputed — include with zero temporal metrics so no data is lost
            logger.debug(f"Skill '{canonical}' not in precomputed list — using zero temporal metrics.")
            pc = {
                "years_total":    0.0,
                "years_recent_3": 0.0,
                "last_used_date": None,
                "recency_weight": 1.0,   # neutral so proficiency/impact still score
            }

        proficiency = int(skill_entry.get("proficiency_score", 3))
        frequency   = float(skill_entry.get("frequency_score", 2.5))
        impact      = int(skill_entry.get("impact_weight", 3))
        seniority   = int(skill_entry.get("seniority_weight", 3))

        composite = _composite(
            years_total    = pc["years_total"],
            years_recent_3 = pc["years_recent_3"],
            proficiency    = proficiency,
            impact         = impact,
            seniority      = seniority,
            recency_weight = pc["recency_weight"],
        )

        merged_skills.append({
            "skill_id":              str(idx + 1),
            "canonical_name":        canonical,
            "years_total":           pc["years_total"],
            "years_recent_3":        pc["years_recent_3"],
            "last_used_date":        pc["last_used_date"],
            "proficiency_score":     proficiency,
            "frequency_score":       frequency,
            "impact_weight":         impact,
            "recency_weight":        pc["recency_weight"],
            "seniority_weight":      seniority,
            "composite_skill_score": composite,
        })

    return {
        "candidate_skill_profile": {
            "candidate_id": candidate_id,
            "skills": merged_skills,
        }
    }
