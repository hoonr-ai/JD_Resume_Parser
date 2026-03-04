import sys
import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Union

# Add backend directory to path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.parsing.jd_to_toon import jd_to_toon
from app.parsing.plaintext_to_json import plaintext_to_json
from app.parsing.plaintext_to_toon import plaintext_to_toon
from jd_parser.locationandother import clean_job

app = FastAPI(
    title="JD & Resume Parser API",
    description="API for parsing Job Descriptions and Resumes into structured formats like JSON and TOON.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

class ResumeRequest(BaseModel):
    plaintext: str

@app.post("/api/parse/jd-to-toon", tags=["JD Parsing"], summary="Parse JD to TOON")
async def parse_jd_to_toon_endpoint(payload: Union[List[Dict[str, Any]], Dict[str, Any]]):
    """
    Accepts Job Description data (list of jobs or wrapped dict) and converts to TOON format.
    """
    try:
        data = payload
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            # check wrapper
            jobs = [data]
            for key in ["data", "Data", "jobs", "result", "results"]:
                if key in data and isinstance(data[key], list):
                    jobs = data[key]
                    break
        else:
            raise ValueError("Unsupported format")
            
        results = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            cleaned = clean_job(job)
            toon_script = jd_to_toon(cleaned)
            results.append({"job_id": cleaned.get('job_id', cleaned.get('id', 'unknown')), "toon": toon_script})
            
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parse/resume-to-json", tags=["Resume Parsing"], summary="Parse Resume Plaintext to JSON")
async def parse_resume_to_json_endpoint(request: ResumeRequest):
    """
    Accepts raw resume plaintext and extracts structured profile data into JSON schema.
    """
    if not request.plaintext.strip():
        raise HTTPException(status_code=400, detail="Missing or empty 'plaintext'")
        
    try:
        result = plaintext_to_json(request.plaintext)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parse/resume-to-toon", tags=["Resume Parsing"], summary="Parse Resume Plaintext to TOON")
async def parse_resume_to_toon_endpoint(request: ResumeRequest):
    """
    Accepts raw resume plaintext and converts it directly to a unified TOON representation.
    """
    if not request.plaintext.strip():
        raise HTTPException(status_code=400, detail="Missing or empty 'plaintext'")
        
    try:
        toon = plaintext_to_toon(request.plaintext)
        return {"status": "success", "toon": toon}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files after API routes
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def read_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not found</h1><p>Ensure the frontend/index.html file exists.</p>"
