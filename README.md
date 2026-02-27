# Resume Parser — Plaintext → TOON

Converts raw resume plaintext directly into a structured **TOON** script format.  
Built to merge with a JD parsing backend.

---

## Quick Start

### Prerequisites
```bash
# 1. Activate the virtual environment
.resparse\Scripts\activate          # Windows

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Set environment variables
copy backend\.env.example backend\.env   # then fill in values
```

### `.env` required values
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-key
OPENAI_API_KEY=sk-...          # only needed for LLM scoring (archived)
```

---

## Running the Parser

### Drop resumes into the input folder
Place any `.json` resume files into:
```
backend/input_resumes/
```
Each JSON must contain a `PLAINTEXT` field (and optionally `GLOBAL_ID`):
```json
{
  "data": [{ "GLOBAL_ID": "abc123", "PLAINTEXT": "John Doe\n..." }]
}
```

### Run
```
cmd /c "set PYTHONPATH=backend && .resparse\Scripts\python.exe run_plaintext_to_toon.py"
```

### Output
| Path | Contents |
|---|---|
| `backend/Final_output_TOON/<name>_final_parsed_structure.toon` | Generated TOON script |
| `backend/input_resumes/processed/` | Successfully parsed JSONs moved here |
| `backend/input_resumes/failed/` | Failed JSONs moved here |

---

## Module Integration (for your teammate)

### Import directly into your backend
```python
from app.parsing.plaintext_to_toon import plaintext_to_toon

toon_script: str = plaintext_to_toon(
    raw_text="...",   # full resume plaintext
    source_id="abc"   # optional GLOBAL_ID
)
```

### Set `PYTHONPATH=backend` before running any script
```bash
set PYTHONPATH=backend    # Windows CMD
$env:PYTHONPATH="backend" # Windows PowerShell
export PYTHONPATH=backend  # Linux/Mac
```

### What `plaintext_to_toon()` returns
A TOON string with **16 schema-ordered sections**:
```
TOON_VERSION  1.0

SECTION  SOURCE        → GLOBAL_ID
SECTION  CONTACT       → email, name, phone, location, linkedin, github
SECTION  WORK_AUTHORIZATION
SECTION  COMPENSATION_PREFERENCES
SECTION  ROLE_PREFERENCES
SECTION  SUMMARY
SECTION  SKILLS        → flat list of canonical skill names
SECTION  EMPLOYMENT_HISTORY
SECTION  PROJECTS
SECTION  EDUCATION
SECTION  PUBLICATIONS_AND_PATENTS
SECTION  AWARDS_AND_LEADERSHIP
SECTION  SENIORITY_AND_SCOPE
SECTION  EMPLOYMENT_RECENCY
SECTION  STABILITY_AND_TENURE
SECTION  RAW_EXTRACTION → full normalized body text
END_SECTION  RAW_EXTRACTION
```

---

## Project Structure

```
FINAL_RESUME_PARSER/
├── run_plaintext_to_toon.py     ← main entry point
├── poc_jd_match.py              ← JD matching proof-of-concept
├── _archive/llm_scoring/        ← LLM skill scoring (archived, not active)
└── backend/
    ├── .env                     ← secrets (never commit this)
    ├── requirements.txt
    ├── ontology_cache.json      ← local skills DB cache (auto-refreshed)
    ├── input_resumes/           ← drop .json files here
    │   ├── processed/           ← auto-moved after success
    │   └── failed/              ← auto-moved after failure
    ├── Final_output_TOON/       ← generated .toon files
    ├── JD/                      ← JD JSON files for matching PoC
    └── app/
        ├── parsing/             ← core module (5 files)
        │   ├── plaintext_to_toon.py
        │   ├── text_cleaning.py
        │   ├── contact_extract.py
        │   ├── section_extract.py
        │   └── skills_extract.py
        └── db/                  ← skill ontology loader
            ├── ontology/resolver.py
            └── supabase_client.py
```

---

## Merging into your teammate's backend

1. **Copy** the `backend/app/parsing/` and `backend/app/db/` folders into his project's `app/` directory
2. **Add** to his `requirements.txt` (from `backend/requirements.txt`)
3. **Set** `SUPABASE_URL` and `SUPABASE_KEY` in his `.env`
4. **Call** `plaintext_to_toon(raw_text, source_id)` wherever he needs a TOON output

> The module has **zero coupling** to the rest of this repo.  
> `app/parsing/` + `app/db/` is fully self-contained.
