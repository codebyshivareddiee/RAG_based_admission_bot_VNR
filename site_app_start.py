"""
Site app startup script - reads SITE_PORT from environment and starts uvicorn
"""
import os
from pathlib import Path

from dotenv import load_dotenv

import uvicorn

if __name__ == "__main__":
    # Load project .env so local runs work without manually exporting vars.
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

    host = os.environ.get("HOST")
    if not host:
        raise RuntimeError("HOST environment variable is required (set it in .env or shell env)")

    raw_site_port = os.environ.get("SITE_PORT") or "8001"
    site_port = int(raw_site_port)
    print(f"Starting site server on {host}:{site_port}")
    
    uvicorn.run(
        "app.site_app:app",
        host=host,
        port=site_port,
        log_level="info"
    )
