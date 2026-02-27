"""
jd_to_toon.py
─────────────
Converts a cleaned JD dictionary into a standard TOON_JOB script format.
"""


from app.parsing.text_cleaning import normalize_text_lossless

def _val(value):
    if value is None or str(value).strip() == "":
        return "None"
    return str(value).strip()

def _multi_line(value):
    if not value or str(value).strip() == "":
        return ""
    # Inherit existing behavior: use the normalizer
    norm = normalize_text_lossless(str(value))
    
    # Indent every line by 8 spaces to fit under DESCRIPTION/REMARKS
    lines = norm.strip().split('\n')
    indented = [f"        {line}" for line in lines if line.strip()]
    return "\n".join(indented)

def jd_to_toon(jd_dict: dict) -> str:
    """
    Format a cleaned JD dictionary into the strict TOON_JOB hierarchical string layout.
    """
    
    loc = jd_dict.get("location") or {}
    bill = jd_dict.get("bill_rate") or {}
    pay = jd_dict.get("pay_rate") or {}
    
    lines = [
        "TOON_JOB",
        f"    ID: {_val(jd_dict.get('job_id'))}",
        f"    COMPANY: {_val(jd_dict.get('company'))}",
        f"    TITLE: {_val(jd_dict.get('job_title'))}",
        "    LOCATION:"
    ]
    
    if not loc:
        lines.extend([
            "        CITY: None",
            "        STATE: None",
            "        COUNTRY: None",
            "        POSTAL_CODE: None"
        ])
    else:
        lines.extend([
            f"        CITY: {_val(loc.get('city'))}",
            f"        STATE: {_val(loc.get('state'))}",
            f"        COUNTRY: {_val(loc.get('country'))}",
            f"        POSTAL_CODE: {_val(loc.get('postal_code'))}"
        ])
        
    lines.extend([
        f"    JOBDIVA_NUMBER: {_val(jd_dict.get('jobdiva_number'))}",
        f"    POSITIONS: {_val(jd_dict.get('positions'))}",
        "    BILL_RATE:",
        f"        MIN: {_val(bill.get('min'))}",
        f"        MAX: {_val(bill.get('max'))}",
        f"        PERIOD: {_val(bill.get('period'))}",
        "    PAY_RATE:",
        f"        MIN: {_val(pay.get('min'))}",
        f"        MAX: {_val(pay.get('max'))}",
        f"        PERIOD: {_val(pay.get('period'))}",
        f"    POSITION_TYPE: {_val(jd_dict.get('position_type'))}",
        f"    ONSITE_FLEXIBILITY: {_val(jd_dict.get('onsite_flexibility'))}",
        f"    REMOTE_PERCENTAGE: {_val(jd_dict.get('remote_percentage'))}",
        "    DESCRIPTION: |"
    ])
    
    desc = _multi_line(jd_dict.get('description'))
    if desc:
        lines.append(desc)
    else:
        lines.append("")
        
    lines.append("    RECRUITER_REMARKS: |")
    
    rem = _multi_line(jd_dict.get('recruiter_remarks'))
    if rem:
        lines.append(rem)
    else:
        lines.append("")
        
    return "\n".join(lines)

