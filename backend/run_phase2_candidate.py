"""
run_phase2_candidate.py
───────────────────────
Batch processes raw parsed Candidate Resume TOON files and extracts
structured CANDIDATE_SKILL_PROFILE TOON files using hybrid LLM extraction
and Python mathematical exponential decay scoring.
"""

import os
import glob
from app.parsing.candidate_profile_builder import build_candidate_profile

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    resume_toon_dir = os.path.join(base_dir, "Final_output_TOON")
    out_dir = os.path.join(base_dir, "CANDIDATE_SKILL_PROFILE")
    
    if not os.path.exists(resume_toon_dir):
        print(f"Directory {resume_toon_dir} does not exist.")
        return
        
    os.makedirs(out_dir, exist_ok=True)
    
    toon_files = glob.glob(os.path.join(resume_toon_dir, "*.toon"))
    if not toon_files:
        print(f"No .toon files found in {resume_toon_dir}")
        return
        
    # LIMIT TO 1 FILE FOR RAPID TESTING
    toon_files = toon_files[:1]
        
    print(f"Found {len(toon_files)} Resume TOON files. Processing Phase 2 Mathematical Scoring...")
    
    success_count = 0
    fail_count = 0
    
    for full_path in toon_files:
        filename = os.path.basename(full_path)
        candidate_id = filename.replace(".toon", "")
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        print(f"\nProcessing {filename}...")
        try:
            extracted_toon = build_candidate_profile(content, candidate_id)
            
            out_path = os.path.join(out_dir, filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(extracted_toon)
            
            print(f"  ✅ Saved Phase 2 output to {out_path}")
            success_count += 1
        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}")
            fail_count += 1
            
    print(f"\n==================================================")
    print(f"Phase 2 Complete. Success: {success_count} | Failed: {fail_count}")
    print(f"Output folder: {out_dir}")

if __name__ == "__main__":
    main()
