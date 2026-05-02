"""
VNRVJIET Site with Embedded Chatbot – FastAPI application.
Port 8001: VNR admissions site with chatbot widget embedded.

This app serves the VNRVJIET admissions page with a floating chatbot widget
that fetches from localhost:8000.

Run locally with uvicorn:
    uvicorn app.site_app:app --port 8001 --reload
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("app.site_app")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
FULL_SITE_SOURCE = BASE_DIR / "VNRVJIET-admiison-site.html"
FULL_SITE_ASSETS_DIR = BASE_DIR / "VNRVJIET-admiison-site_files"

settings = get_settings()

app = FastAPI(
    title="VNRVJIET Admissions Site",
    description="VNRVJIET admissions page with embedded chatbot widget",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Serve static assets ───────────────────────────────────────
if FULL_SITE_ASSETS_DIR.exists():
    app.mount(
        "/VNRVJIET-admiison-site_files",
        StaticFiles(directory=str(FULL_SITE_ASSETS_DIR)),
        name="site-assets",
    )


@app.get("/", response_class=HTMLResponse)
async def vnr_with_chatbot():
    """Serve the VNR admissions page with chatbot modal."""
    if not FULL_SITE_SOURCE.exists():
        return HTMLResponse("<h1>Admissions site not found</h1>", status_code=404)

    html = FULL_SITE_SOURCE.read_text(encoding="utf-8")

    # Add chatbot modal if not already present
    if 'id="vnr-chat-button"' not in html:
        chat_modal = """
        <style>
          #vnr-chat-button {
            position: fixed;
            bottom: 28px;
            right: 28px;
            width: 62px;
            height: 62px;
            border-radius: 50%;
            background: linear-gradient(135deg, #1a237e, #3949ab);
            cursor: pointer;
            box-shadow: 0 6px 20px rgba(26, 35, 126, 0.45);
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            border: none;
            padding: 0;
          }

          #vnr-chat-button:hover {
            transform: scale(1.08);
            box-shadow: 0 8px 25px rgba(26, 35, 126, 0.55);
          }

          #vnr-chat-button.open {
            transform: scale(0.94);
            box-shadow: 0 4px 16px rgba(26, 35, 126, 0.35);
          }

          #vnr-chat-button svg {
            width: 28px;
            height: 28px;
            fill: white;
          }

          /* Chat Modal */
          #vnr-chat-modal {
            position: fixed;
            bottom: 98px;
            right: 20px;
            width: min(420px, calc(100vw - 40px));
            height: min(680px, calc(100vh - 130px));
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
            z-index: 9998;
            display: none;
            flex-direction: column;
            opacity: 0;
            transform: scale(0.96) translateY(12px);
            transition: opacity 0.25s ease, transform 0.25s ease;
            background: #fff;
            border: 1px solid rgba(26, 35, 126, 0.12);
          }

          #vnr-chat-modal.open {
            display: flex;
            opacity: 1;
            transform: scale(1) translateY(0);
          }

          #vnr-chat-modal iframe {
            flex: 1;
            border: none;
            width: 100%;
            height: 100%;
            display: block;
          }

          /* Mobile */
          @media (max-width: 480px) {
            #vnr-chat-button {
              bottom: 18px;
              right: 18px;
              width: 56px;
              height: 56px;
            }

            #vnr-chat-modal {
              bottom: 0 !important;
              right: 0 !important;
              width: 100vw !important;
              height: 100vh !important;
              border-radius: 0 !important;
            }

            #vnr-chat-button {
              z-index: 10000;
            }
          }
        </style>

        <!-- Chat Button -->
        <button id="vnr-chat-button" onclick="toggleChatModal()" title="Open Admissions Chat">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.02 2 11c0 2.67 1.19 5.07 3.08 6.74L4 22l4.54-1.51C9.61 20.83 10.78 21 12 21c5.52 0 10-4.02 10-9S17.52 2 12 2z"/>
          </svg>
        </button>

        <!-- Chat Modal -->
        <div id="vnr-chat-modal">
          <iframe src="{chatbot_url}?fullscreen=true" title="VNRVJIET Admissions Chat" sandbox="allow-scripts allow-forms allow-popups"></iframe>
        </div>

        <script>
          function toggleChatModal() {
            var modal = document.getElementById('vnr-chat-modal');
            var button = document.getElementById('vnr-chat-button');
            if (modal.classList.contains('open')) {
              modal.style.opacity = '0';
              modal.style.transform = 'scale(0.95) translateY(10px)';
              setTimeout(() => {
                modal.classList.remove('open');
                if (button) {
                  button.classList.remove('open');
                  button.setAttribute('aria-expanded', 'false');
                }
              }, 250);
            } else {
              modal.classList.add('open');
              if (button) {
                button.classList.add('open');
                button.setAttribute('aria-expanded', 'true');
              }
              setTimeout(() => {
                modal.style.opacity = '1';
                modal.style.transform = 'scale(1) translateY(0)';
              }, 10);
            }
          }

          // Close modal when pressing Escape key
          document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
              var modal = document.getElementById('vnr-chat-modal');
              if (modal.classList.contains('open')) {
                toggleChatModal();
              }
            }
          });
        </script>
"""
        html = html.replace("</body>", f"{chat_modal}</body>", 1)

    # Replace placeholder with actual chatbot URL
    html = html.replace("{chatbot_url}", settings.CHATBOT_FULL_URL)

    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
