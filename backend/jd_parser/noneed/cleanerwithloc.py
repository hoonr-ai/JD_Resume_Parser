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
    text = soup.get_text(" ", strip=True)
    return re.sub(r'\s+', ' ', text)


# --------------------------------------------------
# PICK FIELD (handles both schemas)
# --------------------------------------------------

def pick(job, *keys):
    for k in keys:
        if k in job and job[k]:
            return job[k]
        if k.upper() in job and job[k.upper()]:
            return job[k.upper()]
        if k.lower() in job and job[k.lower()]:
            return job[k.lower()]
    return None


# --------------------------------------------------
# LOCATION EXTRACTION FROM TEXT
# --------------------------------------------------

CITY_STATE_RE = re.compile(
    r'\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*),\s*([A-Z]{2})\b'
)

ZIP_RE = re.compile(r'\b\d{5}(?:-\d{4})?\b')


def extract_location_from_text(text):
    if not text:
        return None

    match = CITY_STATE_RE.search(text)
    zip_match = ZIP_RE.search(text)

    location = {}

    if match:
        location["city"] = match.group(1)
        location["state"] = match.group(2)

    if zip_match:
        location["postal_code"] = zip_match.group(0)

    return location if location else None


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

    description = clean_html(description_raw)

    # ---- structured location first ----
    location = {
        "city": pick(job, "city", "POSTING_CITY"),
        "state": pick(job, "state", "POSTING_STATE"),
        "country": pick(job, "country", "POSTING_COUNTRY"),
        "postal_code": pick(job, "zipcode", "POSTING_ZIPCODE"),
    }

    # remove empty
    location = {k: v for k, v in location.items() if v}

    # ---- fallback to description ----
    if not location:
        text_loc = extract_location_from_text(description)
        if text_loc:
            location = text_loc

    cleaned = {
        "job_id": str(pick(job, "id", "ID", "JOBDIVANO")),
        "company": pick(job, "company", "companyname", "COMPANYNAME"),
        "job_title": pick(job, "job title", "jobtitle", "JOBTITLE", "POSTING_TITLE"),
        "location": location if location else None,
        "description": description
    }

    return cleaned