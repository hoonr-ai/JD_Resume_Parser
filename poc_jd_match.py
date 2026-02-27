"""
poc_jd_match.py
───────────────
Proof-of-concept: send 1 candidate TOON + 1 JD to the LLM and get back
a structured JD-contextual match report.

Run from project root:
    cmd /c "set PYTHONPATH=backend && .resparse\Scripts\python.exe poc_jd_match.py"
"""

import asyncio, json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ── paths ────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
TOON_FILE = ROOT / "backend/Final_output_TOON_clean/surya_final_parsed_structure.toon"
JD_FILE   = ROOT / "backend/JD/j1.json"
OUT_FILE  = ROOT / "poc_match_output.json"

load_dotenv(ROOT / "backend/.env")
API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── prompt ───────────────────────────────────────────────────────────────────
SYSTEM = """\
You are a precise technical recruiter assistant.
Given a candidate's TOON resume script and a structured JD, you:
1. Identify which JD-required skills the candidate actually has evidence of in their TOON.
2. For each matched skill, score the candidate's proficiency (1–5 scale).
3. List required skills the candidate is MISSING entirely.
4. Produce an overall match percentage (0–100).

Be strict: only report a skill as matched if there is real evidence in the candidate's EMPLOYMENT_HISTORY.
Do NOT infer a skill from the SKILLS section alone — it must appear in actual work experience.
Return ONLY valid JSON. No markdown, no commentary.
"""

USER_TEMPLATE = """\
CANDIDATE_TOON:
{toon}

JOB_DESCRIPTION_REQUIREMENTS:
{jd}

OUTPUT_SCHEMA:
{{
  "jd_id": "string",
  "candidate_id": "string",
  "match_summary": {{
    "overall_match_pct": number,
    "mandatory_skills_matched": number,
    "mandatory_skills_total": number,
    "optional_skills_matched": number,
    "optional_skills_total": number
  }},
  "matched_skills": [
    {{
      "jd_skill": "string",
      "candidate_skill": "string",
      "mandatory": boolean,
      "jd_min_years": number,
      "jd_required_level": number,
      "candidate_proficiency": number,
      "evidence_snippet": "brief quote from EMPLOYMENT_HISTORY (≤ 20 words)"
    }}
  ],
  "missing_required_skills": ["string"],
  "missing_optional_skills": ["string"],
  "recruiter_summary": "2-3 sentence plain-English summary of fit"
}}
"""

# ── main ─────────────────────────────────────────────────────────────────────
async def run():
    print("Reading TOON and JD files…")
    toon = TOON_FILE.read_text(encoding="utf-8")
    jd_data = json.loads(JD_FILE.read_text(encoding="utf-8"))
    jd = json.dumps(jd_data[0]["TOON"]["jd_skill_requirements"], indent=2)

    # Extract candidate name from TOON for labelling
    candidate_id = TOON_FILE.stem.replace("_final_parsed_structure", "")

    user_prompt = USER_TEMPLATE.format(toon=toon, jd=jd)

    print(f"Sending to LLM  (candidate={candidate_id}, jd_id={jd_data[0]['TOON']['jd_skill_requirements']['jd_id']})…")
    client = AsyncOpenAI(api_key=API_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
    )

    raw = resp.choices[0].message.content
    result = json.loads(raw)
    # Inject candidate_id if LLM left it blank
    result.setdefault("candidate_id", candidate_id)

    # ── Telemetry ──────────────────────────────────────────────────────────
    usage = resp.usage
    # GPT-4o-mini pricing (as of Feb 2026): $0.150 / 1M input, $0.600 / 1M output
    PRICE_IN  = 0.150 / 1_000_000
    PRICE_OUT = 0.600 / 1_000_000
    cost_in   = usage.prompt_tokens     * PRICE_IN
    cost_out  = usage.completion_tokens * PRICE_OUT
    cost_total = cost_in + cost_out

    OUT_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n✅  Output saved → {OUT_FILE}\n")

    # Print a human-readable summary to console
    ms = result.get("match_summary", {})
    print("=" * 60)
    print(f"  JD ID        : {result.get('jd_id')}")
    print(f"  Candidate    : {result.get('candidate_id')}")
    print(f"  Overall Match: {ms.get('overall_match_pct')}%")
    print(f"  Mandatory    : {ms.get('mandatory_skills_matched')}/{ms.get('mandatory_skills_total')} matched")
    print(f"  Optional     : {ms.get('optional_skills_matched')}/{ms.get('optional_skills_total')} matched")
    print()
    print("  Matched skills:")
    for s in result.get("matched_skills", []):
        flag = "★" if s.get("mandatory") else "◇"
        print(f"    {flag} {s['jd_skill']:<30} proficiency={s['candidate_proficiency']}/5")
    print()
    missing = result.get("missing_required_skills", [])
    if missing:
        print(f"  MISSING required: {', '.join(missing)}")
    print()
    print(f"  Recruiter note: {result.get('recruiter_summary', '')}")
    print()
    print("  ── LLM Telemetry ─────────────────────────────────────")
    print(f"  Model          : {resp.model}")
    print(f"  Prompt tokens  : {usage.prompt_tokens:,}")
    print(f"  Output tokens  : {usage.completion_tokens:,}")
    print(f"  Total tokens   : {usage.total_tokens:,}")
    print(f"  Input cost     : ${cost_in:.6f}")
    print(f"  Output cost    : ${cost_out:.6f}")
    print(f"  TOTAL COST     : ${cost_total:.6f}  (~${cost_total*83:.4f} INR)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
