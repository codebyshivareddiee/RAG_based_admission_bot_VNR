"""
Railway startup script - reads PORT from environment and starts uvicorn
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

    raw_port = os.environ.get("PORT") or os.environ.get("APP_PORT")
    if not raw_port:
        raise RuntimeError("PORT or APP_PORT environment variable is required (set it in .env or shell env)")

    port = int(raw_port)
    print(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info"
    )
