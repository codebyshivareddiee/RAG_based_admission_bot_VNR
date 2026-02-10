# VNRVJIET Admissions Chatbot

A production-ready, hybrid **RAG + Rule-based** admissions chatbot for **VNR Vignana Jyothi Institute of Engineering and Technology (VNRVJIET)**, with a website-embeddable floating chat widget.

---

## Architecture

```
College Website
   ↓
Floating Chat Button (iframe)
   ↓
FastAPI Backend
   ↓
Query Classifier (rule-based)
   ↓
 ┌───────────────────┬────────────────────┐
 │ Cutoff Engine      │  RAG Retrieval     │
 │ (SQLite – exact)   │  (Pinecone + OpenAI)│
 └───────────────────┴────────────────────┘
        ↓
   Controlled LLM (GPT-4o-mini)
```

## Features

- **Hybrid pipeline**: Structured cutoff queries via SQLite; informational queries via Pinecone RAG
- **Strict college scope**: Only answers about VNRVJIET; refuses other colleges
- **Intent classifier**: Greeting / informational / cutoff / mixed / out-of-scope
- **Floating chat widget**: Embeddable via iframe, mobile-responsive, collapsible
- **Security**: CORS whitelisting, rate limiting, input sanitisation, sandboxed iframe
- **Production-ready**: Docker, environment-variable config, no exposed secrets

## Project Structure

```
admission-bot/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Centralised settings
│   ├── api/
│   │   └── chat.py                # /api/chat endpoint + orchestrator
│   ├── classifier/
│   │   └── intent_classifier.py   # Rule-based intent detection
│   ├── logic/
│   │   └── cutoff_engine.py       # SQLite cutoff & eligibility engine
│   ├── rag/
│   │   ├── ingest.py              # Document → Pinecone ingestion
│   │   └── retriever.py           # Pinecone retrieval with college filter
│   ├── prompts/
│   │   └── system_prompt.txt      # LLM system prompt with guardrails
│   ├── data/
│   │   └── init_db.py             # DB schema + seed data
│   ├── frontend/
│   │   ├── widget.html            # Chat widget page
│   │   ├── widget.css             # Widget styles
│   │   └── widget.js              # Widget logic
│   └── utils/
│       └── validators.py          # Input sanitisation & entity extraction
├── tests/
│   └── test_chatbot.py            # Pytest test suite
├── docs/
│   └── vnrvjiet_admissions.txt    # Sample RAG source document
├── embed_snippet.html             # Copy-paste embed code for website
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Quick Start

### 1. Clone & configure

```bash
cd admission-bot
cp .env.example .env
# Edit .env with your OpenAI and Pinecone API keys
```

### 2. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

### 3. Initialise the cutoff database

```bash
python -m app.data.init_db
```

### 4. Ingest documents into Pinecone

```bash
# Place your docs (PDF, TXT, MD) in the docs/ folder, then:
python -m app.rag.ingest --docs-dir docs --source website --year 2025
```

### 5. Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open the widget

Visit **http://localhost:8000/widget** in your browser.

API docs at **http://localhost:8000/docs**.

## Docker Deployment

```bash
docker-compose up -d --build
```

## Embed on College Website

Add to any page on `vnrvjiet.ac.in`:

```html
<iframe
  src="https://YOUR_DOMAIN/widget"
  style="position:fixed;bottom:0;right:0;width:420px;height:640px;border:none;z-index:9999;"
  sandbox="allow-scripts allow-same-origin allow-forms"
  title="VNRVJIET Admissions Chat"
></iframe>
```

See `embed_snippet.html` for more options.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, get a response |
| GET | `/api/health` | Health check |
| GET | `/api/branches` | List available branches |
| GET | `/widget` | Chat widget HTML page |
| GET | `/docs` | Swagger API documentation |

### POST `/api/chat`

```json
{
  "message": "What is the CSE cutoff for OC category?",
  "session_id": "optional-session-id"
}
```

Response:

```json
{
  "reply": "The closing cutoff rank for CSE under OC category in Year 2025, Round 1 (Convenor quota) was **3,500**.",
  "intent": "cutoff",
  "session_id": "s_abc12345",
  "sources": ["VNRVJIET Cutoff Database"]
}
```

## Running Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `COLLEGE_NAME` | Full college name | VNR Vignana Jyothi... |
| `COLLEGE_SHORT_NAME` | Short name | VNRVJIET |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `OPENAI_MODEL` | Chat model | gpt-4o-mini |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | text-embedding-3-small |
| `PINECONE_API_KEY` | Pinecone API key | — |
| `PINECONE_INDEX_NAME` | Pinecone index | vnrvjiet-admissions |
| `PINECONE_ENVIRONMENT` | Pinecone region | us-east-1 |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | localhost |
| `RATE_LIMIT_PER_MINUTE` | Max requests/min/IP | 30 |
| `CUTOFF_DB_PATH` | SQLite database path | app/data/cutoffs.db |

## Adding Real Data

### Cutoff Data
Edit the `SEED_DATA` list in `app/data/init_db.py` with real TS EAMCET counselling cutoff data, then re-run:
```bash
python -m app.data.init_db
```

### RAG Documents
Place official admission documents (PDFs, text files) in the `docs/` directory and run the ingestion:
```bash
python -m app.rag.ingest --docs-dir docs --source pdf --year 2025
```

## License

Internal use — VNRVJIET.
