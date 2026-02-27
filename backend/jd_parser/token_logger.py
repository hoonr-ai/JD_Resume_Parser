import csv
import os
from datetime import datetime

CSV_FILE = "token_usage.csv"

class TokenLogger:

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0

        # create file with header if not exists
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "job_id",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "estimated_cost"
                ])

    def log(self, usage, job_id):
        if not usage:
            return

        in_tok = usage.input_tokens
        out_tok = usage.output_tokens
        total = in_tok + out_tok

        # GPT-4.1-mini pricing
        cost = (in_tok/1_000_000)*0.15 + (out_tok/1_000_000)*0.60

        self.requests += 1
        self.input_tokens += in_tok
        self.output_tokens += out_tok

        # WRITE IMMEDIATELY (important)
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow().isoformat(),
                job_id,
                in_tok,
                out_tok,
                total,
                round(cost, 6)
            ])

    def summary(self):
        total = self.input_tokens + self.output_tokens
        cost = (self.input_tokens/1_000_000)*0.15 + (self.output_tokens/1_000_000)*0.60

        print("\n======== TOKEN SUMMARY ========")
        print("Requests:", self.requests)
        print("Input tokens:", self.input_tokens)
        print("Output tokens:", self.output_tokens)
        print("Total tokens:", total)
        print(f"Estimated cost: ${cost:.4f}")
        print("CSV saved to token_usage.csv")
        print("===============================")