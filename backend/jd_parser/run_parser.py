
import json
import os
import argparse
from openai_jd_parser import extract_jd_requirements, token_logger

def load_job_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description="Parse cleaned jobs with LLM and output to LLM_Output folder.")
    parser.add_argument('--input', '-i', required=True, help='Input cleaned job file or directory')
    parser.add_argument('--output_dir', '-o', default='LLM_Output', help='Output directory for LLM outputs')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    input_paths = []
    if os.path.isdir(args.input):
        for fname in os.listdir(args.input):
            if fname.endswith('.json'):
                input_paths.append(os.path.join(args.input, fname))
    else:
        input_paths = [args.input]

    total_jobs = len(input_paths)
    print(f"\nLoaded jobs: {total_jobs}")

    results = []
    failed = 0

    for idx, path in enumerate(input_paths, start=1):
        try:
            job = load_job_file(path)
            title = (
                job.get("job_title")
                or job.get("JOBTITLE")
                or job.get("job title")
                or "UNKNOWN TITLE"
            )
            print(f"\n[{idx}/{total_jobs}] Processing: {title}")
            parsed = extract_jd_requirements(job)
            results.append(parsed)
            # Save each output by job id
            job_id = str(job.get('job_id') or job.get('id') or job.get('ID') or job.get('JOBDIVANO') or f'job_{idx}')
            out_path = os.path.join(args.output_dir, f'{job_id}.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)
        except Exception as e:
            failed += 1
            print("❌ Failed:", str(e)[:300])
            continue

    print("\n==============================")
    print(f"✅ DONE — {args.output_dir} created")
    print(f"✔ Success: {len(results)}")
    print(f"❌ Failed: {failed}")
    print("==============================")
    token_logger.summary()

if __name__ == "__main__":
    main()