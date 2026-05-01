# Separated Port Deployment

## Overview
The application is now split into **two separate FastAPI apps** running on different ports:

### Port 8000: Pure Chatbot
- **Route**: `http://localhost:8000/`
- **Description**: Full-screen chatbot only
- **Features**: 
  - Pure chat interface fills entire viewport
  - No topbar, no navigation, no extra UI
  - Fullscreen mode enabled by default
  - Includes all API endpoints for chat functionality

### Port 8001: VNR Admissions Site with Embedded Chatbot
- **Route**: `http://localhost:8001/`
- **Description**: VNRVJIET admissions page with floating chatbot widget
- **Features**:
  - Static admissions page
  - Floating chat widget in bottom-right corner
  - Widget fetches from localhost:8000
  - Responsive design for mobile/tablet

---

## Running Both Apps

### Option 1: Run Main App (Port 8000)
```bash
# Terminal 1 - Pure Chatbot on Port 8000
python railway_start.py
```

### Option 2: Run Site App (Port 8001)
```bash
# Terminal 2 - VNR Site with Widget on Port 8001
uvicorn app.site_app:app --port 8001 --reload
```

### Option 3: Run Both Simultaneously
```bash
# Terminal 1
python railway_start.py  # Runs on port 8000

# Terminal 2
uvicorn app.site_app:app --port 8001 --reload  # Runs on port 8001
```

---

## File Structure

- **`app/main.py`** - Port 8000 app (pure chatbot only)
  - Route `/` → Serves widget in fullscreen mode
  - Static files at `/static/`
  - API endpoints at `/api/chat`, `/api/admin`

- **`app/site_app.py`** - Port 8001 app (VNR site with widget)
  - Route `/` → VNR admissions page with embedded chatbot widget
  - Static files at `/VNRVJIET-admiison-site_files/`
  - Widget iframe src points to `http://localhost:8000`

---

## Testing

Run tests for the main chatbot app:
```bash
python -m pytest tests/test_site_routes.py -v
```

---

## Deployment Notes

- **For production**: Update `http://localhost:8000` to your actual domain in `app/site_app.py`
- **CORS is enabled** on both apps for cross-origin requests
- Both apps use the same `/static` assets and database connection
- The site app (8001) is lightweight and doesn't need the full API infrastructure

---

## URLs Summary

| Port | URL | Purpose |
|------|-----|---------|
| **8000** | `http://localhost:8000/` | Pure full-screen chatbot |
| **8001** | `http://localhost:8001/` | VNR site with embedded chatbot widget |
