import re
from typing import Dict, Any, List

SECTION_HEADERS = {
    "summary": [
        "SUMMARY", "PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY",
        "PROFILE", "PROFESSIONAL PROFILE", "CAREER OVERVIEW",
        "CAREER OVERIVEW",  # common typo seen in resumes
        "OBJECTIVE",
    ],
    "skills": [
        "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES",
        "AREAS OF EXPERTISE", "KEY SKILLS", "ADMINISTRATIVE SKILLS",
    ],
    "employment_history": [
        "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE",
        "EMPLOYMENT HISTORY", "CAREER HISTORY", "WORK HISTORY",
        "PROFESSIONAL BACKGROUND", "EMPLOYMENT", "PROFESSIONAL EXPERIENCE:",
        "CAREER EXPERIENCE",
    ],
    "education": [
        "EDUCATION", "ACADEMIC BACKGROUND", "ACADEMIC QUALIFICATIONS",
        "EDUCATION/TRAINING", "EDUCATION AND TRAINING", "TRAINING",
        "ACADEMIC CREDENTIALS",
    ],
    "certifications": [
        "CERTIFICATES", "CERTIFICATE", "CERTIFICATIONS", "LICENSES & CERTIFICATIONS",
        "LICENSES AND CERTIFICATIONS"
    ],
    "projects": ["PROJECTS", "KEY PROJECTS", "PROJECT EXPERIENCE"],
}

def extract_seniority_level(text: str) -> str | None:
    import re
    head = "\n".join(text.splitlines()[:5])
    patterns = [
        (re.compile(r"\b(sr\.?|senior)\b", re.I), "senior"),
        (re.compile(r"\b(jr\.?|junior)\b", re.I), "junior"),
        (re.compile(r"\blead\b", re.I), "lead"),
        (re.compile(r"\bprincipal\b", re.I), "principal"),
        (re.compile(r"\bstaff\b", re.I), "staff"),
    ]
    for rx, label in patterns:
        if rx.search(head):
            return label
    return None

def extract_sections(text: str) -> Dict[str, Any]:
    """
    Extracts sections from resume text using regex patterns for headers.
    """
    lines = text.split('\n')
    sections: Dict[str, Any] = {
        "source": {}, "contact": {}, "work_authorization": {}, "compensation_preferences": {},
        "role_preferences": {}, "summary": {}, "skills": {}, "employment_history": {},
        "projects": {}, "education": {}, "publications_and_patents": {},
        "awards_and_leadership": {}, "seniority_and_scope": {}, "employment_recency": {},
        "stability_and_tenure": {}, "raw_extraction": {"text": text}
    }

    # Extract Seniority
    seniority = extract_seniority_level(text)
    sections["seniority_and_scope"] = {"seniority_level": seniority}

    # Identify section start indices
    section_starts = []
    
    # Simple heuristic: Look for lines that match headers broadly
    # We'll use a map to tracking which standard section matches to which line index
    
    for i, line in enumerate(lines):
        line_clean = line.strip().upper()
        # Remove common delimiters at end like ':'
        line_clean = line_clean.strip(":- ")
        
        if not line_clean or len(line_clean) > 40: # Resume headers are usually short
            continue
            
        found_section = None
        for sec_key, headers in SECTION_HEADERS.items():
            if line_clean in headers:
                found_section = sec_key
                break
        
        if found_section:
            section_starts.append((i, found_section))

    # Sort by line number
    section_starts.sort(key=lambda x: x[0])
    
    # Extract text between sections
    for i in range(len(section_starts)):
        start_idx, sec_key = section_starts[i]
        
        # End is start of next section or end of doc
        if i < len(section_starts) - 1:
            end_idx = section_starts[i+1][0]
        else:
            end_idx = len(lines)
            
        # Extract lines, skip the header line itself
        content_lines = lines[start_idx+1:end_idx]
        content_text = "\n".join(content_lines).strip()
        
        if content_text:
            sections[sec_key] = {"content": content_text}

    return sections
