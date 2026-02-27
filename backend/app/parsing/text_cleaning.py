import re
from typing import Tuple, Dict, Optional

def normalize_text_lossless(text: str) -> str:
    """
    1) LOSSLESS normalize:
       - replace \\r\\n with \\n
       - replace \\r with \\n
       - trim trailing spaces per line
       - collapse repeated spaces/tabs INSIDE lines (do not remove newlines)
       - do NOT delete lines
    """
    if not text:
        return ""
        
    # Standardize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    lines = text.split("\n")
    normalized_lines = []
    
    for line in lines:
        # Trim trailing spaces
        line = line.rstrip()
        # Collapse internal spaces (tabs/spaces) -> single space
        # But preserve leading indentation? The prompt says "collapse repeated spaces/tabs INSIDE lines"
        # Usually this means ' '.join(line.split()) but that removes leading/trailing.
        # "do not remove newlines" implies structure preservation. 
        # Let's assume standard "squeeze whitespace" but keep newlines.
        # Safe approach: regex sub for internal whitespace
        # But honestly, ' '.join(line.split()) is mostly what's wanted for extracting info, 
        # though it loses indentation.
        # Resume parsers usually like indentation (for sections).
        # "collapse repeated spaces/tabs INSIDE lines" -> maybe means `re.sub(r'[ \t]+', ' ', line)`
        
        # Let's use regex to collapse ANY run of horizontal whitespace to a single space
        line = re.sub(r'[ \t]+', ' ', line)
        normalized_lines.append(line)
        
    return "\n".join(normalized_lines)


def zone_resume_text(text: str) -> Tuple[str, str, str]:
    """
    Splits text into (body, trailer, email_wrapper).
    
    Primary split marker: "-----END OF RESUME-----"
    Secondary split marker: "----- START OF EMAIL -----"
    """
    if not text:
        return "", "", ""
        
    # Defaults
    body = text
    trailer = ""
    email_wrapper = ""
    
    # 1. Check for Trailer
    trailer_marker = "-----END OF RESUME-----"
    if trailer_marker in text:
        parts = text.split(trailer_marker, 1)
        body = parts[0]
        # The trailer is AFTER the marker. The marker itself is usually discardable or part of the boundary.
        # User says: "resume_trailer_text = text after marker"
        trailer = parts[1]
    
    # 2. Check for Email Wrapper (in body? or in general? 
    # "If found, treat everything AFTER it as email_wrapper_text and exclude from skills extraction."
    # This implies it might be in the 'body' part if trailer wasn't found, OR it overrides trailer/body logic?
    # Usually email wrapper is at the very end or surrounding the resume. 
    # Let's check 'body' for it, since 'trailer' is already separate (metadata).
    # If the marker matches, we split 'body' further.
    
    email_marker = "----- START OF EMAIL -----"
    if email_marker in body:
        parts = body.split(email_marker, 1)
        body = parts[0]
        email_wrapper = parts[1]
        
    # Also check trailer? Usually trailer is metadata appended by the system. 
    # Email wrapper might be artifacts from email processing.
    # We'll assume email marker is in the main text block.
    
    return body, trailer, email_wrapper


def parse_trailer_key_values(trailer_text: str) -> Dict[str, str]:
    """
    Trailer KV parse (strict):
    Extract fields only if line matches "^Key:\s*(.+)$" for these keys:
    Name, Email, Phone, Address, Work Authorization, Job Ref #
    """
    data = {}
    if not trailer_text:
        return data
        
    # Allow loose matching on keys? Prompt says "strict"
    # Keys: Name, Email, Phone, Address, Work Authorization, Job Ref #
    target_keys = {
        "Name", "Email", "Phone", "Address", "Work Authorization", "Job Ref #"
    }
    
    lines = trailer_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Regex: Start of line, Key, Colon, Whitespace, Value, End
        # We need to match specific keys.
        # Let's iterate keys or use a generic regex and check key validity.
        
        # Generic: ^([^:]+):\s*(.+)$
        m = re.match(r"^([^:]+):\s*(.+)$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            
            if key in target_keys:
                # Store normalized key or raw? Map to schema fields?
                # User says: "Store these into candidate_profile.contact with highest priority"
                # We'll return a dict and map later.
                data[key] = val
                
    return data
