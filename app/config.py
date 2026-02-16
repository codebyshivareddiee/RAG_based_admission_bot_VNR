"""
Centralised configuration loaded from environment variables.
All secrets stay in .env – never hard-coded.
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("app.config")

# Look for .env in the project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
_env_loaded = load_dotenv(dotenv_path=_env_path)
print(f"[app.config] .env path: {_env_path}", file=sys.stderr)
print(f"[app.config] .env exists: {_env_path.exists()}", file=sys.stderr)
print(f"[app.config] .env loaded: {_env_loaded}", file=sys.stderr)

BASE_DIR = Path(__file__).resolve().parent


class Settings:
    """Application-wide settings backed by environment variables."""

    # ── College identity ──────────────────────────────────────
    COLLEGE_NAME: str = os.getenv(
        "COLLEGE_NAME",
        "VNR Vignana Jyothi Institute of Engineering and Technology",
    )
    COLLEGE_SHORT_NAME: str = os.getenv("COLLEGE_SHORT_NAME", "VNRVJIET")

    # ── OpenAI ────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_EMBEDDING_MODEL: str = os.getenv(
        "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
    )

    # ── Pinecone ──────────────────────────────────────────────
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "vnrvjiet-admissions")
    PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")

    # ── Server ────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:8000",
        ).split(",")
    ]

    # ── Rate limiting ─────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

    # ── Firebase Firestore ────────────────────────────────────
    FIREBASE_CREDENTIALS_JSON: str = os.getenv(
        "FIREBASE_CREDENTIALS_JSON",
        str(BASE_DIR / "data" / "firebase-service-account.json"),
    )
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")

    # ── Paths ─────────────────────────────────────────────────
    SYSTEM_PROMPT_PATH: str = str(BASE_DIR / "prompts" / "system_prompt.txt")

    # ── Web Search Fallback ───────────────────────────────────
    WEB_SEARCH_ENABLED: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
    
    # Key VNRVJIET website URLs for fallback search
    VNRVJIET_WEBSITE_URLS: dict[str, str] = {
        # Core pages
        "home": "https://vnrvjiet.ac.in/",
        "admissions": "https://vnrvjiet.ac.in/admission/",
        "international_admissions": "https://vnrvjiet.ac.in/international-admissions/",
        "departments": "https://vnrvjiet.ac.in/department/",
        
        # Academic & Support
        "syllabus": "https://vnrvjiet.ac.in/syllabus-books/",
        "academic_calendar": "https://vnrvjiet.ac.in/academic-calendar/",
        "library": "https://vnrvjiet.ac.in/library/",
        
        # Career & Training
        "placements": "https://vnrvjiet.ac.in/training-placement/",
        
        # Student Facilities
        "transport": "https://vnrvjiet.ac.in/transport/",
        "hostel": "https://www.vnrvjiet.ac.in/hostel",
        "campus": "https://www.vnrvjiet.ac.in/campus-life",
        "facilities": "https://www.vnrvjiet.ac.in/facilities",
        
        # Other
        "fees": "https://www.vnrvjiet.ac.in/admissions/fee-structure",
        "scholarship": "https://www.vnrvjiet.ac.in/admissions/scholarships",
        "about": "https://www.vnrvjiet.ac.in/about",
        "general": "https://vnrvjiet.ac.in/",
    }
    
    # Department-specific URLs
    DEPARTMENT_URLS: dict[str, str] = {
        "departments_overview": "https://vnrvjiet.ac.in/department/",
        "cse": "https://vnrvjiet.ac.in/cse/",
        "cse_aiml_iot": "https://vnrvjiet.ac.in/cse-aiml-and-iot/",
        "cse_ds_cys": "https://vnrvjiet.ac.in/cse-ds-and-cys/",
        "it": "https://vnrvjiet.ac.in/it/",
        "mech": "https://vnrvjiet.ac.in/mech/",
        "civil": "https://vnrvjiet.ac.in/civil/",
        "ece": "https://vnrvjiet.ac.in/ece/",
        "eee": "https://vnrvjiet.ac.in/eee/",
        "eie": "https://vnrvjiet.ac.in/eie/",
        "physics": "https://vnrvjiet.ac.in/physics/",
        "mathematics": "https://vnrvjiet.ac.in/mathematics-and-management-sciences/",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
