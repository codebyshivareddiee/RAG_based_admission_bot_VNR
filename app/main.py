"""
VNRVJIET Admissions Chatbot – FastAPI entry point.
Port 8000: Pure chatbot only (full-screen).

Run locally:
    python railway_start.py
"""

from __future__ import annotations

import logging
import sys
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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.data.init_db import init_db, get_db, COLLECTION, SEED_DATA
from app.logic.cutoff_cache import hydrate_cutoff_cache

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise datastore and hydrate local cutoff cache."""
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

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


@app.get("/", response_class=HTMLResponse)
async def root():
        """Serve the chatbot as a true full-viewport page on port 8000."""
        widget_path = FRONTEND_DIR / "widget.html"
        if not widget_path.exists():
                return HTMLResponse("<h1>Widget not found</h1>", status_code=404)

        widget_html = widget_path.read_text(encoding="utf-8")

        inject_style = """
        <style>
            html, body {
                width: 100%;
                height: 100%;
                margin: 0;
                overflow: hidden;
                background: #f5f7fb;
            }

            body.fullscreen-mode {
                width: 100vw;
                height: 100vh;
            }

            .fullscreen-mode .welcome-popup,
            .fullscreen-mode .chat-toggle {
                display: none !important;
            }

            .fullscreen-mode .chat-container {
                position: fixed !important;
                inset: 0 !important;
                width: 100vw !important;
                height: 100vh !important;
                max-height: none !important;
                border-radius: 0 !important;
                transform: none !important;
                opacity: 1 !important;
                pointer-events: auto !important;
                box-shadow: none !important;
            }
        </style>
        """

        inject_script = """
        <script>
            if (!window.location.search.includes('fullscreen=true')) {
                window.history.replaceState({}, '', window.location.pathname + '?fullscreen=true');
            }
        </script>
        """

        widget_html = widget_html.replace("<body>", '<body class="fullscreen-mode">', 1)
        widget_html = widget_html.replace("</head>", inject_style + "</head>", 1)
        widget_html = widget_html.replace("</body>", inject_script + "</body>")

        return HTMLResponse(
                widget_html,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
