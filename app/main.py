"""
VNRVJIET Admissions Chatbot – FastAPI entry point.

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.chat import router as chat_router
from app.data.init_db import init_db

# Configure logging so debug/info from our modules is visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()

FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise the cutoff database."""
    init_db()
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

# ── Serve frontend static files ──────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/widget", response_class=HTMLResponse)
async def widget():
    """Serve the chat widget HTML (embedded via iframe on college website)."""
    widget_path = FRONTEND_DIR / "widget.html"
    if not widget_path.exists():
        return HTMLResponse("<h1>Widget not found</h1>", status_code=404)
    return HTMLResponse(widget_path.read_text(encoding="utf-8"))


@app.get("/")
async def root():
    """Landing page / health check."""
    return {
        "service": f"{settings.COLLEGE_SHORT_NAME} Admissions Chatbot",
        "status": "running",
        "docs": "/docs",
        "widget": "/widget",
    }
