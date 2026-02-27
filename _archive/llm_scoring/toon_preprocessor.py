"""
toon_preprocessor.py
────────────────────
Cleans and neatly formats a TOON script before sending it to the LLM.

What gets removed / reformatted:
  1. RAW_EXTRACTION section  — duplicate of EMPLOYMENT_HISTORY; also causes
                               the LLM to anchor on self-reported "X years"
  2. Empty/boilerplate sections — SECTIONS, SCHEMA_VERSION, ENTITY, SOURCE,
                                  ROLE_PREFERENCES, EMPLOYMENT_RECENCY,
                                  STABILITY_AND_TENURE, etc.
  3. EMPLOYMENT_HISTORY       — reformatted so each role block is cleanly
                                separated and readable (no clutter or run-ons)
  4. SKILLS noise filtering   — drops generic / false-positive tokens including
                                single meaningful-sounding words that are not
                                real skill names (File, Basic, Navigation, etc.)
  5. SUMMARY truncation       — first 5 sentences or ≤ 600 chars
"""

import re
from typing import Optional


# ── Sections to drop entirely ──────────────────────────────────────────────────

_DROP_SECTIONS = {
    "RAW_EXTRACTION",
    "SECTIONS",
    "SCHEMA_VERSION",
    "ENTITY",
    "SOURCE",
    "ROLE_PREFERENCES",
    "EMPLOYMENT_RECENCY",
    "STABILITY_AND_TENURE",
}

# Sections dropped only when body == EMPTY / blank
_DROP_IF_EMPTY = {
    "AWARDS_AND_LEADERSHIP", "COMPENSATION_PREFERENCES", "EDUCATION",
    "PROJECTS", "PUBLICATIONS_AND_PATENTS", "WORK_AUTHORIZATION",
    "SUMMARY",
}


# ── Skill noise lists ──────────────────────────────────────────────────────────

# Generic single words / multi-word phrases that FlashText commonly mis-tags
_NOISE_TOKENS: set[str] = {
    # Pure generics
    "design", "tool", "tools", "framework", "frameworks", "server", "database",
    "software", "development", "architecture", "testing", "logging", "monitoring",
    "routing", "parsing", "streaming", "storage", "mapping", "embedded",
    "concurrency", "threading", "encryption", "performance", "scheduling",
    "optimization", "hardware", "mobile", "portal", "cloud", "frontend",
    "backend", "web", "api", "gui", "http", "enterprise", "verification",
    "access", "search", "collections", "configuration", "privacy", "tags",
    "scratch", "make", "rc", "arrow", "go", "ai", "npm", "vector",
    "concurrent", "messaging", "scripting language", "scripting languages",
    "no sql", "nosql", "data access", "data transfer", "version control",
    "build automation", "static analysis", "dependency injection",
    "simple directmedia layer", "windows embedded compact", "millenniumdb",
    "java class library", "object oriented", "data processing", "user interface",
    # Plain nouns broken out of compound skill names
    "file", "basic", "navigation", "requests", "root", "cgi", "gap",
    "collaboration", "frameworks", "containers", "rpc",
    # Single-letter or 2-letter non-skills
    "r", "c", "js", "ts",
    # Overly generic acronyms extracted without context
    "orm", "sdk", "ide", "cli", "cdn", "vm", "os",
}

# Any ITEM whose canonical name is all-lowercase and ≤ 3 chars is almost always noise
_MAX_SHORT_LEN = 3

# Detects a month-name + 4-digit year → used to recognize role-header bullet lines
_ROLE_HEADER_DATE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may"
    r"|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

# ── Section extraction ─────────────────────────────────────────────────────────

def _extract_sections(toon: str) -> dict[str, str]:
    """Return {section_name: body_text} for every SECTION … END_SECTION block."""
    pattern = re.compile(
        r"SECTION\s+(\S+)\s*\n(.*?)END_SECTION\s+\1",
        re.DOTALL,
    )
    return {m.group(1): m.group(2) for m in pattern.finditer(toon)}


# ── SKILLS cleaner ─────────────────────────────────────────────────────────────

def _filter_skills(skills_body: str) -> str:
    """
    Keep only genuine skill items — drop:
      • tokens in _NOISE_TOKENS (case-insensitive)
      • items whose name is all-lowercase AND ≤ _MAX_SHORT_LEN chars
      • items containing ONLY digits
    """
    lines = skills_body.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.upper().startswith("ITEM"):
            kept.append(line)
            continue

        item_value = re.sub(r"^ITEM\s+", "", stripped, flags=re.IGNORECASE).strip()
        lower = item_value.lower()

        # Drop noise
        if lower in _NOISE_TOKENS:
            continue
        # Drop tiny generic tokens (all lowercase, ≤ 3 chars — real skills are
        # capitalised by convention: CSS, SQL, Git, C++, etc.)
        if lower == item_value and len(item_value) <= _MAX_SHORT_LEN:
            continue
        # Drop pure digits
        if item_value.isdigit():
            continue

        kept.append(line)

    return "\n".join(kept)


# ── EMPLOYMENT_HISTORY formatter ───────────────────────────────────────────────

def _format_employment_section(emp_body: str) -> str:
    """
    Reformat the EMPLOYMENT_HISTORY body so each role block is clearly
    separated, readable, and compact:

      • Each new role starts with "Client:" on its own line, preceded by
        two blank lines (except the very first).
      • Bullet lines (starting with •, –, *, or leading whitespace + verb)
        get one leading space for clean indentation.
      • Consecutive blank lines are collapsed to a single blank.
      • Trailing "Tools: ..." tech stack lines are preserved but isolated
        with a blank line above them.
    """
    lines = emp_body.splitlines()
    out: list[str] = []
    first_client = True

    for raw in lines:
        line = raw.rstrip()

        # Normalize typographic dashes → plain hyphen (EN DASH –, EM DASH —)
        line = line.replace("\u2013", "-").replace("\u2014", "-")

        # ── Detect role-header lines ─────────────────────────────────────────
        # Case A: explicit 'Client:' prefix (standard TOON format)
        is_explicit_client = bool(re.match(r"^\s*(?:CONTENT\s+)?Client:", line, re.IGNORECASE))

        # Case B: bullet line where the date appears within the first 80 chars
        # of the content → this is a company/dates header in bullet format
        # (e.g. "• CONTENT  Toyota, Irving TX Apr 2022 - Till Date")
        # Exclude known non-header bullets: Title:, Role:, Environment:, Tools:
        _is_non_header = re.match(
            r"^\s*[•\-*]?\s*(?:CONTENT\s+)?(?:Title|Role|Responsibilities?|Environment|Tools|Tech\s+Stack)\s*:",
            line, re.IGNORECASE
        )
        if not is_explicit_client and not _is_non_header:
            _clean_for_check = re.sub(r"^\s*[•\-*]?\s*(?:CONTENT\s+)?", "", line).strip()
            _dm = _ROLE_HEADER_DATE_RE.search(_clean_for_check)
            is_bullet_client = bool(_dm and _dm.start() < 85)
        else:
            is_bullet_client = False

        is_any_client = is_explicit_client or is_bullet_client

        # Detect a new Client: block (may have CONTENT prefix)
        if is_any_client:
            if not first_client:
                # Two blank lines before every subsequent role
                # (collapse any existing trailing blanks first)
                while out and out[-1] == "":
                    out.pop()
                out.append("")
                out.append("")
            first_client = False
            if is_explicit_client:
                # Normalize: remove CONTENT prefix, keep "Client: ..."
                line = re.sub(r"^\s*CONTENT\s+", "", line, flags=re.IGNORECASE)
                out.append(line)
            else:
                # Bullet-format header → rewrite as "Client: <content>"
                content = re.sub(r"^\s*[•\-*]?\s*(?:CONTENT\s+)?", "", line).strip()
                out.append(f"Client: {content}")

        elif re.match(r"^\s*Role:", line, re.IGNORECASE):
            out.append(line.strip())

        elif re.match(r"^\s*Responsibilities\s*:", line, re.IGNORECASE):
            out.append("")
            out.append("Responsibilities:")

        elif re.match(r"^\s*(?:Tools|Environment|Tech Stack)\s*:", line, re.IGNORECASE):
            # Preserve the tech stack line but separate it with a blank above
            while out and out[-1] == "":
                out.pop()
            out.append("")
            # Wrap long tool lines at ~100 chars
            out.extend(_wrap_tools_line(line.strip()))

        elif line.strip() == "":
            # Collapse multiple blanks - only add one
            if out and out[-1] != "":
                out.append("")

        else:
            # Regular bullet / description line — ensure one-space indent
            text = line.strip()
            if text:
                # Clean bullet characters at the start
                text = re.sub(r"^[•\-–*]\s*", "", text)
                out.append(f"  • {text}")

    # Remove leading/trailing blank lines from result
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    return "\n".join(out)


def _wrap_tools_line(line: str, width: int = 110) -> list[str]:
    """
    Split a long 'Tools: ...' line into multiple lines at commas,
    keeping each line under `width` characters.
    """
    prefix_match = re.match(r"(Tools|Environment|Tech Stack)\s*:\s*", line, re.IGNORECASE)
    if not prefix_match:
        return [line]

    prefix = prefix_match.group(0)
    rest   = line[len(prefix):]
    items  = [x.strip() for x in rest.split(",") if x.strip()]

    result_lines: list[str] = []
    current = prefix
    for item in items:
        candidate = current + item + ", "
        if len(candidate) > width and current != prefix:
            result_lines.append(current.rstrip(", "))
            current = "  " + item + ", "
        else:
            current = candidate
    if current.strip().rstrip(","):
        result_lines.append(current.rstrip(", "))

    return result_lines


# ── SUMMARY truncation ─────────────────────────────────────────────────────────

def _truncate_summary(summary_body: str, max_chars: int = 600) -> str:
    """Keep the first ~5 sentences or max_chars, whichever comes first."""
    text = re.sub(r"^\s*CONTENT\s+", "", summary_body.strip())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = ""
    for s in sentences:
        if len(result) + len(s) > max_chars:
            break
        result += s + " "
    return f"  CONTENT  {result.strip()}\n"


# ── Public API ─────────────────────────────────────────────────────────────────

def preprocess_toon_for_llm(toon_script: str) -> str:
    """
    Take a full TOON script and return a cleaned, neatly formatted version
    ready to send to the LLM.
    """
    sections = _extract_sections(toon_script)
    output_lines = ["TOON_VERSION  1.0", ""]

    for name, body in sections.items():

        # 1) Drop sections that should never go to LLM
        if name in _DROP_SECTIONS:
            continue

        body_stripped = body.strip()

        # 2) Drop empty sections
        if name in _DROP_IF_EMPTY and body_stripped in ("EMPTY", ""):
            continue

        # 3) Format EMPLOYMENT_HISTORY for readability
        if name == "EMPLOYMENT_HISTORY":
            body = _format_employment_section(body)

        # 4) Filter SKILLS noise
        elif name == "SKILLS":
            body = _filter_skills(body)
            if not re.search(r"ITEM\s+\S", body):
                continue

        # 5) Truncate SUMMARY
        elif name == "SUMMARY" and body_stripped not in ("EMPTY", ""):
            body = _truncate_summary(body)

        # Emit cleaned section
        output_lines.append(f"SECTION  {name}")
        output_lines.append(body.rstrip())
        output_lines.append(f"END_SECTION  {name}")
        output_lines.append("")

    return "\n".join(output_lines)


def preprocess_toon_file(toon_path: str) -> tuple[str, int, int]:
    """
    Read a .toon file, pre-process it, and return:
      (cleaned_toon_str, original_line_count, cleaned_line_count)
    """
    with open(toon_path, encoding="utf-8") as f:
        original = f.read()

    cleaned = preprocess_toon_for_llm(original)
    return cleaned, original.count("\n"), cleaned.count("\n")
