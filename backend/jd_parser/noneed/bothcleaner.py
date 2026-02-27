import re
import html
from bs4 import BeautifulSoup

# --------------------------------------------------
# TEXT CLEANER
# --------------------------------------------------

def clean_html(text: str | None):
    if not text:
        return None

    text = html.unescape(text)
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = re.sub(r'\s+', ' ', text)

    return text


# --------------------------------------------------
# FIELD RESOLVER (handles both formats)
# --------------------------------------------------

def pick(job, *keys):
    """
    Returns first existing key from multiple possibilities
    Handles UPPERCASE and lowercase schemas
    """
    for k in keys:
        if k in job and job[k]:
            return job[k]
        if k.upper() in job and job[k.upper()]:
            return job[k.upper()]
        if k.lower() in job and job[k.lower()]:
            return job[k.lower()]
    return None


# --------------------------------------------------
# MAIN CLEAN FUNCTION
# --------------------------------------------------

def clean_job(job: dict):

    description = pick(job,
        "posting description",
        "postingdescription",
        "job description",
        "jobdescription"
    )

    cleaned = {
        "job_id": str(pick(job, "id", "ID", "JOBDIVANO")),
        "company": pick(job, "company", "companyname", "COMPANYNAME"),
        "job_title": pick(job, "job title", "jobtitle", "JOBTITLE", "POSTING_TITLE"),
        "description": clean_html(description)
    }

    return cleaned