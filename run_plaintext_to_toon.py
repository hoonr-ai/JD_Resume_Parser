"""
run_plaintext_to_toon.py
────────────────────────
Scans backend/input_resumes/ for .json files, converts each one
directly from PLAINTEXT → TOON using plaintext_to_toon(), and saves
the result to backend/Final_output_TOON/<name>_final_parsed_structure.toon

Successfully processed files → moved to input_resumes/processed/
Failed files                 → moved to input_resumes/failed/

Run:
    cmd /c "set PYTHONPATH=backend && .resparse\\Scripts\\python.exe run_plaintext_to_toon.py"
"""
import sys, os, json, re, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from app.parsing.plaintext_to_toon import plaintext_to_toon

ROOT        = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR   = os.path.join(ROOT, "backend", "input_resumes")
OUT_DIR     = os.path.join(ROOT, "backend", "Final_output_TOON")
PROCESSED   = os.path.join(INPUT_DIR, "processed")
FAILED      = os.path.join(INPUT_DIR, "failed")

for d in (OUT_DIR, PROCESSED, FAILED):
    os.makedirs(d, exist_ok=True)

files = [f for f in os.listdir(INPUT_DIR)
         if f.lower().endswith(".json") and os.path.isfile(os.path.join(INPUT_DIR, f))]

if not files:
    print(f"No .json files found in input_resumes/")
    sys.exit(0)

stats = {"total": len(files), "success": 0, "failed": 0}
print(f"Found {len(files)} file(s) in input_resumes/\n")

for filename in files:
    file_path = os.path.join(INPUT_DIR, filename)
    base_name = os.path.splitext(filename)[0]
    out_path  = os.path.join(OUT_DIR, f"{base_name}_final_parsed_structure.toon")

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

        toon = plaintext_to_toon(raw_text, source_id=source_id)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(toon)

        # Quick section count check
        sections_found = re.findall(r"^SECTION  (\S+)", toon, re.MULTILINE)
        skills_count   = toon.count("\n  ITEM  ")

        print(f"  ✅  {filename}")
        print(f"      → {os.path.basename(out_path)}")
        print(f"      Sections: {len(sections_found)} | Skills: {skills_count}")

        # Move to processed/
        shutil.move(file_path, os.path.join(PROCESSED, filename))
        print(f"      Moved → input_resumes/processed/{filename}")
        stats["success"] += 1

    except Exception as e:
        print(f"  ❌  {filename}  →  {e}")
        # Move to failed/
        shutil.move(file_path, os.path.join(FAILED, filename))
        print(f"      Moved → input_resumes/failed/{filename}")
        stats["failed"] += 1

print(f"\n{'='*50}")
print(f"Done. Success: {stats['success']} | Failed: {stats['failed']} | Total: {stats['total']}")
print(f"Output folder: {OUT_DIR}")
