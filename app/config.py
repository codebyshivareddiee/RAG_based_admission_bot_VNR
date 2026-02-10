"""
Centralised configuration loaded from environment variables.
All secrets stay in .env – never hard-coded.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
