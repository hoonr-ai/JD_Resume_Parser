"""
run_jd_to_toon.py
────────────────────────
Scans backend/JD/ for .json files, cleans the JDs using the friend's logic,
converts each one directly to TOON using jd_to_toon(), and saves
the result to backend/Final_output_JD_TOON/<job_id>.toon

Run:
    cmd /c "set PYTHONPATH=backend && .resparse\Scripts\python.exe run_jd_to_toon.py"
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from app.parsing.jd_to_toon import jd_to_toon
from jd_parser.locationandother import clean_job

def load_jobs(path):
    if os.path.getsize(path) == 0:
        raise ValueError("File is completely empty (0 bytes). Please make sure it is saved in your editor.")
        
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    # Case 1 → list 
    if isinstance(data, list):
        return data

    # Case 2 → wrapped API response
    if isinstance(data, dict):
        for key in ["data", "Data", "jobs", "result", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]

    raise ValueError("Unsupported JSON format")

ROOT        = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR   = os.path.join(ROOT, "backend", "JD")
OUT_DIR     = os.path.join(ROOT, "backend", "Final_output_JD_TOON")

os.makedirs(OUT_DIR, exist_ok=True)

files = [f for f in os.listdir(INPUT_DIR)
         if f.lower().endswith(".json") and os.path.isfile(os.path.join(INPUT_DIR, f))]

if not files:
    print(f"No .json files found in JD/")
    sys.exit(0)

stats = {"total_files": len(files), "success_jobs": 0, "failed_jobs": 0}
print(f"Found {len(files)} file(s) in JD/\n")

for filename in files:
    file_path = os.path.join(INPUT_DIR, filename)
    print(f"Processing {filename}...")
    
    try:
        raw_jobs = load_jobs(file_path)
        
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
                
            try:
                # 1. Run friend's cleaning logic
                cleaned = clean_job(job)
                
                # 2. Run our deterministic extraction to TOON
                toon_script = jd_to_toon(cleaned)
                
                # 3. Save
                job_id = str(cleaned.get('job_id') or cleaned.get('id') or cleaned.get('ID') or cleaned.get('JOBDIVANO') or "unknown")
                # sanitize job_id for filename
                safe_job_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', job_id)
                out_path = os.path.join(OUT_DIR, f"{safe_job_id}.toon")
                
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(toon_script)
                    
                stats["success_jobs"] += 1
                
                print(f"  ✅  {safe_job_id}.toon generated.")
                
            except Exception as e:
                print(f"  ❌  Failed job inside {filename} → {e}")
                stats["failed_jobs"] += 1
                
    except Exception as e:
        print(f"  ❌  Failed reading file {filename} → {e}")

print(f"\n{'='*50}")
print(f"Done. Success Jobs: {stats['success_jobs']} | Failed Jobs: {stats['failed_jobs']} | Files checked: {stats['total_files']}")
print(f"Output folder: {OUT_DIR}")
