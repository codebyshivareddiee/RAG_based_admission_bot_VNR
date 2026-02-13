"""
Firebase Firestore cutoff database initialisation & seeding.

Run this module directly to seed Firestore with sample data:
    python -m app.data.init_db

Prerequisites:
    1. Create a Firebase project at https://console.firebase.google.com
    2. Enable Firestore Database (start in production mode)
    3. Go to Project Settings → Service Accounts → Generate New Private Key
    4. Save the JSON file as  app/data/firebase-service-account.json
    5. Set FIREBASE_PROJECT_ID in .env
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

logger = logging.getLogger("app.data.init_db")
logger.info("init_db.py: starting imports...")

logger.info("init_db.py: importing firebase_admin...")
import firebase_admin
logger.info("init_db.py: firebase_admin OK")

logger.info("init_db.py: importing firebase_admin.credentials...")
from firebase_admin import credentials
logger.info("init_db.py: credentials OK")

logger.info("init_db.py: importing firebase_admin.firestore...")
from firebase_admin import firestore
logger.info("init_db.py: firestore OK")

from app.config import get_settings

logger = logging.getLogger("app.data.init_db")

settings = get_settings()

# ── Firebase singleton ────────────────────────────────────────
_db = None


def _init_firebase():
    """Initialise Firebase Admin SDK (idempotent)."""
    if not firebase_admin._apps:
        cred_path = Path(settings.FIREBASE_CREDENTIALS_JSON)
        logger.info(f"Firebase credentials path: {cred_path}")
        logger.info(f"Firebase credentials file exists: {cred_path.exists()}")
        if not cred_path.exists():
            raise FileNotFoundError(
                f"Firebase credentials file not found at {cred_path}.\n"
                "Download it from Firebase Console → Project Settings → "
                "Service Accounts → Generate New Private Key."
            )
        logger.info("Loading Firebase credentials...")
        cred = credentials.Certificate(str(cred_path))
        logger.info(f"Initialising Firebase app (project={settings.FIREBASE_PROJECT_ID})...")
        firebase_admin.initialize_app(cred, {
            "projectId": settings.FIREBASE_PROJECT_ID,
        })
        logger.info("Firebase app initialised successfully")
    else:
        logger.info("Firebase app already initialised, reusing")


def get_db():
    """Return the Firestore client (singleton)."""
    global _db
    if _db is None:
        logger.info("Creating Firestore client...")
        try:
            _init_firebase()
            _db = firestore.client()
            logger.info("Firestore client created successfully")
        except Exception as e:
            logger.error(f"Failed to create Firestore client: {e}")
            traceback.print_exc()
            raise
    return _db


# ── Collection name ───────────────────────────────────────────
COLLECTION = "cutoffs"

# fmt: off
# Representative sample data for VNRVJIET (Telangana EAMCET)
# Replace / extend with real data from official counselling results.
SEED_DATA: list[dict] = [
    # ── CSE ────────────────────────────────────────────────────
    {"branch": "CSE", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 3500,  "quota": "Convenor"},
    {"branch": "CSE", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 4200,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 5800,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-A", "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 6500,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-B", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 7200,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-B", "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 8000,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-D", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 9500,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-D", "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 10200, "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-E", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 11000, "quota": "Convenor"},
    {"branch": "CSE", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 18000, "quota": "Convenor"},
    {"branch": "CSE", "category": "SC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 20000, "quota": "Convenor"},
    {"branch": "CSE", "category": "ST",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 32000, "quota": "Convenor"},
    {"branch": "CSE", "category": "EWS",  "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 6000,  "quota": "Convenor"},

    # ── ECE ────────────────────────────────────────────────────
    {"branch": "ECE", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 8000,  "quota": "Convenor"},
    {"branch": "ECE", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 9500,  "quota": "Convenor"},
    {"branch": "ECE", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 12000, "quota": "Convenor"},
    {"branch": "ECE", "category": "BC-B", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 14500, "quota": "Convenor"},
    {"branch": "ECE", "category": "BC-D", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 17000, "quota": "Convenor"},
    {"branch": "ECE", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 28000, "quota": "Convenor"},
    {"branch": "ECE", "category": "ST",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 45000, "quota": "Convenor"},
    {"branch": "ECE", "category": "EWS",  "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 11000, "quota": "Convenor"},

    # ── EEE ────────────────────────────────────────────────────
    {"branch": "EEE", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 15000, "quota": "Convenor"},
    {"branch": "EEE", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 17000, "quota": "Convenor"},
    {"branch": "EEE", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 20000, "quota": "Convenor"},
    {"branch": "EEE", "category": "BC-B", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 23000, "quota": "Convenor"},
    {"branch": "EEE", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 38000, "quota": "Convenor"},
    {"branch": "EEE", "category": "ST",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 55000, "quota": "Convenor"},

    # ── IT ─────────────────────────────────────────────────────
    {"branch": "IT", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 5500,  "quota": "Convenor"},
    {"branch": "IT", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 6800,  "quota": "Convenor"},
    {"branch": "IT", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 9000,  "quota": "Convenor"},
    {"branch": "IT", "category": "BC-B", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 11000, "quota": "Convenor"},
    {"branch": "IT", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 22000, "quota": "Convenor"},
    {"branch": "IT", "category": "ST",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 38000, "quota": "Convenor"},

    # ── MECH ──────────────────────────────────────────────────
    {"branch": "MECH", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 30000, "quota": "Convenor"},
    {"branch": "MECH", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 35000, "quota": "Convenor"},
    {"branch": "MECH", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 40000, "quota": "Convenor"},
    {"branch": "MECH", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 55000, "quota": "Convenor"},

    # ── CIVIL ─────────────────────────────────────────────────
    {"branch": "CIVIL", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 42000, "quota": "Convenor"},
    {"branch": "CIVIL", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 48000, "quota": "Convenor"},
    {"branch": "CIVIL", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 52000, "quota": "Convenor"},
    {"branch": "CIVIL", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 65000, "quota": "Convenor"},

    # ── CSE (AI & ML) ─────────────────────────────────────────
    {"branch": "CSE (AI & ML)", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 4000,  "quota": "Convenor"},
    {"branch": "CSE (AI & ML)", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 5000,  "quota": "Convenor"},
    {"branch": "CSE (AI & ML)", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 6500,  "quota": "Convenor"},
    {"branch": "CSE (AI & ML)", "category": "BC-B", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 8500,  "quota": "Convenor"},
    {"branch": "CSE (AI & ML)", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 19000, "quota": "Convenor"},

    # ── CSE (Data Science) ────────────────────────────────────
    {"branch": "CSE (Data Science)", "category": "OC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 4500,  "quota": "Convenor"},
    {"branch": "CSE (Data Science)", "category": "OC",   "year": 2025, "round": 2, "gender": "Any", "cutoff_rank": 5500,  "quota": "Convenor"},
    {"branch": "CSE (Data Science)", "category": "BC-A", "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 7500,  "quota": "Convenor"},
    {"branch": "CSE (Data Science)", "category": "SC",   "year": 2025, "round": 1, "gender": "Any", "cutoff_rank": 20000, "quota": "Convenor"},

    # ── 2024 data (historical comparison) ─────────────────────
    {"branch": "CSE", "category": "OC",   "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 3200,  "quota": "Convenor"},
    {"branch": "CSE", "category": "OC",   "year": 2024, "round": 2, "gender": "Any", "cutoff_rank": 3900,  "quota": "Convenor"},
    {"branch": "CSE", "category": "BC-A", "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 5500,  "quota": "Convenor"},
    {"branch": "CSE", "category": "SC",   "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 17000, "quota": "Convenor"},
    {"branch": "ECE", "category": "OC",   "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 7500,  "quota": "Convenor"},
    {"branch": "ECE", "category": "BC-A", "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 11000, "quota": "Convenor"},
    {"branch": "IT",  "category": "OC",   "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 5000,  "quota": "Convenor"},
    {"branch": "IT",  "category": "BC-A", "year": 2024, "round": 1, "gender": "Any", "cutoff_rank": 8500,  "quota": "Convenor"},
]
# fmt: on


def _doc_id(row: dict) -> str:
    """Generate a deterministic document ID for deduplication."""
    return (
        f"{row['branch']}_{row['category']}_{row['year']}_"
        f"R{row['round']}_{row['gender']}_{row['quota']}"
    ).replace(" ", "-").replace("(", "").replace(")", "")


def init_db() -> None:
    """Seed Firestore with cutoff data (idempotent – uses set with merge)."""
    db = get_db()
    batch = db.batch()
    count = 0

    for row in SEED_DATA:
        doc_ref = db.collection(COLLECTION).document(_doc_id(row))
        batch.set(doc_ref, row, merge=True)
        count += 1

        # Firestore batch limit is 500
        if count % 450 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    print(f"✅  Seeded {count} cutoff records to Firestore collection '{COLLECTION}'")


if __name__ == "__main__":
    init_db()
