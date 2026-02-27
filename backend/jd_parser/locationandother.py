import re
import html
from bs4 import BeautifulSoup


# --------------------------------------------------
# TEXT CLEANER
# --------------------------------------------------

def clean_html(text):
    if not text:
        return None
    text = html.unescape(text)
    soup = BeautifulSoup(text, "html.parser")
    return re.sub(r'\s+', ' ', soup.get_text(" ", strip=True))


# --------------------------------------------------
# FLEXIBLE FIELD PICKER
# --------------------------------------------------

def pick(job, *keys):
    for k in keys:
        if k in job and job[k] not in [None, "", 0]:
            return job[k]
        if k.upper() in job and job[k.upper()] not in [None, "", 0]:
            return job[k.upper()]
        if k.lower() in job and job[k.lower()] not in [None, "", 0]:
            return job[k.lower()]
    return None


# --------------------------------------------------
# LOCATION EXTRACTION
# --------------------------------------------------

CITY_STATE = re.compile(r'\b([A-Z][a-zA-Z ]+),\s*([A-Z]{2})\b')
REMOTE = re.compile(r'(remote|hybrid|onsite)', re.I)
REMOTE_PERCENT = re.compile(r'(\d{1,3})\s*%\s*remote', re.I)


def extract_location(description, job):
    location = {
        "city": pick(job, "city", "POSTING_CITY"),
        "state": pick(job, "state", "POSTING_STATE"),
        "country": pick(job, "country", "POSTING_COUNTRY"),
        "postal_code": pick(job, "zipcode", "POSTING_ZIPCODE")
    }

    location = {k: v for k, v in location.items() if v}

    if location:
        return location

    if not description:
        return None

    match = CITY_STATE.search(description)
    if match:
        return {"city": match.group(1), "state": match.group(2)}

    return None


# --------------------------------------------------
# RATE + TYPE EXTRACTION FROM TEXT
# --------------------------------------------------

def extract_remote_info(text):
    if not text:
        return None, None

    mode = None
    percent = None

    if re.search(r'\bremote\b', text, re.I):
        mode = "remote"
    elif re.search(r'\bhybrid\b', text, re.I):
        mode = "hybrid"
    elif re.search(r'\bonsite\b', text, re.I):
        mode = "onsite"

    m = REMOTE_PERCENT.search(text)
    if m:
        percent = int(m.group(1))

    return mode, percent


def extract_positions(text):
    if not text:
        return None
    m = re.search(r'(\d+)\s+positions?', text, re.I)
    return int(m.group(1)) if m else None


def extract_position_type(text):
    if not text:
        return None

    if re.search(r'\bcontract\b', text, re.I):
        return "contract"
    if re.search(r'\bfull[- ]?time\b', text, re.I):
        return "full_time"
    if re.search(r'\bw2\b', text, re.I):
        return "w2"
    if re.search(r'\bc2c\b', text, re.I):
        return "c2c"

    return None


# --------------------------------------------------
# MAIN CLEAN FUNCTION
# --------------------------------------------------

def clean_job(job: dict):

    description_raw = pick(job,
        "posting description",
        "postingdescription",
        "job description",
        "jobdescription"
    )

    # -------- NEW: Recruiter Remarks Raw --------
    recruiter_remarks_raw = pick(job,
        "recruiter remarks",
        "recruiterremarks",
        "remarks",
        "internal notes",
        "recruiter notes",
        "RECRUITERREMARKS"
    )

    description = clean_html(description_raw)
    recruiter_remarks = clean_html(recruiter_remarks_raw)

    onsite_mode, remote_percent = extract_remote_info(description)

    cleaned = {
        "job_id": str(pick(job, "id", "ID", "JOBDIVANO")),

        "company": pick(job, "company", "COMPANYNAME"),
        "job_title": pick(job, "job title", "JOBTITLE"),

        "location": extract_location(description, job),

        "jobdiva_number": pick(job, "JOBDIVANO", "reference #"),

        "positions": pick(job, "positions", "POSITIONS") or extract_positions(description),

        "bill_rate": {
            "min": pick(job, "minimum bill rate", "BILLRATEMIN"),
            "max": pick(job, "maximum bill rate", "BILLRATEMAX"),
            "period": pick(job, "bill rate per", "BILLRATEPER"),
        },

        "pay_rate": {
            "min": pick(job, "minimum rate", "PAYRATEMIN"),
            "max": pick(job, "maximum rate", "PAYRATEMAX"),
            "period": pick(job, "rate per", "PAYRATEPER"),
        },

        "position_type": pick(job, "job type", "POSITIONTYPE") or extract_position_type(description),

        "onsite_flexibility": onsite_mode,
        "remote_percentage": remote_percent,

        "description": description,

        # -------- NEW EMPTY FIELD --------
        "recruiter_remarks": ""
    }

    return cleaned