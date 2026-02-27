"""
plaintext_to_json.py
────────────────────
Converts raw resume plaintext → structured JSON dict.

Reuses the same pipeline as plaintext_to_toon:
    normalize → zone → extract_sections / contact / skills

Then assembles a JSON-ready dict with the schema:
    name, location, phone, email, summary, skills,
    experience [ {title, company, from, to, bullets} ],
    education, certifications, projects,
    _source_file, _format_detected
"""

import re
import json
from typing import Optional

from app.parsing.text_cleaning import (
    normalize_text_lossless,
    zone_resume_text,
    parse_trailer_key_values,
)
from app.parsing.contact_extract import extract_contact_info
from app.parsing.section_extract import extract_sections, extract_seniority_level
from app.parsing.skills_extract import extract_skills, NOISE_TOKENS

# ── Shared helpers (from plaintext_to_toon) ───────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_CATEGORY_LABEL_RE = re.compile(
    r"^(?:Frontend|Backend|Databases?|Cloud(?:\s+&?\s*Devops?)?|Testing(?:\s+&?\s*Qa?)?|"
    r"Messaging(?:\s+&?\s*Data\s+Processing)?|Auth(?:entication)?(?:\s+&?\s*Security)?|"
    r"Monitor(?:ing)?(?:\s+&?\s*Logging)?|Enterprise\s+Platforms?(?:\s+&?\s*Ecm?)?|"
    r"Development\s+Practices?|Tools?|Frameworks?|Languages?|Skills?|Technical\s+Skills?|"
    r"Mobile|Web|Data(?:base)?|Infrastructure|Devops|Security|Certifications?|Others?|"
    r"Microservices\s*&?\s*APIs?|GenAI\s*&?\s*LLMs?|Architecture\s*&?\s*Design\s*Patterns?|"
    r"Build\s*&?\s*Dependency\s*Mgmt|UI\s*/\s*Frontend|Caching)"
    r"\s*[:–-]",
    re.IGNORECASE,
)
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
_NOISE_SKILL_TOKENS = {"exposure", "secondary", "link", "primary", "intermediate", "advanced", "basic"}


def _extract_email(text: str) -> Optional[str]:
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else None


def _fallback_skill_extract(skills_section_text: str) -> list[str]:
    if not skills_section_text or not skills_section_text.strip():
        return []
    raw_skills: set[str] = set()
    for line in skills_section_text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = _CATEGORY_LABEL_RE.sub("", line).strip()
        line = _PARENTHETICAL_RE.sub("", line)
        parts = re.split(r"[,/]", line)
        for part in parts:
            skill = part.strip().strip("•–*- ")
            if not skill or len(skill) < 2:
                continue
            if skill.lower() in NOISE_TOKENS or skill.lower() in _NOISE_SKILL_TOKENS:
                continue
            if re.fullmatch(r"[\d.]+", skill):
                continue
            raw_skills.add(skill)
    return sorted(raw_skills)


# ── Date helpers ───────────────────────────────────────────────────────────────

# Matches: "Jan 2020", "January 2020", "01/2020", "2020", "Present", "Till Date", "Current"
_MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_TOKEN = (
    rf"(?:{_MONTH_NAMES}\s+\d{{4}}"       # "Jan 2020"
    rf"|\d{{1,2}}/\d{{4}}"                 # "01/2020"
    rf"|\d{{4}}"                             # "2020"
    rf"|[Pp]resent|[Cc]urrent|[Tt]ill\s+[Dd]ate|[Tt]o\s+[Dd]ate)"
)
_DATE_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN})\s*(?:[-–—to]+\s*({_DATE_TOKEN}))?",
    re.IGNORECASE,
)


def _extract_date_range(text: str) -> tuple[str, str]:
    """Return (from_date, to_date) strings from a date-range string, or ('', '')."""
    matches = list(_DATE_RANGE_RE.finditer(text))
    if not matches:
        return "", ""
    if len(matches) >= 2:
        return matches[0].group(1).strip(), matches[1].group(1).strip()
    m = matches[0]
    g1 = (m.group(1) or "").strip()
    g2 = (m.group(2) or "").strip()
    return g1, g2


# ── Experience entry parser ────────────────────────────────────────────────────

# Noise lines to skip inside bullet blocks
_TOOLS_LINE_RE = re.compile(
    r"^(?:Tools?|Environment|Tech(?:nology)?|Stack|Environments?|Tech\s+Stack)\s*:",
    re.IGNORECASE,
)
_SEPARATOR_RE = re.compile(r"^[-=_*]{4,}$")

# Patterns that signal a new job starts
# Pattern A — "Client: Company - Location --- Date – Date"
# Handles: '---', '- - -', ' -- ', or just a space before the date
_CLIENT_LINE_RE = re.compile(
    r"^Client\s*:\s*(.+?)\s*(?:(?:-\s*){2,}(?:-\s*)*|-{2,}|\s+)"
    r"(" + _DATE_TOKEN + r".*?)$",
    re.IGNORECASE,
)
# Pattern B: "Company Name  Date – Date" (whitespace gap or dash)
_COMPANY_DATE_LINE_RE = re.compile(
    rf"^(.+?)\s+({_DATE_TOKEN}.*)$",
    re.IGNORECASE,
)
# Pattern C: "Title | Company | Location    Date – Date"
_PIPE_HEADER_RE = re.compile(
    rf"^(.+?)\s*\|\s*(.+?)(?:\s*\|\s*\S+)?\s+({_DATE_TOKEN}.*)$",
    re.IGNORECASE,
)
# Pattern D: "Title at Company  Date"
_AT_HEADER_RE = re.compile(
    rf"^(.+?)\s+at\s+(.+?)\s+({_DATE_TOKEN}.*)$",
    re.IGNORECASE,
)
# Role line (follows Client: line in Raju-style)
_ROLE_LINE_RE = re.compile(r"^Role\s*:\s*(.+)$", re.IGNORECASE)
# Bullet indicators
_BULLET_PREFIX_RE = re.compile(r"^[•\-–\*o]\s+|^\d+\.\s+")


def _is_date_heavy(text: str) -> bool:
    """True if the line is predominantly date text."""
    dm = list(_DATE_RANGE_RE.finditer(text))
    if not dm:
        return False
    date_chars = sum(len(m.group()) for m in dm)
    return date_chars / max(len(text), 1) > 0.25


def _clean_bullet(line: str) -> str:
    line = _BULLET_PREFIX_RE.sub("", line.strip())
    return line.strip()


def _parse_experience_entries(emp_text: str) -> list[dict]:
    """
    Parse employment_history free text into a list of:
        {title, company, from, to, bullets}

    Handles 4 job-header formats:
      A) Client: Company - Location --- Date – Date  /  Role: Title
      B) Title | Company | Location    Date – Date
      C) Title at Company    Date
      D) Plain "Company  Date" line followed by title/role
    """
    if not emp_text or not emp_text.strip():
        return []

    lines = emp_text.splitlines()
    entries: list[dict] = []

    # ── Build a list of (line_index, parsed_header) ──────────────────────────
    job_markers: list[tuple[int, dict]] = []

    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw:
            i += 1
            continue

        # Pattern A — Client: Company ...  Date
        m = _CLIENT_LINE_RE.match(raw)
        if m:
            company = m.group(1).strip().rstrip("-–— \t")
            date_str = m.group(2).strip()
            frm, to = _extract_date_range(date_str)
            # Look ahead for Role: line
            title = ""
            j = i + 1
            while j < len(lines) and j < i + 5:
                nxt = lines[j].strip()
                rm = _ROLE_LINE_RE.match(nxt)
                if rm:
                    title = rm.group(1).strip()
                    break
                j += 1
            job_markers.append((i, {"title": title, "company": company, "from": frm, "to": to}))
            i += 1
            continue

        # Pattern B — Title | Company | Location    Date
        m = _PIPE_HEADER_RE.match(raw)
        if m:
            title = m.group(1).strip()
            company = m.group(2).strip()
            frm, to = _extract_date_range(m.group(3))
            job_markers.append((i, {"title": title, "company": company, "from": frm, "to": to}))
            i += 1
            continue

        # Pattern C — Title at Company    Date
        m = _AT_HEADER_RE.match(raw)
        if m:
            title = m.group(1).strip()
            company = m.group(2).strip()
            frm, to = _extract_date_range(m.group(3))
            job_markers.append((i, {"title": title, "company": company, "from": frm, "to": to}))
            i += 1
            continue

        # Pattern D — "Company   Date" (multi-space gap)
        m = _COMPANY_DATE_LINE_RE.match(raw)
        if m and _is_date_heavy(m.group(2)):
            company = m.group(1).strip()
            frm, to = _extract_date_range(m.group(2))
            # Try to get title from next non-blank line if it's a Role: line
            title = ""
            j = i + 1
            while j < len(lines) and j < i + 4:
                nxt = lines[j].strip()
                if nxt:
                    rm = _ROLE_LINE_RE.match(nxt)
                    title = rm.group(1).strip() if rm else nxt
                    break
                j += 1
            job_markers.append((i, {"title": title, "company": company, "from": frm, "to": to}))
            i += 1
            continue

        i += 1

    if not job_markers:
        # No structured entries found — return whole block as single entry
        bullets = [
            _clean_bullet(ln) for ln in lines
            if ln.strip() and not _SEPARATOR_RE.match(ln.strip()) and not _TOOLS_LINE_RE.match(ln.strip())
        ]
        return [{"title": "", "company": "", "from": "", "to": "", "bullets": bullets}]

    # ── Collect bullets for each job ─────────────────────────────────────────
    for idx, (marker_line, header) in enumerate(job_markers):
        start = marker_line + 1
        end = job_markers[idx + 1][0] if idx + 1 < len(job_markers) else len(lines)

        bullets = []
        for ln in lines[start:end]:
            stripped = ln.strip()
            if not stripped:
                continue
            if _SEPARATOR_RE.match(stripped):
                continue
            if _TOOLS_LINE_RE.match(stripped):
                # Also skip the next wrapped continuation line of a Tools: block
                # (they start with a closing paren or have dense comma lists)
                continue
            # Skip "Role: ..." lines (already captured as title)
            if _ROLE_LINE_RE.match(stripped):
                continue
            # Skip "Responsibilities:" header lines
            if re.match(r"^Responsibilities\s*:?\s*$", stripped, re.I):
                continue
            # Skip sub-header lines that are pure date text
            if _is_date_heavy(stripped) and len(stripped) < 50:
                continue
            # Skip tool-stack continuation lines:
            # identifies lines that are >35% commas (tech lists like "Maven, Jenkins, Docker, ...")
            # or start with a closing parenthesis (wrapped Tools: lines like "XSLT), WebSphere...")
            comma_ratio = stripped.count(",") / max(len(stripped), 1)
            if comma_ratio > 0.08 and len(stripped) > 60:
                # Likely a tool list — check if it lacks any verb (verbs indicate real bullets)
                has_verb = bool(re.search(
                    r"\b(?:developed|designed|implemented|created|built|used|integrated|"
                    r"deployed|optimized|architected|achieved|worked|managed|led|ensured|"
                    r"performed|configured|migrated|automated|resolved|wrote|developed)\b",
                    stripped, re.IGNORECASE,
                ))
                if not has_verb:
                    continue
            if stripped.startswith(")") or stripped.startswith("),"):
                continue
            # Also catch wrapped tool-list lines like "XSLT), Web sphere 7.0, ..."
            if re.match(r"^\w[\w./]+\),?\s+\w", stripped):
                continue
            cleaned = _clean_bullet(stripped)
            if cleaned:
                bullets.append(cleaned)

        entry = {**header, "bullets": bullets}
        entries.append(entry)

    return entries


# ── Education / Certifications / Projects parsers ─────────────────────────────

def _parse_education_entries(edu_text: str) -> list[str]:
    """Return education entries as a list of clean strings (one per line/degree)."""
    if not edu_text or not edu_text.strip():
        return []
    entries = []
    for ln in edu_text.splitlines():
        s = ln.strip()
        if not s or _SEPARATOR_RE.match(s):
            continue
        entries.append(s)
    return entries


def _parse_certification_entries(text: str) -> list[str]:
    """Split certifications on '|' or newlines, return clean list."""
    if not text or not text.strip():
        return []
    raw = []
    for part in re.split(r"\||\n", text):
        s = part.strip().strip("•–*-")
        if s and len(s) > 3:
            raw.append(s)
    return raw


def _parse_project_entries(text: str) -> list[str]:
    """Return project entries as clean strings."""
    if not text or not text.strip():
        return []
    entries = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or _SEPARATOR_RE.match(s):
            continue
        s = _BULLET_PREFIX_RE.sub("", s).strip()
        if s:
            entries.append(s)
    return entries


# ── Public API ─────────────────────────────────────────────────────────────────

def plaintext_to_json(
    raw_text: str,
    source_id: str = "",
    source_file: str = "",
) -> dict:
    """
    Convert raw resume plaintext directly to a structured JSON-ready dict.

    Parameters
    ----------
    raw_text    : Full raw resume plaintext (PLAINTEXT field from input JSON).
    source_id   : Optional GLOBAL_ID from input JSON.
    source_file : Original filename (e.g. 'Raju_Resume.json').

    Returns
    -------
    Python dict matching the target JSON schema.
    """

    # ── Step 1: Normalize & Zone ───────────────────────────────────────────────
    normalized = normalize_text_lossless(raw_text)
    body, trailer, _email_wrapper = zone_resume_text(normalized)
    trailer_kv = parse_trailer_key_values(trailer)

    # ── Step 2: Extract contact info ───────────────────────────────────────────
    contact = extract_contact_info(body)

    # Merge trailer KV overrides (highest priority)
    if trailer_kv.get("Name"):    contact["full_name"] = trailer_kv["Name"]
    if trailer_kv.get("Phone"):   contact["phone_raw"]  = trailer_kv["Phone"]
    if trailer_kv.get("Address"): contact["location"]   = trailer_kv["Address"]

    email = (
        trailer_kv.get("Email")
        or contact.get("email")
        or _extract_email(body)
        or _extract_email(_email_wrapper)
        or ""
    )

    # ── Step 3: Extract sections ───────────────────────────────────────────────
    sections = extract_sections(body)

    def _get(key: str) -> str:
        sec = sections.get(key, {})
        return (sec.get("content") or "") if isinstance(sec, dict) else ""

    # ── Step 4: Extract skills ─────────────────────────────────────────────────
    skills = extract_skills(body)
    if not skills:
        skills_text = _get("skills")
        if not skills_text:
            m = re.search(
                r"(?:TECHNICAL\s+)?SKILLS?\s*\n(.+?)(?=\n[A-Z][A-Z\s]{2,}\n|$)",
                body, re.DOTALL | re.IGNORECASE,
            )
            if m:
                skills_text = m.group(1)
        skills = _fallback_skill_extract(skills_text)

    # ── Step 5: Parse structured sections ─────────────────────────────────────
    emp_text = _get("employment_history")
    experience = _parse_experience_entries(emp_text)

    # Education vs Certifications — split if both present in same section text
    edu_text  = _get("education")
    cert_text = _get("certifications") if "certifications" in sections else ""

    # If no separate certifications section, try to split from education text
    if not cert_text and edu_text:
        cert_split = re.split(
            r"\n(?:CERTIFICATIONS?|CERTIFICATES?)\s*\n",
            edu_text, maxsplit=1, flags=re.IGNORECASE,
        )
        if len(cert_split) == 2:
            edu_text, cert_text = cert_split[0].strip(), cert_split[1].strip()

    education     = _parse_education_entries(edu_text)
    certifications = _parse_certification_entries(cert_text)
    projects       = _parse_project_entries(_get("projects"))

    # ── Step 6: Detect format ─────────────────────────────────────────────────
    format_detected = "standard"
    if re.search(r"Client\s*:", body, re.IGNORECASE):
        format_detected = "client_role"
    elif re.search(r"\bWORK HISTORY\b", body, re.IGNORECASE):
        format_detected = "work_history"
    elif re.search(r"----- START OF EMAIL", body, re.IGNORECASE):
        format_detected = "email_wrapped"

    # ── Step 7: Assemble output dict ──────────────────────────────────────────
    return {
        "name":           contact.get("full_name") or "",
        "location":       contact.get("location") or "",
        "phone":          contact.get("phone_raw") or "",
        "email":          email,
        "summary":        _get("summary"),
        "skills":         skills,
        "experience":     experience,
        "education":      education,
        "certifications": certifications,
        "projects":       projects,
        "_source_id":     source_id,
        "_source_file":   source_file,
        "_format_detected": format_detected,
    }
