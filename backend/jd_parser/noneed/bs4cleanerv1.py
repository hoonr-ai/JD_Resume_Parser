import re
import html
from bs4 import BeautifulSoup

# -------------------------------
# TEXT CLEANER
# -------------------------------

def clean_html(text):
    if not text:
        return None

    # decode HTML entities
    text = html.unescape(text)

    # remove HTML tags
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    return text


# -------------------------------
# MAIN CLEANER (MINIMAL VERSION)
# -------------------------------

def clean_job(job):

    cleaned_description = clean_html(
        job.get("posting description") or job.get("job description")
    )

    cleaned = {
        "job_id": str(job.get("id")),
        "company": job.get("company"),
        "job_title": job.get("job title"),
        "description": cleaned_description
    }

    return cleaned