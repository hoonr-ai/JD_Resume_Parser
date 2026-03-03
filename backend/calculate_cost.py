import os

def count_chars(directory, files_to_match=None):
    if not os.path.exists(directory):
        return 0
    total_chars = 0
    for filename in os.listdir(directory):
        if files_to_match and filename not in files_to_match:
            continue
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                total_chars += len(f.read())
    return total_chars

# Phase 1
phase1_input_chars = count_chars(r"backend/Final_output_JD_TOON")
phase1_output_chars = count_chars(r"backend/JD_SKILL_REQUIREMENT")

# Phase 2
phase2_processed_files = os.listdir(r"backend/CANDIDATE_SKILL_PROFILE") if os.path.exists(r"backend/CANDIDATE_SKILL_PROFILE") else []
phase2_input_chars = count_chars(r"backend/Final_output_TOON", files_to_match=phase2_processed_files)
phase2_output_chars = count_chars(r"backend/CANDIDATE_SKILL_PROFILE")

total_input_chars = phase1_input_chars + phase2_input_chars
total_output_chars = phase1_output_chars + phase2_output_chars

total_input_tokens = total_input_chars / 4
total_output_tokens = total_output_chars / 4

cost = (total_input_tokens / 1_000_000) * 0.150 + (total_output_tokens / 1_000_000) * 0.600

print(f"Total Input Characters: {total_input_chars:,} (~{int(total_input_tokens):,} tokens)")
print(f"Total Output Characters: {total_output_chars:,} (~{int(total_output_tokens):,} tokens)")
print(f"Estimated Cost: ${cost:.6f}")
