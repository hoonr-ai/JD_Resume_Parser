from typing import List, Set
from app.db.ontology.resolver import OntologyResolver

# Strict noise filter
NOISE_TOKENS = {
    "email", "mail", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun", 
    "science", "education", "engineering", "validation", "protocols", "registry", 
    "programming", "data management", "data integration", "tops-10", "hal/s", "less",
    "code", "ref", "date", "adept", "processing", "financial", "administration", "security", "networking", "accessibility", "marketing", "documentation"
}

STOP_SKILL_TOKENS = {"sr", "jr", "senior", "junior", "lead", "principal", "staff", "associate"}

# Allow 2-char skills
ALLOW_SHORT = {"c", "r", "go", "ai", "c++", "c#", "5s", "qa", "qc", "ui", "ux", "ml", "bi"}

# Context words required for "R"
R_CONTEXT_WORDS = {"language", "programming", "rstudio", "tidyverse", "ggplot", "shiny", "cran", "statistical", "analysis"}

# Skills missing from DB to inject manually
MISSING_SKILLS = {
    "SAS": "SAS",
    "Jira": "Jira",
    "CDISC": "CDISC",
    "ADaM": "ADaM",
    "SDTM": "SDTM",
    "TFLs": "TFLs",
    "SOPs": "SOPs",
    "CAPA": "CAPA",
    # Cindy's Skills
    "Microsoft Office": "Microsoft Office",
    "Excel": "Excel",
    "Word": "Word",
    "PowerPoint": "PowerPoint",
    "Outlook": "Outlook",
    "Access": "Access",
    "Accounts Payable": "Accounts Payable",
    "Accounts Receivable": "Accounts Receivable",
    "Data Entry": "Data Entry",
    "Ten Key": "Ten Key",
    "Medical Terminology": "Medical Terminology",
    "Medical Transcription": "Medical Transcription",
    "Medical Billing": "Medical Insurance Billing",
    "HIPAA": "HIPAA",
    "Anatomy": "Anatomy",
    "Physiology": "Physiology",
    # Ricardo's Design Skills
    "Adobe Creative Suite": "Adobe Creative Suite",
    "Photoshop": "Adobe Photoshop",
    "Illustrator": "Adobe Illustrator",
    "InDesign": "Adobe InDesign",
    "After Effects": "Adobe After Effects",
    "Premiere": "Adobe Premiere Pro",
    "Figma": "Figma",
    "Canva": "Canva",
    "UX/UI Design": "UX/UI Design",
    "SharePoint": "Microsoft SharePoint",
    "Microsoft 365": "Microsoft 365",
    "Teller Express": "Teller Express",
    # Grace's Cloud/DevOps Skills
    "Azure": "Microsoft Azure",
    "GCP": "Google Cloud Platform",
    "Kubernetes": "Kubernetes",
    "Terraform": "Terraform",
    "Ansible": "Ansible",
    "Jenkins": "Jenkins",
    "Maven": "Maven",
    "MongoDB": "MongoDB",
    "Cassandra": "Apache Cassandra",
    "HANA": "SAP HANA",
    "DynamoDB": "Amazon DynamoDB",
    "AppDynamics": "AppDynamics",
    "Grafana": "Grafana",
    # Dheeraj's Oracle/Fusion Skills
    "Oracle Fusion Cloud": "Oracle Fusion Cloud",
    "Oracle Fusion": "Oracle Fusion Cloud",
    "Fusion Financials": "Oracle Fusion Financials",
    "Oracle Financials": "Oracle Financials",
    "BI Publisher": "Oracle BI Publisher",
    "BIP": "Oracle BI Publisher",
    "OTBI": "Oracle Transactional Business Intelligence",
    "XML Publisher": "Oracle XML Publisher",
    "FBDI": "File-Based Data Import (FBDI)",
    "ADFDI": "ADF Desktop Integrator",
    "SQL*Loader": "SQL*Loader",
    "Oracle Integration Cloud": "Oracle Integration Cloud",
    "OIC": "Oracle Integration Cloud",
    "ESS Jobs": "ESS Jobs",
    "BPM Worklist": "BPM Worklist",
    "AME": "Approval Management Engine",
    "Fast Formulas": "Fast Formulas",
    "P2P": "Procure-to-Pay",
    "O2C": "Order-to-Cash",
    "AP": "Accounts Payable",
    "AR": "Accounts Receivable",
    "GL": "General Ledger",
    "FA": "Fixed Assets",
    "PO": "Purchase Orders",
    "OM": "Order Management",
    "SOAP": "SOAP APIs",
    "REST": "REST APIs"
}

def extract_skills(text: str) -> List[str]:
    """
    Extracts canonical skills using FlashText with strict filtering.
    """
    resolver = OntologyResolver.get_instance()
    resolver.load_ontology() 
    processor = resolver.keyword_processor
    
    if not text or not processor:
        return []
        
    # Hotfix: Inject missing skills if not present
    if "SAS" not in processor:
        for skill, canonical in MISSING_SKILLS.items():
            processor.add_keyword(skill, canonical) 
    
    # Extract with spans: [(skill_id, start, end), ...]
    matches = processor.extract_keywords(text, span_info=True)
    
    # Identify "bad" lines
    bad_ranges = []
    lines = text.split('\n')
    current_pos = 0
    for line in lines:
        line_len = len(line)
        line_lower = line.lower()
        if "@" in line or "linkedin" in line_lower or "github" in line_lower:
             bad_ranges.append((current_pos, current_pos + line_len))
        current_pos += line_len + 1 

    final_skills = set()
    
    for sid, start, end in matches:
        # A) Contact Line Filter
        is_bad = False
        for b_start, b_end in bad_ranges:
            if b_start <= start < b_end:
                is_bad = True
                break
        if is_bad:
            continue
            
        # Get Node
        node = resolver.skill_nodes.get(sid)
        if node: 
            canonical = node["canonical_name"]
        else:
            # Fallback for injected skills where SID is the canonical name
            canonical = sid
            
        canonical_lower = canonical.lower()
        
        # Get the actual matched text (alias)
        matched_text = text[start:end]
        matched_lower = matched_text.lower()
        
        # B) Seniority Filter
        if matched_lower in STOP_SKILL_TOKENS:
            continue
            
        # C) Noise Filter (Canonical OR Alias)
        if canonical_lower in NOISE_TOKENS or matched_lower in NOISE_TOKENS:
            continue
            
        # D) Length / Short Token Rules
        if len(matched_lower) < 3 and matched_lower not in ALLOW_SHORT:
            continue
            
        # E) Special Context for "R"
        if matched_lower == "r":
            # Check +/- 30 chars
            ctx_start = max(0, start - 30)
            ctx_end = min(len(text), end + 30)
            context_snippet = text[ctx_start:ctx_end].lower()
            if not any(w in context_snippet for w in R_CONTEXT_WORDS):
                continue

        final_skills.add(canonical)
        
    return list(final_skills)
