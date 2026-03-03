"""
run_phase3_match.py
───────────────────
Batch processes Phase 1 JD Outputs and Phase 2 Candidate Outputs
to evaluate mathematical fit.
"""

import os
import glob
from app.parsing.matching_engine import evaluate_match

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jd_req_dir = os.path.join(base_dir, "JD_SKILL_REQUIREMENT")
    cand_prof_dir = os.path.join(base_dir, "CANDIDATE_SKILL_PROFILE")
    out_dir = os.path.join(base_dir, "MATCH_RESULTS")
    
    if not os.path.exists(jd_req_dir) or not os.path.exists(cand_prof_dir):
        print(f"Missing required input directories.")
        return
        
    os.makedirs(out_dir, exist_ok=True)
    
    jd_files = glob.glob(os.path.join(jd_req_dir, "*.toon"))
    cand_files = glob.glob(os.path.join(cand_prof_dir, "*.toon"))
    
    if not jd_files or not cand_files:
        print(f"Missing Phase 1 or Phase 2 TOON files.")
        return
        
    # Target the specific 11042200 JD file request by the user
    jd_file = os.path.join(jd_req_dir, "11042200.toon")
    jd_name = "11042200"
    
    if not os.path.exists(jd_file):
        print(f"File {jd_file} does not exist. Did you run Phase 1 for it?")
        return
    
    with open(jd_file, "r", encoding="utf-8") as f:
        jd_content = f.read()
        
    print(f"Starting Phase 3 Match Evaluation against JD [{jd_name}]...")
    
    for cand_file in cand_files:
        cand_name = os.path.basename(cand_file).replace('.toon', '')
        print(f"\nEvaluating Candidate [{cand_name}]...")
        
        with open(cand_file, "r", encoding="utf-8") as f:
            cand_content = f.read()

        try:
            match_toon = evaluate_match(jd_content, cand_content)
            
            out_filename = f"{jd_name}_vs_{cand_name}.toon"
            out_path = os.path.join(out_dir, out_filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(match_toon)
            
            print(f"  [SUCCESS] Saved Phase 3 Match to {out_path}")
        except Exception as e:
            print(f"  [ERROR] Error evaluating match: {e}")
            
    print(f"\n==================================================")
    print(f"Phase 3 Complete.")
    print(f"Output folder: {out_dir}")
    
    from app.parsing.token_logger import telemetry
    telemetry.summary()

if __name__ == "__main__":
    main()
