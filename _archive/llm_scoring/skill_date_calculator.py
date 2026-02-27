"""
skill_date_calculator.py
────────────────────────
Parses employment history from a TOON script and computes, in pure Python,
the temporal metrics for every skill listed in the SKILLS section:

  • years_total     – sum of all role durations where the skill was used
  • years_recent_3  – overlap with the 3-year window ending TODAY
  • last_used_date  – ISO date string of latest role end date for that skill
  • recency_weight  – EXP(-0.2 * (current_year - last_used_year))

Result is a dict keyed by canonical skill name:
  {
    "Oracle BI Publisher": {
        "years_total":    6.0,
        "years_recent_3": 2.42,
        "last_used_date": "2026-01-01",
        "recency_weight": 1.0,
    },
    ...
  }

No external dependencies required beyond the standard library.
"""

import re
import math
from datetime import date
from typing import Optional


# ── Month lookup ───────────────────────────────────────────────────────────────

_MONTH_MAP: dict[str, int] = {
    "jan": 1,  "january": 1,
    "feb": 2,  "february": 2,
    "mar": 3,  "march": 3,
    "apr": 4,  "april": 4,
    "may": 5,
    "jun": 6,  "june": 6,
    "jul": 7,  "july": 7,
    "aug": 8,  "august": 8,
    "sep": 9,  "sept": 9,  "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Matches month-name (with optional no-space) then 4-digit year
# e.g.  "June2019", "Sept 2021", "April  2024", "Jan-2026"
_DATE_RE = re.compile(
    r"(?i)\b"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may"
    r"|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"[\s\-]*((?:19|20)\d{2})\b"
)

# "Till Date", "Present", "Current", "Now", "Ongoing"
_PRESENT_RE = re.compile(
    r"\b(?:till\s*date|present|current|to\s*date|ongoing|now|till\s*now)\b",
    re.IGNORECASE,
)

# Brand/platform prefixes to strip when doing secondary skill matching
_BRAND_PREFIXES = {
    "oracle", "apache", "spring", "aws", "azure", "google",
    "ibm", "microsoft", "openai", "amazon", "confluent",
}


def _normalise(text: str) -> str:
    """
    Produce a normalised form of a skill name / role text for fuzzy matching:
      • lowercase
      • collapse all whitespace to a single space
      • remove non-alphanumeric separators (dots, slashes, hyphens)
      • strip plural 's' from the end (REST APIs → rest api)
    """
    t = text.lower()
    # Remove dots, slashes, hyphens used as separators
    t = re.sub(r"[./\\-]", " ", t)
    # Collapse multiple spaces
    t = re.sub(r"\s+", " ", t).strip()
    # Strip trailing plural 's' if the word is > 3 chars  (apis→api, services→service)
    t = re.sub(r"(?<=\w{3})s\b", "", t)
    return t


# ── Internal data structure ────────────────────────────────────────────────────

class _Period:
    """One employment role with resolved start/end dates."""
    __slots__ = ("client", "start", "end", "text_lower")

    def __init__(self, client: str, start: date, end: date, text: str):
        self.client     = client
        self.start      = start
        self.end        = end
        self.text_lower = text.lower()

    def duration_months(self) -> float:
        return max(0.0, float(
            (self.end.year - self.start.year) * 12
            + (self.end.month - self.start.month)
        ))


# ── Date helpers ───────────────────────────────────────────────────────────────

def _fix_nospace(text: str) -> str:
    """Insert a space between a letter and a digit: 'June2019' → 'June 2019'."""
    return re.sub(r"([a-zA-Z])(\d)", r"\1 \2", text)


def _parse_my(month_str: str, year_str: str) -> Optional[date]:
    """Parse a (month_name, year_string) pair into date(year, month, 1)."""
    month = _MONTH_MAP.get(month_str.lower().strip())
    if not month:
        return None
    try:
        return date(int(year_str), month, 1)
    except (ValueError, TypeError):
        return None


def _extract_date_range(text: str, today: date) -> tuple[Optional[date], Optional[date]]:
    """
    Return (start, end) from a block of text.
    'end' is today if the text contains a "present"-style word.
    Returns (None, None) if no dates found.
    """
    normalised = _fix_nospace(text)
    hits = []
    for m in _DATE_RE.finditer(normalised):
        d = _parse_my(m.group(1), m.group(2))
        if d:
            hits.append((m.start(), d))

    has_present = bool(_PRESENT_RE.search(normalised))

    if not hits:
        return (None, None)

    hits.sort(key=lambda x: x[0])

    if len(hits) == 1:
        start = hits[0][1]
        end   = today if has_present else None
        return (start, end)

    start = hits[0][1]
    end   = today if has_present else hits[-1][1]
    return (start, end)


def _months_overlap(s1: date, e1: date, s2: date, e2: date) -> float:
    """Months of overlap between [s1,e1) and [s2,e2)."""
    lo = max(s1, s2)
    hi = min(e1, e2)
    if hi <= lo:
        return 0.0
    return max(0.0, float((hi.year - lo.year) * 12 + (hi.month - lo.month)))


# ── TOON parsing ───────────────────────────────────────────────────────────────

def _extract_section(toon: str, name: str) -> str:
    """Return the body text of a named TOON section, or ''."""
    m = re.search(
        rf"SECTION\s+{re.escape(name)}\s*\n(.*?)END_SECTION\s+{re.escape(name)}",
        toon, re.DOTALL,
    )
    return m.group(1) if m else ""


def _parse_employment_periods(toon: str, today: date) -> list[_Period]:
    """
    Split EMPLOYMENT_HISTORY into one _Period per 'Client:' block
    and resolve their start/end dates.
    """
    emp_text = _extract_section(toon, "EMPLOYMENT_HISTORY")
    if not emp_text:
        return []

    # Split on lines that begin a new "Client:" block (with optional CONTENT prefix)
    blocks = re.split(
        r"\n(?=\s*(?:CONTENT\s+)?Client:)",
        emp_text,
        flags=re.IGNORECASE,
    )

    periods: list[_Period] = []
    for raw_block in blocks:
        block = raw_block.strip()
        if not block:
            continue

        # Strip leading "CONTENT  " artefact
        block = re.sub(r"^\s*CONTENT\s+", "", block, flags=re.IGNORECASE)

        # Client name from first line
        first_line = block.split("\n")[0]
        cm = re.match(r"Client:\s*(.+)", first_line, re.IGNORECASE)
        client = cm.group(1).strip() if cm else first_line

        # Try dates from first 5 lines only (avoids false hits in description)
        header = "\n".join(block.split("\n")[:5])
        start, end = _extract_date_range(header, today)

        # Fall back to whole block if header had no dates
        if start is None:
            start, end = _extract_date_range(block, today)

        if start is None:
            continue                    # cannot determine dates → skip

        if end is None:
            end = today                 # open-ended roles default to today

        # Sanity: end must be >= start
        if end < start:
            end = today

        periods.append(_Period(client=client, start=start, end=end, text=block))

    return periods



# Noise words to exclude when extracting skills from Tools: lines
_TOOLS_NOISE = {
    "windows", "windows10", "eclipse", "intellij", "webstorm", "putty",
    "confluence", "jira", "crucible", "sourcetree", "udeploy", "xldeploy",
    "sdp", "bitbucket", "stash", "jprofiler", "ehcache", "openshift",
    "agile", "scrum", "tdd", "oop", "j2ee", "jvm", "ooa", "ood",
    "concurrent", "package", "lambda", "expressions", "streams",
    "dom", "sax", "xpath", "stax", "xslt",  # extracted individually via XSLT item
}


def _extract_skills_from_tools_lines(emp_body: str) -> list[str]:
    """
    Extract skill tokens from 'Tools: ...' or 'Environment: ...' lines
    inside the EMPLOYMENT_HISTORY block.
    These are curated by the candidate and capture skills missing from SKILLS section.
    """
    found: list[str] = []
    seen: set[str] = set()

    for line in emp_body.splitlines():
        stripped = line.strip()
        m = re.match(r"(?:Tools|Environment|Tech\s*Stack)\s*:\s*(.*)", stripped, re.IGNORECASE)
        if not m:
            continue

        tokens = [t.strip() for t in m.group(1).split(",") if t.strip()]
        for tok in tokens:
            # Clean up parenthetical remarks like "XML (Dom, Sax, ...)"
            tok = re.sub(r"\(.*?\)", "", tok).strip()
            tok = re.sub(r"\s{2,}", " ", tok).strip()
            if not tok or len(tok) < 2:
                continue

            tok_lower = tok.lower()
            if tok_lower in _TOOLS_NOISE:
                continue
            # Skip version numbers like "Java 8/17" → keep "Java"
            tok_clean = re.sub(r"\s*[\d./]+\s*$", "", tok).strip()
            if not tok_clean or len(tok_clean) < 2:
                continue

            key = tok_clean.lower()
            if key not in seen:
                seen.add(key)
                found.append(tok_clean)

    return found


def _extract_skills(toon: str) -> list[str]:
    """
    Return deduplicated skill names from:
      1. SKILLS section ITEM lines (primary source)
      2. Tools:/Environment: lines in EMPLOYMENT_HISTORY (fills gaps like Hibernate)
    """
    # Primary: SKILLS section
    body = _extract_section(toon, "SKILLS")
    from_skills_section: list[str] = []
    seen: set[str] = set()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("ITEM"):
            skill = re.sub(r"^ITEM\s+", "", stripped, flags=re.IGNORECASE).strip()
            if skill and skill.lower() not in seen:
                seen.add(skill.lower())
                from_skills_section.append(skill)

    # Secondary: Tools: lines in EMPLOYMENT_HISTORY
    emp_body = _extract_section(toon, "EMPLOYMENT_HISTORY")
    from_tools: list[str] = []
    for skill in _extract_skills_from_tools_lines(emp_body):
        if skill.lower() not in seen:
            seen.add(skill.lower())
            from_tools.append(skill)

    return from_skills_section + from_tools




def _skill_in_period(skill: str, period: _Period) -> bool:
    """
    Return True if this skill is evidenced in the period's description.

    Matching strategy (in order):
      1. Exact lowercase substring match.
      2. Normalised match — collapse whitespace, strip dots/hyphens, strip
         plural 's' — so "MongoDB" matches "Mongo DB", "REST APIs" matches
         "REST API", "Node Js" matches "Node.js".
      3. Brand-prefix stripped match — "Oracle BI Publisher" → "BI Publisher".
      4. Brand-prefix + normalised match.
    """
    # Strategy 1 — exact
    key = skill.lower()
    if key in period.text_lower:
        return True

    # Strategy 2 — normalised
    norm_skill  = _normalise(skill)
    norm_period = _normalise(period.text_lower)  # normalise once per check
    if norm_skill and norm_skill in norm_period:
        return True

    # Strategy 3 — drop brand prefix
    parts = key.split()
    if len(parts) > 1 and parts[0] in _BRAND_PREFIXES:
        alt = " ".join(parts[1:])
        if alt in period.text_lower:
            return True
        # Strategy 4 — brand-stripped + normalised
        if _normalise(alt) in norm_period:
            return True

    return False


# ── Public API ─────────────────────────────────────────────────────────────────

MAX_SKILLS_PER_PROFILE = 15   # cap sent to LLM

def compute_all_skill_metrics(
    toon_script: str,
    today: Optional[date] = None,
) -> dict[str, dict]:
    """
    Main entry point. Returns a dict keyed by skill name:

      {
        "BI Publisher": {
            "years_total":    6.0,
            "years_recent_3": 2.42,
            "last_used_date": "2026-01-01",
            "recency_weight": 1.0,
        },
        ...
      }
    """
    if today is None:
        today = date.today()

    three_yr_start = date(today.year - 3, today.month, today.day)

    periods = _parse_employment_periods(toon_script, today)
    skills  = _extract_skills(toon_script)

    result: dict[str, dict] = {}

    for skill in skills:
        matched = [p for p in periods if _skill_in_period(skill, p)]

        if not matched:
            result[skill] = {
                "years_total":    0.0,
                "years_recent_3": 0.0,
                "last_used_date": None,
                "recency_weight": 0.0,
            }
            continue

        # years_total – sum of all matched role durations
        total_months  = sum(p.duration_months() for p in matched)
        years_total   = round(total_months / 12.0, 2)

        # years_recent_3 – overlap with 3-year window
        recent_months = sum(
            _months_overlap(p.start, p.end, three_yr_start, today)
            for p in matched
        )
        years_recent_3 = round(recent_months / 12.0, 2)

        # last_used_date – latest end date among matched roles
        last_used = max(p.end for p in matched)

        # recency_weight – EXP(-0.2 * year_gap)
        year_gap       = today.year - last_used.year
        recency_weight = round(math.exp(-0.2 * year_gap), 4)

        result[skill] = {
            "years_total":    years_total,
            "years_recent_3": years_recent_3,
            "last_used_date": last_used.isoformat(),
            "recency_weight": recency_weight,
        }

    return result


def format_metrics_table(metrics: dict[str, dict]) -> str:
    """
    Return a human-readable table of pre-computed metrics for injection
    into the LLM prompt.
    """
    if not metrics:
        return "(no skills found)"

    lines = [
        "SKILL                                    | YRS_TOTAL | YRS_RECENT_3 | LAST_USED  | RECENCY_WT",
        "-" * 95,
    ]
    for skill, m in metrics.items():
        last = m["last_used_date"] or "unknown"
        lines.append(
            f"{skill:<40} | {m['years_total']:9.2f} | {m['years_recent_3']:12.2f}"
            f" | {last} | {m['recency_weight']:.4f}"
        )
    return "\n".join(lines)


def filter_top_skills(
    metrics: dict[str, dict],
    max_skills: int = MAX_SKILLS_PER_PROFILE,
) -> dict[str, dict]:
    """
    From the full metrics dict, return only the top `max_skills` entries.

    Filtering rules (applied in order):
      1. Drop any skill with years_total == 0  (no employment evidence at all)
      2. Rank remaining skills by:
            signal = years_total * 0.4 + years_recent_3 * 0.6
         (heavier weight on recency — more relevant for JD matching)
      3. Return the top `max_skills` by signal score.
    """
    evidenced = {
        skill: m for skill, m in metrics.items()
        if m["years_total"] > 0.0
    }

    ranked = sorted(
        evidenced.items(),
        key=lambda kv: kv[1]["years_total"] * 0.4 + kv[1]["years_recent_3"] * 0.6,
        reverse=True,
    )

    return dict(ranked[:max_skills])

