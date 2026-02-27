import re
import phonenumbers
from typing import Dict, Optional, Tuple

def extract_contact_info(text: str) -> Dict[str, Optional[str]]:
    """
    Extracts contact info from raw text.
    Returns dict with keys: full_name, phone_raw, phone_e164, github, linkedin, location
    """
    info = {
        "full_name": None,
        "phone_raw": None,
        "phone_e164": None,
        "github": None,
        "linkedin": None,
        "location": None
    }
    
    if not text:
        return info

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 1. Name Strategy: First non-empty line usually (or check "Name:" prefix)
    # Simple heuristic: First line that doesn't look like a contact detail or header
    for line in lines[:5]:
        if "name" in line.lower() and ":" in line:
            info["full_name"] = line.split(":", 1)[1].strip()
            break
        if len(line.split()) < 5: # Assume name is short
             # Avoid lines that are just email or phone
            if "@" not in line and not any(c.isdigit() for c in line):
                 if not info["full_name"]: info["full_name"] = line

    # 2. Phone
    # Use phonenumbers to find matches
    try:
        # We assume US/Default region if not parseable, but let's try generic
        # iterating matches
        for match in phonenumbers.PhoneNumberMatcher(text, "US"): # Default to US for parsing logic if ambiguous
            p = match.number
            info["phone_raw"] = match.raw_string
            info["phone_e164"] = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
            break # Take first found
    except Exception:
        pass

    # 3. GitHub
    # github.com/<handle>
    github_match = re.search(r"github\.com/([a-zA-Z0-9-]+)", text, re.IGNORECASE)
    if github_match:
        info["github"] = github_match.group(0) # Store full url or handle? instructions say "regex github.com/<handle>" -> let's store the matched string

    # 4. LinkedIn
    # linkedin.com/in/<handle> or /pub/
    linkedin_match = re.search(r"linkedin\.com/(in|pub)/([a-zA-Z0-9-%]+)", text, re.IGNORECASE)
    if linkedin_match:
        info["linkedin"] = linkedin_match.group(0)

    # 5. Location (improved)
    US_STATES = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
                 "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD",
                 "TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"}

    COUNTRIES = {"usa","united states","canada","india","uk","united kingdom","australia","uae","singapore"}

    # Regex for finding City, State Zip or City, Country
    # Added support for "." as separator (e.g. "Dallas. TX")
    CITY_STATE_COUNTRY = re.compile(r"([A-Z][a-zA-Z\.\s]+)[,\.]\s*([A-Z]{2}|[A-Z][a-zA-Z]+)")

    US_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
    CA_POSTAL = re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d\b", re.I)

    # TITLE WORDS to reject
    TITLE_WORDS = {
        "developer","engineer","architect","analyst","manager","consultant","specialist",
        "administrator","designer","full stack","backend","frontend","software",
        "java developer","software engineer"
    }

    def looks_like_title(line: str) -> bool:
        s = line.lower()
        if any(w in s for w in TITLE_WORDS):
            return True
        # many TitleCase words often means title/header
        tc = sum(1 for w in line.split() if w[:1].isupper())
        return tc >= 4 and len(line.split()) >= 4

    best_loc = None
    best_score = -999

    for line in lines[:12]:
        # extracted separately. We shouldn't skip the whole line just because it has an email
        # if the location is on the same line (e.g. "City, State | email@domain.com")
        if "github" in line.lower() or "linkedin" in line.lower():
            continue
        if info.get("full_name") and line.strip() == info["full_name"].strip():
            continue

        if looks_like_title(line):
             # STRICT REJECTION
             continue

        score = 0

        # Try regex
        m = CITY_STATE_COUNTRY.search(line)
        valid_region = False
        
        if m:
            city = m.group(1).strip()
            region = m.group(2).strip()
            
            if region.upper() in US_STATES:
                score += 3
                valid_region = True
            elif region.lower() in COUNTRIES:
                score += 3
                valid_region = True
                
            if valid_region:
                # Prefer shorter clean matches
                if len(line) <= 50:
                    score += 1
                
                if score > best_score:
                    best_score = score
                    best_loc = f"{city}, {region}"

        # Check for ZIP codes - can boost or be primary if line is short
        zip_matches = list(US_ZIP.finditer(line)) + list(CA_POSTAL.finditer(line))
        if zip_matches:
            # If line has pipes, split and check segments
            segments = re.split(r'[|•]', line)
            for seg in segments:
                seg = seg.strip()
                if US_ZIP.search(seg) or CA_POSTAL.search(seg):
                    local_score = 0
                    
                    # If it also looks like a title, reject segment
                    if looks_like_title(seg): 
                        continue
                        
                    if CITY_STATE_COUNTRY.search(seg):
                         # If we have City, St in this segment, verify region
                         m_seg = CITY_STATE_COUNTRY.search(seg)
                         r_seg = m_seg.group(2).strip()
                         if r_seg.upper() in US_STATES or r_seg.lower() in COUNTRIES:
                             local_score += 5
                         else:
                             # ZIP but invalid state? Maybe just zip
                             local_score += 2
                    else:
                        local_score += 2 # Just zip

                    if len(seg) < 50:
                        if local_score > best_score:
                             best_score = local_score
                             best_loc = seg
                    break 

    # threshold: require evidence (score >= 2 means at least valid region match OR zip)
    info["location"] = best_loc if best_score >= 2 else None
            
    return info
