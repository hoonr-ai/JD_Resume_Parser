import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from jd_schema import JDResponse
from prompt_builder import SYSTEM_PROMPT

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------------- TOKEN LOGGER ----------------
class TokenLogger:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0

    def log(self, usage):
        if not usage:
            return
        self.requests += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def summary(self):
        total = self.input_tokens + self.output_tokens
        cost = (self.input_tokens/1_000_000)*0.15 + (self.output_tokens/1_000_000)*0.60

        print("\n======== TOKEN USAGE ========")
        print("Requests:", self.requests)
        print("Input tokens:", self.input_tokens)
        print("Output tokens:", self.output_tokens)
        print("Total tokens:", total)
        print(f"Estimated cost: ${cost:.4f}")
        print("=============================")


token_logger = TokenLogger()


# ---------------- MAIN FUNCTION ----------------
def extract_jd_requirements(job):

    user_prompt = f"""
Job ID: {job.get('job_id')}
Job Title: {job.get('job_title')}

Job Description:
{job.get('description')}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",   # IMPORTANT: use Responses API model
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
    )

    # log tokens
    token_logger.log(response.usage)

    text = response.output_text.strip()

    # ---------------- TRY DIRECT JSON ----------------
    try:
        parsed = json.loads(text)
        return parsed
    except Exception:
        pass

    # ---------------- TRY EXTRACT JSON BLOCK ----------------
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
        return parsed
    except Exception:
        print("\n⚠️ MODEL RETURNED INVALID JSON:")
        print(text[:800])
        return None