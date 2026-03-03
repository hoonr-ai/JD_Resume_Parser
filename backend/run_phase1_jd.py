"""
run_phase1_jd.py
────────────────
Batch processes raw parsed JD TOON files and extracts
structured JD_SKILL_REQUIREMENT TOON files via the LLM.
"""

import os
import glob
from app.parsing.jd_requirements_extractor import extract_jd_requirements

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jd_toon_dir = os.path.join(base_dir, "Final_output_JD_TOON")
    out_dir = os.path.join(base_dir, "JD_SKILL_REQUIREMENT")
    
    if not os.path.exists(jd_toon_dir):
        print(f"Directory {jd_toon_dir} does not exist.")
        return
        
    os.makedirs(out_dir, exist_ok=True)
    
    toon_files = glob.glob(os.path.join(jd_toon_dir, "*.toon"))
    if not toon_files:
        print(f"No .toon files found in {jd_toon_dir}")
        return
        
    print(f"Found {len(toon_files)} JD TOON files. Processing Phase 1 Phase JD Skill Requirements Extraction...")
    
    success_count = 0
    fail_count = 0
    
    for full_path in toon_files:
        filename = os.path.basename(full_path)
        jd_id = filename.replace(".toon", "")
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        print(f"\nProcessing {filename}...")
        try:
            extracted_toon = extract_jd_requirements(content, jd_id)
            
            out_path = os.path.join(out_dir, filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(extracted_toon)
            
            print(f"  ✅ Saved Phase 1 output to {out_path}")
            success_count += 1
        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}")
            fail_count += 1
            
    print(f"\n==================================================")
    print(f"Phase 1 Complete. Success: {success_count} | Failed: {fail_count}")
    print(f"Output folder: {out_dir}")
    
    from app.parsing.token_logger import telemetry
    telemetry.summary()

if __name__ == "__main__":
    main()
