import json
import os
import shutil
from locationandother import clean_job


def load_jobs(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Case 1 → list 
    if isinstance(data, list):
        return data

    # Case 2 → wrapped API response
    if isinstance(data, dict):
        for key in ["data", "Data", "jobs", "result", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]

    raise ValueError("Unsupported JSON format")



def main():

    input_dir = 'Input'
    output_dir = 'Cleaned_Jobs'
    processed_dir = os.path.join(input_dir, 'processed')  # lowercase for consistency
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    input_files = [f for f in os.listdir(input_dir)
                  if f.endswith('.json') and os.path.isfile(os.path.join(input_dir, f))]

    for input_file in input_files:
        input_path = os.path.join(input_dir, input_file)
        try:
            raw_jobs = load_jobs(input_path)
            cleaned_jobs = [clean_job(j) for j in raw_jobs if isinstance(j, dict)]
            for job, cleaned in zip(raw_jobs, cleaned_jobs):
                job_id = str(job.get('id') or job.get('ID') or job.get('JOBDIVANO') or cleaned.get('job_id') or 'unknown')
                out_path = os.path.join(output_dir, f'{job_id}.json')
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(cleaned, f, indent=2, ensure_ascii=False)
            print(f"✅ Cleaned {len(cleaned_jobs)} jobs from {input_file} to {output_dir}")
            # Move processed input file to Processed
            shutil.move(input_path, os.path.join(processed_dir, input_file))
        except Exception as e:
            print(f"❌ Failed to process {input_file}: {e}")


if __name__ == "__main__":
    main()