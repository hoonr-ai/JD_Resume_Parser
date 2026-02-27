"""
plaintext_to_toon.py
────────────────────
Converts raw resume plaintext → TOON script directly.

Replaces the two-step:
    plaintext → build_combined_profile() [JSON dict] → json_to_toon()
with a single step:
    plaintext → plaintext_to_toon()

All extraction modules (text_cleaning, contact_extract, section_extract,
skills_extract) are reused unchanged. Only the assembly step is new.

Sections are emitted in schema-defined order:
    source, contact, work_authorization, compensation_preferences,
    role_preferences, summary, skills, employment_history, projects,
    education, publications_and_patents, awards_and_leadership,
    seniority_and_scope, employment_recency, stability_and_tenure,
    raw_extraction
"""

import re
from typing import Optional

from app.parsing.text_cleaning import (
    normalize_text_lossless,
    zone_resume_text,
    parse_trailer_key_values,
)
from app.parsing.contact_extract import extract_contact_info
from app.parsing.section_extract import extract_sections, extract_seniority_level
from app.parsing.skills_extract import extract_skills, NOISE_TOKENS


# ── Schema section order ───────────────────────────────────────────────────────

_SCHEMA_SECTIONS = [
    "source",
    "contact",
    "work_authorization",
    "compensation_preferences",
    "role_preferences",
    "summary",
    "skills",
    "employment_history",
    "projects",
    "education",
    "publications_and_patents",
    "awards_and_leadership",
    "seniority_and_scope",
    "employment_recency",
    "stability_and_tenure",
    "raw_extraction",
]


# ── TOON helpers ───────────────────────────────────────────────────────────────

def _section(name: str, body_lines: list[str]) -> str:
    """Wrap body_lines in SECTION / END_SECTION tags."""
    label = name.upper()
    inner = "\n".join(body_lines) if body_lines else "  EMPTY"
    return f"SECTION  {label}\n{inner}\nEND_SECTION  {label}"


def _val(v: Optional[str]) -> str:
    """Render a scalar; blank/None → NULL."""
    if v is None or str(v).strip() == "":
        return "NULL"
    return str(v).strip()


# ── Fallback employment extractor (no standard section header) ──────────────────

_RESPONSIBILITIES_SPLIT_RE = re.compile(
    r"(?=(?:Responsibilities|RESPONSIBILITIES)\s*:\s*\n)"
)
_TRAILING_NOISE_RE = re.compile(
    r"(?:\n|^)(?:EDUCATION|CERTIFICATIONS?|AWARDS?|PUBLICATIONS?)"
    r"(?:\s*[:.]|\s*\n)",
    re.IGNORECASE,
)


def _fallback_employment_extract(body: str) -> Optional[str]:
    """
    Fallback for resumes that list work history as repeating
    'Responsibilities: ... Environment: ...' blocks with no top-level
    section header (e.g. no 'PROFESSIONAL EXPERIENCE' heading).

    Returns the extracted text if at least 1 block found, else None.
    """
    # Only trigger if the body contains multiple Responsibilities: occurrences
    occ = [m.start() for m in
           re.finditer(r"(?:^|\n)Responsibilities\s*:", body, re.IGNORECASE)]
    if not occ:
        return None

    # Grab everything from the first Responsibilities: onward
    start = occ[0]
    chunk = body[start:]

    # Cut off at EDUCATION / CERTIFICATIONS if they appear later
    cut = _TRAILING_NOISE_RE.search(chunk)
    if cut:
        chunk = chunk[:cut.start()]

    return chunk.strip() if chunk.strip() else None


# ── Fallback for orphaned-date / multi-column PDF resumes ─────────────────────

# Matches date ranges like: 11/2024, 01/2023, January 2013, 2014 - 2019, etc.
_DATE_RANGE_RE = re.compile(
    r"(?:"
    r"\d{1,2}/\d{4}"                       # 04/2025
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}"                             # October 2013
    r"|\d{4}"                               # plain year
    r")"                                    # end outer group
    r"(?:\s*[-–to]+\s*"
    r"(?:\d{1,2}/\d{4}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}|\d{4}|[Pp]resent|[Cc]urrent"
    r"))?",
    re.IGNORECASE,
)

# Known section headers to use as stop signals
_STOP_SECTION_RE = re.compile(
    r"^(?:EDUCATION|EDUCATION/TRAINING|EDUCATION AND TRAINING|TRAINING|CERTIFICATIONS?|"
    r"SKILLS|TECHNICAL\s+SKILLS|AWARDS?|PUBLICATIONS?|PROJECTS?|SUMMARY|PROFILE|LANGUAGES?|"
    r"REFERENCES?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _fallback_work_history_extract(body: str) -> Optional[str]:
    """
    Fallback for two hard cases that _fallback_employment_extract() misses:

    Case A — Bare 'Job Title at Company' lines (CareerBuilder email format):
        Lines like 'Java Full stack developer at' with a date on the next line.
        Assembles each pair into a readable entry.

    Case B — Multi-column PDF collapse (Ricardo-style):
        Dates appear as orphaned lines at the very top of the document.
        Job titles and companies appear later with NO dates beside them.
        Strategy: collect all floating date ranges from the top block, then
        output the EXPERIENCE section content with the date pool prepended.

    Returns extracted employment text or None.
    """
    lines = body.splitlines()

    # ── Case A: 'Job Title at' line followed by date line ──────────────────────
    at_pattern = re.compile(
        r"^(.+?)\s+at\s*$",  # e.g. "Java Full stack developer at"
        re.IGNORECASE,
    )
    entries_a: list[str] = []
    i = 0
    while i < len(lines):
        m = at_pattern.match(lines[i].strip())
        if m:
            title = m.group(1).strip()
            # Next non-blank line should be a date
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _DATE_RANGE_RE.search(lines[j]):
                date_str = lines[j].strip()
                # Also grab the line after dates if it looks like a duration note
                entries_a.append(f"{title}\n{date_str}")
                i = j + 1
                continue
        i += 1

    if entries_a:
        return "\n\n".join(entries_a)

    # ── Case B: Detect a block of orphaned date-only lines near the top ────────
    SCAN_TOP = min(25, len(lines))  # only look in first 25 lines for date cluster
    floating_dates: list[str] = []
    date_line_indices: set[int] = set()

    for idx, line in enumerate(lines[:SCAN_TOP]):
        stripped = line.strip()
        if not stripped:
            continue
        # Line is "mostly dates" if > 30% of its non-space chars are digits/slashes
        date_matches = list(_DATE_RANGE_RE.finditer(stripped))
        if date_matches:
            date_chars = sum(len(m.group()) for m in date_matches)
            if date_chars / max(len(stripped), 1) > 0.3:
                floating_dates.append(stripped)
                date_line_indices.add(idx)

    if len(floating_dates) < 2:
        return None  # Not a multi-column PDF pattern — give up

    # Try to find an EXPERIENCE block with actual content after the header
    exp_match = re.search(
        r"^(?:EXPERIENCE|PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT|EMPLOYMENT HISTORY)"
        r"\s*\n((?!\s*(?:SKILLS|TECHNICAL\s+SKILLS|SUMMARY|PROFILE|EDUCATION|LANGUAGES?|PROJECTS?))"
        r".+?)(?=\n[A-Z][A-Z\s]{2,}\n|$)",
        body,
        re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )

    exp_block = ""
    if exp_match:
        candidate = exp_match.group(1).strip()
        stop = _STOP_SECTION_RE.search(candidate)
        if stop:
            candidate = candidate[:stop.start()].strip()
        if candidate:
            exp_block = candidate

    # If the EXPERIENCE section is empty (next line is immediately another header),
    # look for late-appearing job entries anywhere in the body after all section headers.
    # These are lines that look like: "Job Title", "Company Name", bullet points, etc.
    # Strategy: collect text from after the last known section header cluster
    if not exp_block:
        # Find positions of all section header lines
        header_pattern = re.compile(
            r"^(?:EXPERIENCE|SKILLS|TECHNICAL\s+SKILLS|SUMMARY|EDUCATION|LANGUAGES?|"
            r"PROJECTS?|CERTIFICATIONS?|REFERENCES?|PROFILE|OBJECTIVE|TRAINING)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        header_spans = [(m.start(), m.end()) for m in header_pattern.finditer(body)]

        if header_spans:
            # Take text from after the last cluster of consecutive headers
            # (they tend to bunch at the top of a multi-col PDF)
            last_header_end = header_spans[-1][1]
            late_content = body[last_header_end:].strip()

            # Cut off at trailer markers
            cut = re.search(r"-----\s*END OF RESUME|-----\s*START OF EMAIL", late_content)
            if cut:
                late_content = late_content[:cut.start()].strip()

            if late_content and len(late_content) > 50:
                exp_block = late_content

    if not exp_block:
        return None

    # Prepend the floating date pool as a note for context
    date_pool = "  ".join(floating_dates)
    return (
        f"[Date ranges found in document: {date_pool}]\n\n"
        f"{exp_block}"
    )


# ── Fallback skill extractor (no DB needed) ───────────────────────────────────

_CATEGORY_LABEL_RE = re.compile(
    r"^(?:Frontend|Backend|Databases?|Cloud(?:\s+&?\s*Devops?)?|Testing(?:\s+&?\s*Qa?)?|"
    r"Messaging(?:\s+&?\s*Data\s+Processing)?|Auth(?:entication)?(?:\s+&?\s*Security)?|"
    r"Monitor(?:ing)?(?:\s+&?\s*Logging)?|Enterprise\s+Platforms?(?:\s+&?\s*Ecm?)?|"
    r"Development\s+Practices?|Tools?|Frameworks?|Languages?|Skills?|Technical\s+Skills?|"
    r"Mobile|Web|Data(?:base)?|Infrastructure|Devops|Security|Certifications?|Others?)"
    r"\s*[:–-]",
    re.IGNORECASE,
)

_PARENTHETICAL_RE   = re.compile(r"\([^)]*\)")
_NOISE_SKILL_TOKENS = {"exposure", "secondary", "link", "primary", "intermediate", "advanced", "basic"}


def _fallback_skill_extract(skills_section_text: str) -> list[str]:
    """
    Regex-based skill extractor that works without the Supabase ontology.
    Parses the SKILLS / TECHNICAL SKILLS section text, strips category labels
    (e.g. 'Frontend:', 'Backend:'), and splits on commas / newlines.
    """
    if not skills_section_text or not skills_section_text.strip():
        return []

    raw_skills: set[str] = set()

    for line in skills_section_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Strip category label prefix  e.g. "Frontend: TypeScript, Angular..."
        line = _CATEGORY_LABEL_RE.sub("", line).strip()

        # Remove parentheticals  e.g. "(ES6+)" or "(exposure)"
        line = _PARENTHETICAL_RE.sub("", line)

        # Split on comma or slash
        parts = re.split(r"[,/]", line)
        for part in parts:
            skill = part.strip().strip("•–*- ")
            if not skill:
                continue
            skill_lower = skill.lower()
            # Skip short noise tokens
            if len(skill) < 2:
                continue
            if skill_lower in NOISE_TOKENS or skill_lower in _NOISE_SKILL_TOKENS:
                continue
            # Skip pure numbers or year-like tokens
            if re.fullmatch(r"[\d.]+", skill):
                continue
            raw_skills.add(skill)

    return sorted(raw_skills)


_SEPARATOR_LINE_RE = re.compile(r'^[_\-=*]{4,}$')


def _content_lines(text: Optional[str]) -> list[str]:
    """
    Split a multi-line content blob into consistently indented plain-text lines.

    Rules:
      - 2-space indent on every line — no bullets, no markers.
      - Separator-only lines (______, ------) are dropped; they add zero value for LLM.
      - Leading bullet/dash chars (•, –, *, -) are stripped from each line.
      - Blank lines preserved as single separators between blocks.
      - Single-line content is inlined without a leading blank.
    """
    if not text or not text.strip():
        return ["  EMPTY"]

    lines = text.strip().splitlines()
    non_blank = [l for l in lines if l.strip()]
    if len(non_blank) == 1:
        content = re.sub(r"^[•\-\u2013*]\s*", "", non_blank[0].strip())
        return [f"  {content}"]

    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
        elif _SEPARATOR_LINE_RE.match(stripped):
            # Drop pure separator lines — token waste
            continue
        else:
            stripped = re.sub(r"^[•\-\u2013*]\s*", "", stripped)
            out.append(f"  {stripped}")

    while out and out[-1] == "":
        out.pop()
    return out


# ── Section-specific writers ───────────────────────────────────────────────────

def _write_source(source_id: str) -> str:
    lines = [f"  GLOBAL_ID  {_val(source_id)}"]
    return _section("SOURCE", lines)


def _write_contact(contact: dict, email: Optional[str] = None) -> str:
    lines = [
        f"  EMAIL  {_val(email or contact.get('email'))}",
        f"  FULL_NAME  {_val(contact.get('full_name'))}",
        f"  GITHUB  {_val(contact.get('github'))}",
        f"  LINKEDIN  {_val(contact.get('linkedin'))}",
        f"  LOCATION  {_val(contact.get('location'))}",
        f"  PHONE_E164  {_val(contact.get('phone_e164'))}",
        f"  PHONE_RAW  {_val(contact.get('phone_raw'))}",
    ]
    return _section("CONTACT", lines)


def _write_skills(skills: list[str]) -> str:
    if not skills:
        return _section("SKILLS", ["  EMPTY"])
    lines = [f"  ITEM  {s.strip()}" for s in skills if s.strip()]
    return _section("SKILLS", lines)


def _write_content_section(name: str, text: Optional[str]) -> str:
    return _section(name, _content_lines(text))


def _write_seniority(level: Optional[str]) -> str:
    return _section("SENIORITY_AND_SCOPE", [f"  SENIORITY_LEVEL  {_val(level)}"])


def _write_empty(name: str) -> str:
    return _section(name, ["  EMPTY"])


def _write_raw_extraction(body: str) -> str:
    # Store the full normalized body verbatim, line by line
    lines: list[str] = []
    for raw in body.strip().splitlines():
        stripped = raw.strip()
        if stripped:
            lines.append(f"  {stripped}")
        else:
            lines.append("")
    return _section("RAW_EXTRACTION", lines if lines else ["  EMPTY"])


# ── Email extraction helper ────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

def _extract_email(text: str) -> Optional[str]:
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else None


# ── Work authorization detection ───────────────────────────────────────────────

_WORK_AUTH_RE = re.compile(
    r"\b(us\s*citizen|green\s*card|h[\-\s]?1b?|opt|cpt|ead|tn\s*visa|"
    r"authorized\s+to\s+work|work\s+authorization|visa\s+status|"
    r"permanent\s+resident|no\s+sponsorship|require\s+sponsorship)\b",
    re.IGNORECASE,
)

def _extract_work_auth(text: str) -> Optional[str]:
    """Return the first sentence/phrase mentioning work authorization."""
    for line in text.splitlines():
        if _WORK_AUTH_RE.search(line):
            return line.strip()
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def plaintext_to_toon(raw_text: str, source_id: str = "") -> str:
    """
    Convert raw resume plaintext directly to a TOON script.

    Parameters
    ----------
    raw_text  : The full raw resume text (PLAINTEXT field from the input JSON).
    source_id : Optional source/global ID to populate the SOURCE section
                (e.g. GLOBAL_ID from the input JSON).

    Returns
    -------
    A TOON-formatted string ready to save as a .toon file.
    """

    # ── Step 1: Normalize & Zone ───────────────────────────────────────────────
    normalized = normalize_text_lossless(raw_text)
    body, trailer, _email_wrapper = zone_resume_text(normalized)
    trailer_kv = parse_trailer_key_values(trailer)

    # ── Step 2: Extract pieces ─────────────────────────────────────────────────
    contact = extract_contact_info(body)

    # Merge trailer KV (highest priority)
    if trailer_kv.get("Name"):    contact["full_name"] = trailer_kv["Name"]
    if trailer_kv.get("Phone"):   contact["phone_raw"] = trailer_kv["Phone"]
    if trailer_kv.get("Address"): contact["location"]  = trailer_kv["Address"]

    # Email: trailer KV → body regex → email_wrapper regex
    email = (
        trailer_kv.get("Email")
        or _extract_email(body)
        or _extract_email(_email_wrapper)
    )

    sections  = extract_sections(body)
    skills    = extract_skills(body)

    # Fallback: if ontology extractor returned nothing (DB unavailable),
    # parse skills directly from the SKILLS section text
    if not skills:
        skills_section_text = (
            sections.get("skills", {}).get("content", "") or ""
        )
        # Also try the raw body if section wasn't detected
        if not skills_section_text:
            # Look for TECHNICAL SKILLS block in body text
            m = re.search(
                r"(?:TECHNICAL\s+)?SKILLS?\s*\n(.+?)(?=\n[A-Z][A-Z\s]{2,}\n|$)",
                body, re.DOTALL | re.IGNORECASE
            )
            if m:
                skills_section_text = m.group(1)
        skills = _fallback_skill_extract(skills_section_text)

    seniority = extract_seniority_level(body)
    work_auth = _extract_work_auth(body)

    # ── Step 3: Build TOON in schema order ─────────────────────────────────────
    toon_blocks: list[str] = ["TOON_VERSION  1.0", ""]

    def _get_content(sec_key: str) -> Optional[str]:
        sec = sections.get(sec_key, {})
        return sec.get("content") if isinstance(sec, dict) else None

    for sec_name in _SCHEMA_SECTIONS:
        if sec_name == "source":
            block = _write_source(source_id)

        elif sec_name == "contact":
            block = _write_contact(contact, email)

        elif sec_name == "work_authorization":
            block = _write_content_section("WORK_AUTHORIZATION", work_auth)

        elif sec_name == "compensation_preferences":
            block = _write_empty("COMPENSATION_PREFERENCES")

        elif sec_name == "role_preferences":
            block = _write_empty("ROLE_PREFERENCES")

        elif sec_name == "summary":
            text = _get_content("summary")
            block = _write_content_section("SUMMARY", text)

        elif sec_name == "skills":
            block = _write_skills(skills)

        elif sec_name == "employment_history":
            text = _get_content("employment_history")
            # Fallback 1: catch resumes that use Responsibilities: blocks
            # with no standard employment section header
            if not text:
                text = _fallback_employment_extract(body)
            # Fallback 2: multi-column PDF collapse or bare 'job at' lines
            if not text:
                text = _fallback_work_history_extract(body)
            block = _write_content_section("EMPLOYMENT_HISTORY", text)

        elif sec_name == "projects":
            text = _get_content("projects")
            block = _write_content_section("PROJECTS", text)

        elif sec_name == "education":
            text = _get_content("education")
            block = _write_content_section("EDUCATION", text)

        elif sec_name == "publications_and_patents":
            text = _get_content("publications_and_patents")
            block = (
                _write_content_section("PUBLICATIONS_AND_PATENTS", text)
                if text else _write_empty("PUBLICATIONS_AND_PATENTS")
            )

        elif sec_name == "awards_and_leadership":
            text = _get_content("awards_and_leadership")
            block = (
                _write_content_section("AWARDS_AND_LEADERSHIP", text)
                if text else _write_empty("AWARDS_AND_LEADERSHIP")
            )

        elif sec_name == "seniority_and_scope":
            block = _write_seniority(seniority)

        elif sec_name == "employment_recency":
            block = _write_empty("EMPLOYMENT_RECENCY")

        elif sec_name == "stability_and_tenure":
            block = _write_empty("STABILITY_AND_TENURE")

        elif sec_name == "raw_extraction":
            block = _write_raw_extraction(body)

        else:
            block = _write_empty(sec_name.upper())

        toon_blocks.append(block)
        toon_blocks.append("")   # blank line between sections

    return "\n".join(toon_blocks)
