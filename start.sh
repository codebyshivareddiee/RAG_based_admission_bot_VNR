#!/bin/bash
# Railway start script - uses dynamic PORT variable

exec uvicorn app.main:app --host "${HOST:?HOST is required}" --port "${PORT:-${APP_PORT:?PORT or APP_PORT is required}}"
