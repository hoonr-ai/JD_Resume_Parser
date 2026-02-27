import os
import time
import logging
from typing import Dict, Optional, Tuple, Any
from rapidfuzz import process, fuzz
from dotenv import load_dotenv
from app.db.supabase_client import get_supabase_client

load_dotenv()

# Config — read directly from environment (no settings module needed)
_SKILL_NODES_TABLE   = os.getenv("SKILL_NODES_TABLE",   "skill_nodes")
_SKILL_ALIASES_TABLE = os.getenv("SKILL_ALIASES_TABLE", "skill_aliases")
_FUZZY_MATCH_ENABLED = os.getenv("FUZZY_MATCH_ENABLED", "false").lower() == "true"
_FUZZY_THRESHOLD     = int(os.getenv("FUZZY_THRESHOLD", "90"))

logger = logging.getLogger(__name__)

class OntologyResolver:
    _instance = None
    
    def __init__(self):
        from flashtext import KeywordProcessor
        self.skill_aliases: Dict[str, str] = {} # alias_lower -> skill_id
        self.skill_nodes: Dict[str, Dict] = {} # skill_id -> {canonical_name, category}
        self.canonical_map: Dict[str, str] = {} # canonical_lower -> skill_id
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.last_loaded: float = 0
        self.TTL = 6 * 3600 # 6 hours

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = OntologyResolver()
        return cls._instance

    def load_ontology(self, force: bool = False):
        if not force and (time.time() - self.last_loaded < self.TTL) and self.skill_nodes:
            return

        print("🚀 Initializing Hybrid Skill Extractor & Graph Ontology...")
        
        # Try loading from local cache first
        if not force and self._load_from_local_cache():
            return

        logger.info("Loading ontology from Supabase...")
        print("🔗 Ontology: Connecting to Database...")
        supabase = get_supabase_client()

        # Helper to fetch all rows with pagination
        def fetch_all(table, columns):
            all_rows = []
            start = 0
            limit = 1000
            while True:
                response = supabase.table(table).select(columns).range(start, start + limit - 1).execute()
                data = response.data
                if not data:
                    break
                all_rows.extend(data)
                if len(data) < limit:
                    break
                start += limit
            return all_rows

        # Load Skill Nodes
        try:
            nodes_data = fetch_all(_SKILL_NODES_TABLE, "id, canonical_name, category")
            
            self.skill_nodes = {}
            self.canonical_map = {}
            for node in nodes_data:
                sid = node['id']
                cname = node.get('canonical_name')
                cat = node.get('category')
                if cname:
                    self.skill_nodes[sid] = {"canonical_name": cname, "category": cat}
                    self.canonical_map[cname.lower()] = sid
            
            print(f"✅ Ontology: Loaded {len(self.skill_nodes)} skills.")
            
            # Load Skill Aliases
            aliases_data = fetch_all(_SKILL_ALIASES_TABLE, "alias, skill_id")
            
            self.skill_aliases = {}
            for row in aliases_data:
                alias = row.get('alias')
                sid = row.get('skill_id')
                if alias and sid:
                    self.skill_aliases[alias.lower()] = sid
            
            print(f"✅ Ontology: Loaded {len(self.skill_aliases)} aliases.")
            
            # Build FlashText processor
            self._build_keyword_processor()
            
            self.last_loaded = time.time()
            self._save_to_local_cache() # Save for next time
            logger.info(f"Ontology loaded: {len(self.skill_nodes)} nodes, {len(self.skill_aliases)} aliases")
        except Exception as e:
            logger.error(f"Failed to load ontology: {e}")
            print(f"❌ Ontology Error: {e}")

    def _build_keyword_processor(self):
        # Reset
        from flashtext import KeywordProcessor
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        
        # Add aliases
        # We want extract_keywords to return the SKILL_ID
        for alias, sid in self.skill_aliases.items():
            self.keyword_processor.add_keyword(alias, sid)
            
        # Also add canonical names if not covered by aliases
        for cname, sid in self.canonical_map.items():
             self.keyword_processor.add_keyword(cname, sid)
             
        print(f"⚡ FlashText: Index built with {len(self.keyword_processor)} keywords.")

    def _get_cache_path(self):
        import os
        # Save in the same directory as this file or a temp dir. 
        # Better: backend/ontology_cache.json to persist across runs easily
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(base_dir, "ontology_cache.json")

    def _load_from_local_cache(self) -> bool:
        import json
        import os
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return False
            
        try:
            # Check file age (TTL)
            mtime = os.path.getmtime(cache_path)
            if time.time() - mtime > self.TTL:
                print("⚠️ Ontology cache expired, refreshing...")
                return False

            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.skill_nodes = data.get("nodes", {})
            self.skill_aliases = data.get("aliases", {})
            
            # Rebuild canonical map
            self.canonical_map = {}
            for sid, node in self.skill_nodes.items():
                cname = node.get("canonical_name")
                if cname:
                    self.canonical_map[cname.lower()] = sid
            
            self._build_keyword_processor()
            self.last_loaded = time.time()
            print(f"✅ Ontology: Loaded from local cache ({len(self.skill_nodes)} skills, {len(self.skill_aliases)} aliases).")
            return True
        except Exception as e:
            logger.warning(f"Failed to load local cache: {e}")
            return False

    def _save_to_local_cache(self):
        import json
        try:
            cache_path = self._get_cache_path()
            data = {
                "nodes": self.skill_nodes,
                "aliases": self.skill_aliases
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            print(f"💾 Ontology: Cached locally to {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to save local cache: {e}")

    def resolve_skill(self, text: str) -> Optional[Dict[str, Any]]:
        self.load_ontology()
        text_lower = text.lower().strip()
        if not text_lower:
            return None

        # 1. Exact Alias Match
        if text_lower in self.skill_aliases:
            sid = self.skill_aliases[text_lower]
            if sid in self.skill_nodes:
                return self._format_result(sid)

        # 2. Exact Canonical Match
        if text_lower in self.canonical_map:
            sid = self.canonical_map[text_lower]
            return self._format_result(sid)

        # 3. Fuzzy Match (if enabled)
        if _FUZZY_MATCH_ENABLED:
            # Combine aliases and canonicals for search
            choices = list(self.skill_aliases.keys()) + list(self.canonical_map.keys())
            match = process.extractOne(text_lower, choices, scorer=fuzz.WRatio)
            if match:
                best_match_str, score, _ = match
                if score >= _FUZZY_THRESHOLD:
                    if best_match_str in self.skill_aliases:
                        sid = self.skill_aliases[best_match_str]
                    else:
                        sid = self.canonical_map[best_match_str]
                    return self._format_result(sid)
        
        return None

    def _format_result(self, skill_id: str) -> Dict[str, Any]:
        node = self.skill_nodes.get(skill_id)
        if not node:
            return None
        return {
            "skill_id": skill_id,
            "canonical_name": node["canonical_name"],
            "category": node["category"]
        }
