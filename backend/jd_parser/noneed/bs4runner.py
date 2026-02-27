import json
from locationandother import clean_job

with open("response.json", encoding="utf-8") as f:
    raw = json.load(f)

cleaned_jobs = [clean_job(j) for j in raw]

with open("clean_jobsv1.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_jobs, f, indent=2, ensure_ascii=False)

print("Cleaned", len(cleaned_jobs), "jobs")