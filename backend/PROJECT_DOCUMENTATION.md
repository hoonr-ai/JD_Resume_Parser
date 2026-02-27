# Resume Parser Project Documentation

## 1. Project Overview
The **Resume Parser Backend** is a specialized service designed to ingest resume data (currently in JSON format), extract structured information using deterministic parsing and ontology-based resolution, and store the results in a Supabase database. It also generates standardized JSON output files for downstream consumption.

## 2. Technology Stack
*   **Language:** Python 3.10+
*   **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) - High-performance, easy-to-use API framework.
*   **Database:** [Supabase](https://supabase.com/) (PostgreSQL) - Managed database for storage and vector handling.
*   **Database Client:** `supabase-py` - Python client for Supabase interactions.
*   **Testing:** `pytest` - Framework for unit and integration testing.
*   **Runtime:** `uvicorn` - ASGI server for running the FastAPI application.

## 3. System Architecture

The system follows a pipeline architecture:
1.  **Ingestion:** Raw resume data (JSON) is read and sanitized.
2.  **Parsing:** Text is extracted and passed through specialized parsers (Contact, Sections, Skills).
3.  **Resolution:** Skills are resolved against a loaded ontology from Supabase.
4.  **Storage:** Parsed data is stored in relational tables (`candidates`, `candidate_contacts`, etc.).
5.  **Output:** Final results are formatted into two distinct JSON schemas and saved to the file system.

```mermaid
graph TD
    A[Input Resume JSON] -->|Batch Script| B(Ingest Service)
    B --> C{Parsing Pipeline}
    C -->|Extract| D[Contact Info]
    C -->|Extract| E[Sections (Summary, etc.)]
    C -->|Resolve & Score| F[Skills]
    F -->|Ontology| G[Supabase Ontology Table]
    C -->|Combine| H[Candidate Profile]
    H -->|Save| I[(Supabase DB)]
    H -->|Split| J[Profile Schema JSON]
    H -->|Split| K[Skill Profile JSON]
```

## 4. Key Modules

### 4.1 Ingestion (`app/ingestion`)
*   **`sanitizer.py`**: Cleans input strings, removing null bytes and excessive whitespace.
*   **`json_reader.py`**: Reads the input JSON and extracts the raw resume text from fields like `content` or `text`.

### 4.2 Parsing (`app/parsing`)
*   **`section_extract.py`**: Uses Regex patterns to split the resume text into logical sections (Summary, Experience, Education, Skills). Contains `extract_seniority_level` to identify candidate seniority.
*   **`contact_extract.py`**: Extracts email, phone numbers, and links (LinkedIn, GitHub) using regex patterns.
*   **`skills_extract.py`**:
    *   Tokenizes text into n-grams (1-3 words).
    *   Resolves tokens against the Skill Ontology.
    *   Calculates scores based on frequency, recency, and seniority weights.
    *   **Note:** Specifically filters out seniority tokens (e.g., "SR", "Junior") to prevent them from being classified as skills.
*   **`schema_builders.py`**: Assembles the extracted data into the final `candidate_profile` structure.

### 4.3 Database & Ontology (`app/db`)
*   **`supabase_client.py`**: Manages the singleton connection to Supabase.
*   **`ontology/resolver.py`**: Loads the skill ontology into memory at startup to ensure fast, synchronous skill matching during parsing.

#### 4.3.1 Ontology Loading & Usage Process
The ontology system is designed for high performance and minimal database load.

**1. Loading Strategy (with Caching)**
*   **Startup Check:** When `OntologyResolver` initializes, it first checks for a local file `backend/ontology_cache.json`.
*   **Cache Hit:** If the file exists and is less than 6 hours old, the ontology is loaded directly from disk. This takes ~0.5 seconds.
*   **Cache Miss:** If the file is missing or expired, the system connects to Supabase and fetches all rows from `skill_nodes` and `skill_aliases` tables.
*   **Persist:** The fetched data is saved to `backend/ontology_cache.json` for future runs.

**2. Resolution Logic**
The `resolve_skill(text)` method processes potential skill tokens using a tiered approach:
1.  **Exact Alias Match:** Checks if `text.lower()` exists in the `skill_aliases` map (e.g., "js" -> "Javascript").
2.  **Exact Canonical Match:** Checks if `text.lower()` matches a canonical skill name (e.g., "python" -> "Python").
3.  **Fuzzy Match:** (Optional/Configurable) Uses `rapidfuzz` to find close matches if enabled in settings.

**3. Data Structure**
The ontology is stored in memory as:
*   `skill_nodes`: `{skill_id: {canonical_name, category}}`
*   `skill_aliases`: `{alias_lower: skill_id}`
*   `canonical_map`: `{canonical_lower: skill_id}`

### 4.4 Services (`app/services`)
*   **`ingest_service.py`**: The orchestrator. It calls the parser modules, constructs the profile, builds the `candidate_skill_profile`, and handles database insertion (UPSERT logic).

## 5. Data Flow & Output

### 5.1 Input
The system expects JSON files in `backend/input_resumes/` containing a `content` field with the resume text.

### 5.2 Processing
The `batch_ingest_folder.py` script iterates through the input folder and calls the `ingest_service`.

### 5.3 Output Files
For each processed resume (e.g., `Raju_Resume.json`), two output files are generated in `backend/Final_output/`:

1.  **`Raju_Resume_profile_schema.json`**:
    *   Contains personal info, contact details, parsed sections (Summary, Experience), and a simple list of skill names.
    *   Includes metadata like `seniority_and_scope`.
2.  **`Raju_Resume_skill_profile.json`**:
    *   Contains the detailed `candidate_skill_profile`.
    *   Lists every identified skill with its `skill_id`, `canonical_name`, and calculated scores (`proficiency`, `frequency`, `impact`, `recency`).

## 6. Usage Guide

### 6.1 Installation
```bash
# Create virtual env
python -m venv .resparse

# Activate
.\.resparse\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt
```

### 6.2 Configuration
Ensure your `.env` file is set up with:
```
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

### 6.3 Running Batch Ingestion
1.  Place resume JSONs in `backend/input_resumes/`.
2.  Run the script:
    ```bash
    python scripts/batch_ingest_folder.py
    ```
3.  Check `backend/Final_output/` for results.

### 6.4 API Usage
Start the server:
```bash
uvicorn app.main:app --reload
```
POST to `/ingest/resume-json` with the resume JSON body.

## 7. Database Architecture (Supabase)
*   **`candidates`**: Core user table.
*   **`candidate_profile_json`**: Stores the full parsed JSON blob.
*   **`candidate_skill_scores`**: Relational table storing individual skill scores for analytics.
*   **`candidate_resume`**: Stores the raw input text and metadata.
