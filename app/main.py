"""
VNRVJIET Admissions Chatbot – FastAPI entry point.

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

# Configure logging FIRST so all subsequent messages are visible
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("app.main")
logger.info("====== STARTUP: main.py loading ======")

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    logger.info("OK: FastAPI imports succeeded")
except Exception as e:
    logger.error(f"FAILED: FastAPI imports: {e}")
    traceback.print_exc()
    raise

try:
    from app.config import get_settings
    logger.info("OK: app.config imported")
except Exception as e:
    logger.error(f"FAILED: app.config import: {e}")
    traceback.print_exc()
    raise

try:
    from app.api.chat import router as chat_router
    logger.info("OK: app.api.chat imported")
except Exception as e:
    logger.error(f"FAILED: app.api.chat import: {e}")
    traceback.print_exc()
    raise

try:
    from app.api.admin import router as admin_router
    logger.info("OK: app.api.admin imported")
except Exception as e:
    logger.error(f"FAILED: app.api.admin import: {e}")
    traceback.print_exc()
    raise

try:
    from app.data.init_db import init_db
    logger.info("OK: app.data.init_db imported")
except Exception as e:
    logger.error(f"FAILED: app.data.init_db import: {e}")
    traceback.print_exc()
    raise

try:
    settings = get_settings()
    logger.info(f"OK: Settings loaded (COLLEGE_SHORT_NAME={settings.COLLEGE_SHORT_NAME})")
    logger.info(f"    FIREBASE_PROJECT_ID={'SET' if settings.FIREBASE_PROJECT_ID else 'EMPTY'}")
    logger.info(f"    FIREBASE_CREDENTIALS_JSON={settings.FIREBASE_CREDENTIALS_JSON}")
    logger.info(f"    OPENAI_API_KEY={'SET' if settings.OPENAI_API_KEY else 'EMPTY'}")
    logger.info(f"    PINECONE_API_KEY={'SET' if settings.PINECONE_API_KEY else 'EMPTY'}")
except Exception as e:
    logger.error(f"FAILED: get_settings(): {e}")
    traceback.print_exc()
    raise

FRONTEND_DIR = Path(__file__).parent / "frontend"
logger.info(f"FRONTEND_DIR={FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise the cutoff database."""
    logger.info("====== LIFESPAN: starting init_db() ======")
    try:
        init_db()
        logger.info("====== LIFESPAN: init_db() succeeded ======")
    except Exception as e:
        logger.error(f"====== LIFESPAN: init_db() FAILED: {e} ======")
        traceback.print_exc()
        # Don't re-raise — let the server start even if DB init fails
        logger.warning("Continuing startup without database initialisation")
    yield
    logger.info("====== LIFESPAN: shutdown ======")


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
