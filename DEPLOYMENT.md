# VNRVJIET Admissions Chatbot – Complete Deployment Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Local Development](#local-development)
3. [Environment Variables](#environment-variables)
4. [Docker Deployment](#docker-deployment)
5. [Railway.app Deployment](#railwayapp-deployment)
6. [Heroku Deployment](#heroku-deployment)
7. [Production Deployment](#production-deployment)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The application consists of **two separate FastAPI applications** running on different ports:

### Port 8000: Pure Chatbot (Main App)
- **Entry Point**: `app/main.py`
- **Launcher**: `python railway_start.py`
- **Purpose**: Full-screen chatbot interface
- **Features**:
  - Fullscreen chat UI
  - All chat API endpoints (`/api/chat`, `/api/admin`)
  - Database initialization on startup
  - Cutoff cache hydration
  - Static assets at `/static/`

### Port 8001: VNR Admissions Site with Widget (Site App)
- **Entry Point**: `app/site_app.py`
- **Launcher**: `uvicorn app.site_app:app --port 8001`
- **Purpose**: Static admissions page with embedded chatbot widget
- **Features**:
  - VNRVJIET admissions information
  - Floating chat widget (bottom-right corner)
  - Widget iframe fetches from Port 8000
  - Lightweight, no AI processing
  - Responsive mobile design

### Communication Flow
```
User visits site → Port 8001 (Static HTML + CSS)
                      ↓
                   Widget loaded
                      ↓
                   iframe src → Port 8000
                      ↓
                   Port 8000 serves chatbot UI + API
```

---

## Local Development

### Prerequisites
- Python 3.12 or higher
- pip or pipenv
- Virtual environment (recommended)

### Setup

1. **Clone and navigate to project:**
```bash
cd admission-bot
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Create `.env` file** (see [Environment Variables](#environment-variables) section)

5. **Run both applications:**

**Terminal 1 - Main Chatbot (Port 8000):**
```bash
python railway_start.py
```

**Terminal 2 - Site App (Port 8001):**
```bash
python site_app_start.py
```

6. **Access locally:**
- Chatbot: `http://localhost:8000/`
- Site with Widget: `http://localhost:8001/`

### Running Individual Apps

**Only chatbot:**
```bash
python railway_start.py
# Access: http://localhost:8000/
```

**Only site:**
```bash
python site_app_start.py
# Access: http://localhost:8001/
```

### Testing

```bash
python -m pytest tests/ -v
```

---

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-...your-openai-key...
OPENAI_MODEL=gpt-4o-mini

# Pinecone Configuration
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX=your-index-name
PINECONE_ENVIRONMENT=your-region

# Firebase Configuration
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}
# Or use:
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY_ID=your-key-id
FIREBASE_PRIVATE_KEY=your-private-key
FIREBASE_CLIENT_EMAIL=your-email@project.iam.gserviceaccount.com
FIREBASE_CLIENT_ID=your-client-id
FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token

# Database
DATABASE_URL=your-mongodb-uri

# Google Sheets (optional)
GOOGLE_SHEETS_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_SHEETS_ID=your-sheet-id

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Cutoff Snapshot (for caching)
CUTOFF_SNAPSHOT_PATH=./data/cutoff_snapshot.json

# Feature Flags
ENABLE_ANALYTICS=true
MAX_TOKENS=2000
```

### Environment Variable Requirements by Component

| Variable | Default | Required For | Description |
|----------|---------|--------------|-------------|
| `HOST` | "" | Both | Bind address (0.0.0.0 for all interfaces) |
| `PORT` | 0 | Main Chatbot | Port for chatbot app (defaults to 8000 if not set elsewhere) |
| `SITE_PORT` | 8001 | Site App | Port for admissions site app |
| `CHATBOT_FULL_URL` | http://localhost:8000/ | Site App | Full URL for widget iframe (where chatbot is served from) |
| `OPENAI_API_KEY` | (required) | Main Chatbot | OpenAI API access for chat responses |
| `PINECONE_API_KEY` | (required) | Main Chatbot | Vector DB for RAG |
| `FIREBASE_*` | (required) | Main Chatbot | User authentication & storage |
| `DATABASE_URL` | (required) | Main Chatbot | MongoDB connection string |

---

## Docker Deployment

### Build Docker Image

```bash
docker build -t vnrvjiet-chatbot:latest .
```

### Run Single Container (Main Chatbot)

```bash
docker build -t vnrvjiet-chatbot:latest .
docker run -d \
  --name vnrvjiet-chatbot \
  -p 8000:8000 \
  -e PORT=8000 \
  -e HOST=0.0.0.0 \
  --env-file .env \
  vnrvjiet-chatbot:latest
```

### Run Both Apps with Docker Compose

**`docker-compose.yml` includes:**
- **chatbot service**: Main app on PORT (default 8000)
- **site service**: Admissions site on SITE_PORT (default 8001)
- Auto health checks
- Service dependencies
- Environment variable support

**Start services:**
```bash
docker-compose up -d
```

**Override ports with environment variables:**
```bash
PORT=9000 SITE_PORT=9001 docker-compose up -d
```

**View logs:**
```bash
docker-compose logs -f chatbot  # Main app
docker-compose logs -f site     # Site app
docker-compose logs -f          # Both
```

**Stop services:**
```bash
docker-compose down
```

### Health Check

```bash
curl http://localhost:8000/api/health
# Expected: {"status":"healthy"}
```

---

## Railway.app Deployment

### Why Railway?
- ✅ Easy GitHub integration (CI/CD)
- ✅ Automatic deployments on push
- ✅ Built-in environment variable management
- ✅ Simple scaling
- ✅ Support for multiple services

### Setup Steps

1. **Create Railway.app Account:**
   - Go to [railway.app](https://railway.app)
   - Sign up with GitHub

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Authorize and select `admission-bot` repo

3. **Configure Service:**
   - Service name: `vnrvjiet-chatbot`
   - Builder: NIXPACKS (auto-detected)
   - Start command: `python railway_start.py`

4. **Set Environment Variables:**
   - In Railway dashboard, navigate to "Variables"
   - Add all variables from `.env` file
   - **Critically important for production:**
     - `PORT=8000`
     - `SITE_PORT=8001` 
     - `CHATBOT_FULL_URL=https://yourdomain-chatbot.up.railway.app/`
     - `HOST=0.0.0.0`
     - `OPENAI_API_KEY`, `PINECONE_API_KEY`, database credentials
     - `ALLOWED_ORIGINS=https://yourdomain.com`

5. **Deploy:**
   - Railway automatically deploys on git push
   - Monitor deployment in "Deployments" tab

6. **Access Your Chatbot:**
   - Railway generates a public URL
   - Example: `https://vnrvjiet-chatbot-prod.up.railway.app`

### Domain Configuration (Optional)

1. **Add Custom Domain:**
   - Railway Dashboard → Project Settings
   - Custom Domains → Add Domain
   - Update DNS records at your domain provider

2. **Example:**
   ```
   CNAME: chatbot.yourdomain.com → vn...railway.app
   ```

### Railway Configuration File

The `railway.toml` file controls deployment:

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python railway_start.py"
healthcheckPath = "/"
healthcheckTimeout = 100
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

---

## Heroku Deployment

### Setup Steps

1. **Install Heroku CLI:**
   ```bash
   # macOS
   brew tap heroku/brew && brew install heroku
   
   # Windows
   # Download from https://devcenter.heroku.com/articles/heroku-cli
   ```

2. **Login to Heroku:**
   ```bash
   heroku login
   ```

3. **Create Heroku App:**
   ```bash
   heroku create vnrvjiet-chatbot
   ```

4. **Configure Buildpack:**
   ```bash
   heroku buildpacks:add heroku/python
   ```

5. **Set Environment Variables:**
   ```bash
   heroku config:set OPENAI_API_KEY=sk-...
   heroku config:set PINECONE_API_KEY=...
   heroku config:set DATABASE_URL=...
   # ... set all other variables
   ```

   Or use:
   ```bash
   heroku config:set $(cat .env | xargs)
   ```

6. **Deploy:**
   ```bash
   git push heroku main
   # or git push heroku master
   ```

7. **View Logs:**
   ```bash
   heroku logs --tail
   ```

8. **Open App:**
   ```bash
   heroku open
   ```

### Procfile

The `Procfile` specifies the startup command:

```
web: python railway_start.py
```

Heroku automatically uses this to start your app.

### Scaling (Optional)

```bash
# Scale to 2 dynos
heroku ps:scale web=2

# Check status
heroku ps
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All environment variables configured
- [ ] Database migrations completed
- [ ] CORS origins restricted (remove "*" if possible)
- [ ] Security headers configured
- [ ] Rate limiting enabled
- [ ] API keys rotated
- [ ] Monitoring/logging setup
- [ ] Backup strategy in place
- [ ] SSL/TLS certificate installed
- [ ] Health checks configured

### Critical Changes for Production

#### 1. Update Chatbot URL for Production

**For Site App to find the Chatbot:**
```bash
# Set CHATBOT_FULL_URL to your actual domain
# This is used in the iframe src in Port 8001

# .env or environment variable:
CHATBOT_FULL_URL=https://api.yourdomain.com/

# Or if on same domain:
CHATBOT_FULL_URL=https://yourdomain.com/
```

#### 2. Configure Ports for Production

```python
# BEFORE (development)
CORSMiddleware(
    allow_origins=["*"],
    ...
)

# AFTER (production)
CORSMiddleware(
    allow_origins=[
        "https://yourdomain.com",
        "https://api.yourdomain.com",
    ],
    ...
)
```

#### 3. Set Debug Mode to False

```env
DEBUG=false
```

#### 4. Configure Logging

```python
LOG_LEVEL=INFO
# Use cloud logging (e.g., CloudLogging, DataDog)
```

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Your Domain                          │
│              yourdomain.com                             │
└─────────────────────────────────────────────────────────┘
             │                              │
             ├─ /              ────────────┤
             │                              │
             └──────────────────────────────┤
                          ▼
         ┌──────────────────────────────────┐
         │  Nginx/Reverse Proxy (SSL)       │
         │  Port 443 → Port 8000 & 8001     │
         └──────────────────────────────────┘
             │                    │
    ┌────────┘                    └────────┐
    │                                      │
    ▼                                      ▼
┌─────────────────────────┐    ┌──────────────────────┐
│  Main Chatbot App       │    │  Site App            │
│  Port 8000              │    │  Port 8001           │
│  (FastAPI + RAG + LLM)  │    │  (Static + Widget)   │
└─────────────────────────┘    └──────────────────────┘
    │                                      │
    └──────────────┬───────────────────────┘
                   │
    ┌──────────────┴───────────────────────┐
    │                                      │
    ▼                                      ▼
┌─────────────────────────┐    ┌──────────────────────┐
│ Pinecone (Vector DB)    │    │ Firebase (Auth/DB)   │
│                         │    │                      │
└─────────────────────────┘    └──────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ OpenAI API              │
│ (LLM Service)           │
└─────────────────────────┘
```

### Deployment Options

#### Option 1: Railway.app (Recommended)
- **Pros**: Simple, GitHub integration, auto-scaling
- **Cons**: Vendor lock-in
- **Cost**: Pay-as-you-go (~$5-20/month for typical usage)

#### Option 2: Heroku
- **Pros**: Established platform, many add-ons
- **Cons**: Higher cost (~$7+/month minimum)
- **Cost**: Expensive for free tier removal

#### Option 3: Docker on VPS (AWS, DigitalOcean, etc.)
- **Pros**: Full control, better pricing for scale
- **Cons**: More maintenance required
- **Cost**: $5-20/month for basic VPS

#### Option 4: Kubernetes (GKE, EKS)
- **Pros**: Production-grade scaling
- **Cons**: Complex, overkill for single app
- **Cost**: Highly variable

---

## Monitoring & Logs

### Railway.app Logs
```bash
# In Railway Dashboard:
# Project → Services → Deployments → View Logs
```

### Heroku Logs
```bash
heroku logs --tail
```

### Docker Logs
```bash
docker-compose logs -f chatbot
```

### Health Check Endpoints

Both apps expose:
- `GET /` - Returns HTML (health check)
- `GET /api/health` - Returns JSON status

```bash
curl https://yourdomain.com/api/health
# {"status":"healthy","timestamp":"2024-05-01..."}
```

---

## Scaling Considerations

### For Increased Traffic

1. **Chatbot App (Port 8000):**
   - Scale horizontally with load balancer
   - Use connection pooling for database
   - Enable rate limiting
   - Cache frequently asked questions

2. **Site App (Port 8001):**
   - Use CDN for static assets (CloudFlare, Bunny)
   - Enable browser caching headers
   - Compress HTML/CSS/JS

### Database Optimization

- Index frequently queried fields
- Enable read replicas for scaling
- Archive old conversations

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

### Missing Environment Variables

```
Error: KeyError: 'OPENAI_API_KEY'
```

**Solution:**
- Verify `.env` file exists
- Run: `python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.environ)"`
- Ensure no typos in variable names

### Database Connection Failed

```
Error: pymongo.errors.ServerSelectionTimeoutError
```

**Solution:**
- Check `DATABASE_URL` is correct
- Verify IP whitelist in MongoDB Atlas
- Test connection: `mongosh $DATABASE_URL`

### Widget Not Loading

```
GET https://yourdomain.com/static/widget.js 404
```

**Solution:**
- Verify static files exist in `app/frontend/`
- Check nginx/proxy config routes `/static/` to port 8000
- Inspect Network tab in DevTools

### CORS Errors

```
Access to XMLHttpRequest blocked by CORS policy
```

**Solution:**
- Update `allow_origins` in app to match your domain
- Ensure CORS middleware is enabled
- Check browser console for actual origin

### High Memory Usage

**Solution:**
- Enable request/response caching
- Implement pagination for large datasets
- Use streaming for large file uploads
- Monitor with: `docker stats`

---

## Support & Resources

- **Documentation**: See `README.md`
- **Issues**: Check GitHub issues
- **Contact**: admissions@vnrvjiet.in

---

## Deployment Checklist - Quick Reference

| Component | Local Dev | Docker | Railway | Heroku |
|-----------|-----------|--------|---------|--------|
| Port 8000 (Chatbot) | `python railway_start.py` | `docker-compose up` | Auto | `git push heroku` |
| Port 8001 (Site) | `python site_app_start.py` | `docker-compose up` | (separate app) | (separate app) |
| PORT env var | 8000 | from .env | Dashboard | `heroku config` |
| SITE_PORT env var | 8001 | from .env | Dashboard | `heroku config` |
| CHATBOT_FULL_URL | http://localhost:8000 | from .env | https://your-domain | Dashboard |
| Deployment | Manual | Manual | Auto on push | `git push heroku` |
| Scaling | N/A | Manual | Auto | Manual |
| Cost | Free | Free | ~$5-20 | ~$7+ |
