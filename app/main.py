"""
VNRVJIET Admissions Chatbot – FastAPI entry point.

Run locally:
    python railway_start.py
"""

from __future__ import annotations

import logging
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("app.main")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.data.init_db import init_db, get_db, COLLECTION, SEED_DATA
from app.logic.cutoff_cache import hydrate_cutoff_cache

settings = get_settings()

FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise datastore and hydrate local cutoff cache."""
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Don't re-raise — let the server start even if DB init fails

    try:
        source = hydrate_cutoff_cache(
            get_db_func=get_db,
            collection_name=COLLECTION,
            snapshot_path=settings.CUTOFF_SNAPSHOT_PATH,
            fallback_rows=SEED_DATA,
        )
        logger.info("Cutoff cache hydrated from %s", source)
    except Exception as e:
        logger.error(f"Cutoff cache hydration failed: {e}")
    yield


app = FastAPI(
    title=f"{settings.COLLEGE_SHORT_NAME} Admissions Chatbot",
    description=(
        f"Hybrid RAG + Rule-based admissions assistant for "
        f"{settings.COLLEGE_NAME}"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(admin_router, tags=["Admin"])

# ── Serve frontend static files ──────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/widget", response_class=HTMLResponse)
async def widget():
    """Serve the chat widget HTML (embedded via iframe on college website)."""
    widget_path = FRONTEND_DIR / "widget.html"
    if not widget_path.exists():
        return HTMLResponse("<h1>Widget not found</h1>", status_code=404)
    return HTMLResponse(
        widget_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/")
async def root():
    """Landing page / health check."""
    return {
        "service": f"{settings.COLLEGE_SHORT_NAME} Admissions Chatbot",
        "status": "running",
        "docs": "/docs",
        "widget": "/widget",
    }
