"""
run_plaintext_to_json.py
────────────────────────
Scans backend/input_resumes/ for .json files, converts each one
directly from PLAINTEXT → structured JSON using plaintext_to_json(),
and saves the result to backend/Final_output_JSON/<name>_parsed.json

Successfully processed files → moved to input_resumes/processed/
Failed files                 → moved to input_resumes/failed/

Run (from project root):
    cmd /c "set PYTHONIOENCODING=utf-8 && .resparse\\Scripts\\python.exe run_plaintext_to_json.py"
"""
import sys, os, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from app.parsing.plaintext_to_json import plaintext_to_json

ROOT      = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(ROOT, "backend", "input_resumes")
OUT_DIR   = os.path.join(ROOT, "backend", "Final_output_JSON")
PROCESSED = os.path.join(INPUT_DIR, "processed")
FAILED    = os.path.join(INPUT_DIR, "failed")

for d in (OUT_DIR, PROCESSED, FAILED):
    os.makedirs(d, exist_ok=True)

files = [
    f for f in os.listdir(INPUT_DIR)
    if f.lower().endswith(".json") and os.path.isfile(os.path.join(INPUT_DIR, f))
]

if not files:
    print("No .json files found in input_resumes/")
    sys.exit(0)

stats = {"total": len(files), "success": 0, "failed": 0}
print(f"Found {len(files)} file(s) in input_resumes/\n")

for filename in files:
    file_path = os.path.join(INPUT_DIR, filename)
    base_name = os.path.splitext(filename)[0]
    out_path  = os.path.join(OUT_DIR, f"{base_name}_parsed.json")

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Support both {"data": [...]} wrapper and bare {"PLAINTEXT": "..."}
        if "data" in data and isinstance(data["data"], list):
            record = data["data"][0]
        else:
            record = data

        raw_text  = record.get("PLAINTEXT") or record.get("plaintext", "")
        source_id = record.get("GLOBAL_ID", "")

        if not raw_text:
            raise ValueError("No PLAINTEXT field found in JSON")

        result = plaintext_to_json(raw_text, source_id=source_id, source_file=filename)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Quick stats
        exp_count  = len(result.get("experience", []))
        skill_count = len(result.get("skills", []))
        edu_count  = len(result.get("education", []))

        print(f"  ✅  {filename}")
        print(f"      → {os.path.basename(out_path)}")
        print(f"      Jobs: {exp_count} | Skills: {skill_count} | Education lines: {edu_count}")
        print(f"      Format: {result.get('_format_detected', '?')} | Name: {result.get('name', '?')}")

        # Move to processed/
        shutil.move(file_path, os.path.join(PROCESSED, filename))
        print(f"      Moved → input_resumes/processed/{filename}")
        stats["success"] += 1

    except Exception as e:
        import traceback
        print(f"  ❌  {filename}  →  {e}")
        traceback.print_exc()
        shutil.move(file_path, os.path.join(FAILED, filename))
        print(f"      Moved → input_resumes/failed/{filename}")
        stats["failed"] += 1

print(f"\n{'='*50}")
print(f"Done. Success: {stats['success']} | Failed: {stats['failed']} | Total: {stats['total']}")
print(f"Output folder: {OUT_DIR}")
