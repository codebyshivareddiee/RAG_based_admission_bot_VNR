# VNRVJIET Admissions Chatbot

A production-ready, hybrid **RAG + Rule-based** admissions chatbot for **VNR Vignana Jyothi Institute of Engineering and Technology (VNRVJIET)**, with a website-embeddable floating chat widget.

---

## ⚠️ OFFICIAL NOTICE - ANTI-FRAUD WARNING

**ATTENTION:** VNRVJIET does not engage any **Agents or Consultants** for admissions to **Category B & NRI seats**. We strictly follow Government guidelines to fill the seats. 

**Do not be misled by fraudsters.** 

If anyone claims they can get you a seat, please report the fraud immediately:
- **🚨 Fraud Reporting:** +91 9391982884 (ONLY for reporting illegal agents/scams)
- **Email:** postbox@vnrvjiet.ac.in

**Note:** For general admission inquiries, use admissions@vnrvjiet.ac.in or call +91-40-2304 2758.

**Legal action will be taken against fraudsters.**

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
 │ (Firestore – exact)│  (Pinecone + OpenAI)│
 └───────────────────┴────────────────────┘
        ↓
   Controlled LLM (GPT-4o-mini)
```

## Features

- **Hybrid pipeline**: Structured cutoff queries via Firestore; informational queries via Pinecone RAG
- **4 Years Historical Data**: 1,271 EAPCET cutoff records spanning 2022-2025
- **Contact Request System**: Collects user info when they want to speak with admission department
- **Admin Dashboard**: Easy-to-use interface for admission staff to view and manage contact requests
- **Privacy Protection**: Phone numbers only shared for fraud reports, not for general queries
- **Strict college scope**: Only answers about VNRVJIET; refuses other colleges
- **Intent classifier**: Greeting / informational / cutoff / mixed / out-of-scope
- **Special Categories**: SPORTS, CAP, NCC, OTHERS quotas + PH disability codes
- **Anti-Fraud Protection**: Warns users about unauthorized agents claiming to guarantee admissions
- **Floating chat widget**: Embeddable via iframe, mobile-responsive, collapsible
- **Security**: CORS whitelisting, rate limiting, input sanitisation, sandboxed iframe
- **Production-ready**: Docker, Firebase Firestore, environment-variable config, no exposed secrets

## 🔒 Security & Privacy

### Contact Information Protection

The chatbot implements strict security measures to protect sensitive contact information:

**🚨 Admission Section Mobile Number (+91 9391982884):**
- This number is **ONLY** shared when users report fraudulent agents or scams
- **NEVER** disclosed for general admission inquiries
- Protected by explicit system prompt rules

**For all standard queries, the chatbot provides:**
- General email: admissions@vnrvjiet.ac.in
- Main office: +91-40-2304 2758/59/60
- Website: www.vnrvjiet.ac.in

**When the mobile number IS shared:**
- User reports someone claiming to guarantee admission for money
- User mentions fake agents or consultants
- Fraud or scam-related queries

**When the mobile number is NOT shared:**
- General admission questions
- Cutoff inquiries
- Course/fee/campus information
- Any standard student queries

This security measure prevents spam, protects staff privacy, and ensures the fraud reporting line remains available for genuine cases.

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
│   │   └── cutoff_engine.py       # Firestore cutoff & eligibility engine
│   ├── rag/
│   │   ├── ingest.py              # Document → Pinecone ingestion
│   │   └── retriever.py           # Pinecone retrieval with college filter
│   ├── prompts/
│   │   └── system_prompt.txt      # LLM system prompt with guardrails
│   ├── data/
│   │   ├── init_db.py             # Firestore initialization
│   │   └── ingest_eapcet.py       # EAPCET PDF → Firestore ingestion
│   ├── frontend/
│   │   ├── widget.html            # Chat widget page
│   │   ├── widget.css             # Widget styles
│   │   └── widget.js              # Widget logic
│   └── utils/
│       └── validators.py          # Input sanitisation & entity extraction
├── tests/
│   └── test_chatbot.py            # Pytest test suite
├── docs/
│   ├── vnrvjiet_admissions.txt    # Sample RAG source document
│   ├── anti_fraud_notice.txt      # Official anti-fraud warning
│   ├── EAPCET_First-and-Last-Ranks-2025.pdf  # 2025 cutoff data
│   ├── EAPCET_First-and-Last-Ranks-2024.pdf  # 2024 cutoff data
│   ├── First-and-Last-Ranks-2023-Eamcet.pdf  # 2023 cutoff data
│   └── First-and-Last-Ranks-2022.pdf         # 2022 cutoff data
├── ingest_ews.py                  # EWS category ingestion helper
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
# Edit .env with your:
# - OpenAI API key
# - Pinecone API keys
# - Firebase project ID and credentials path
```

### 2. Setup Firebase

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Enable Firestore Database
3. Download service account JSON from Project Settings → Service Accounts
4. Save as `firebase-credentials.json` in project root
5. Update `.env` with `FIREBASE_PROJECT_ID` and `FIREBASE_CREDENTIALS` path

### 3. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

### 4. Load EAPCET Cutoff Data

The database already contains **1,271 cutoff records** from 2022-2025. To verify:

```bash
python -c "
from app.data.init_db import get_db, COLLECTION
db = get_db()
all_docs = list(db.collection(COLLECTION).stream())
print(f'Total records: {len(all_docs)}')
"
```

To add new year's data, see the [EAPCET Cutoff Data](#eapcet-cutoff-data) section.

### 5. Ingest documents into Pinecone

```bash
# Place your docs (PDF, TXT, MD) in the docs/ folder, then:
python -m app.rag.ingest --docs-dir docs --source website --year 2025
```

### 6. Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Open the widget

Visit **http://localhost:8000/widget** in your browser.

API docs at **http://localhost:8000/docs**.

## EAPCET Cutoff Data

The chatbot includes **4 years of historical EAPCET cutoff data (2022-2025)** with **1,271 total records** stored in **Firebase Firestore**.

### Database Summary

| Year | Total Records | Convenor Quota | SPORTS | CAP | NCC | OTHERS | EWS |
|------|---------------|----------------|---------|-----|-----|--------|-----|
| **2022** | 294 | 238 | 7 | 17 | 10 | 22 | 27 |
| **2023** | 285 | 232 | 6 | 16 | 10 | 21 | 28 |
| **2024** | 209 | 209 | — | — | — | — | — |
| **2025** | 483 | 375 | 8 | 25 | 15 | 60 | — |
| **Total** | **1,271** | 1,054 | 21 | 58 | 35 | 103 | 55 |

### Data Structure

Each cutoff record contains:

```python
{
    "year": 2025,                    # Academic year
    "branch": "CSE",                 # Branch code (CSE, ECE, EEE, etc.)
    "caste": "OC",                   # Category (OC, BC-A, BC-B, BC-C, BC-D, BC-E, SC-I, SC-II, ST, EWS)
    "gender": "Boys",                # Boys or Girls
    "first_rank": 2580,              # Opening rank
    "last_rank": 3500,               # Closing rank
    "quota": "Convenor",             # Convenor, SPORTS, CAP, NCC, OTHERS
    "ph_type": "PHO"                 # Optional: PHO, PHH, PHV, PHM, PHA (disability codes)
}
```

### Supported Categories

- **Caste Categories**: OC, BC-A, BC-B, BC-C, BC-D, BC-E, SC-I, SC-II, ST, EWS
- **Special Quotas**: SPORTS, CAP (Children of Armed Personnel), NCC, OTHERS
- **PH (Disability) Codes**:
  - `PHO`: Orthopedic impairment
  - `PHH`: Hearing impairment
  - `PHV`: Visual impairment
  - `PHM`: Mental disability
  - `PHA`: Autism spectrum disorder

### Branches Covered

All 14 engineering branches at VNRVJIET:
- **Core**: CIV (Civil), EEE, ME (Mechanical), ECE
- **Computer Science**: CSE, CSE-CSC (Cybersecurity), CSE-CSM (Machine Learning), CSE-CSD (Data Science), CSE-CSO (IoT)
- **Specialized**: EIE, IT, AUT (Automobile), CSB (Bioinformatics), AID (AI & Data Science)

### Ingesting EAPCET PDF Data

The system automatically extracts cutoff data from official VNRVJIET EAPCET rank PDFs.

#### For Standard Pages (1-2):

```bash
# Ingest pages 1-2 (OC through ST categories)
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page 1

python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page 2
```

#### For Special Categories (Pages 3-4):

```bash
# Ingest pages 3-4 (SPORTS, CAP, NCC, OTHERS with PH codes)
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page special
```

#### For EWS Category:

```bash
# For 2022/2023 PDFs with EWS on page 4
python ingest_ews.py 2022

# For 2025 PDFs with EWS on page 5
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page 5
```

#### Dry Run (Test without uploading):

```bash
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page 1 \
  --dry-run
```

#### Ingest All Pages:

```bash
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2025.pdf" \
  --year 2025 \
  --page all
```

### PDF Format Requirements

The ingestion script expects EAPCET PDFs with the following structure:

- **Page 1**: OC, BC-A, BC-B, BC-C categories (Boys/Girls, First/Last ranks)
- **Page 2**: BC-D, BC-E, SC-I, SC-II, ST categories
- **Page 3**: SPORTS, CAP, NCC, OTHERS quotas (with combined rank-category-PHcode format)
- **Page 4**: Continuation of special categories OR EWS category (depending on year)
- **Page 5** (if present): EWS category for newer PDFs

### Querying Cutoff Data

The chatbot automatically handles natural language queries:

```
User: "What is the CSE cutoff for OC boys in 2024?"
Bot: Returns first_rank and last_rank for CSE-OC-Boys-2024

User: "Show me ECE cutoffs for BC-A category across all years"
Bot: Returns year-wise comparison (2022-2025)

User: "What's the sports quota cutoff for CSE?"
Bot: Returns SPORTS quota cutoffs with available years
```

### Data Verification

Check loaded data:

```bash
python -c "
from app.data.init_db import get_db, COLLECTION
db = get_db()
docs_2025 = list(db.collection(COLLECTION).where('year', '==', 2025).stream())
print(f'2025 records: {len(docs_2025)}')
"
```

### Notes

- **Firestore Backend**: Data stored in Google Cloud Firestore for scalable queries
- **Automatic Branch Normalization**: CIVIL→CIV, MECH→ME, CSE- CSC→CSE-CSC
- **Missing Data**: Cells with `--` or empty values are skipped
- **Document IDs**: Format `{year}_{branch}_{caste}_{gender}_{quota}_{ph_type}`

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
| GET | `/admin/contacts` | Admin dashboard for contact requests |
| GET | `/admin/contacts/export` | Export contact requests to CSV |
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
| `FIREBASE_PROJECT_ID` | Firebase project ID | — |
| `FIREBASE_CREDENTIALS` | Path to Firebase service account JSON | — |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | localhost |
| `RATE_LIMIT_PER_MINUTE` | Max requests/min/IP | 30 |

## Adding More Data

### Adding New Year's Cutoff Data

When new EAPCET cutoff PDFs are released:

1. Place the PDF in the `docs/` directory
2. Run the ingestion script for each page:

```bash
# Example for 2026 data
python -m app.data.ingest_eapcet \
  --pdf "docs/EAPCET_First-and-Last-Ranks-2026.pdf" \
  --year 2026 \
  --page all
```

### RAG Documents

Place official admission documents (PDFs, text files) in the `docs/` directory and run the ingestion:

```bash
pyt

**Important:** The anti-fraud notice (`anti_fraud_notice.txt`) should be ingested into the RAG system so the chatbot can warn users about fraudulent admission agents claiming to guarantee Category B & NRI seats.hon -m app.rag.ingest --docs-dir docs --source pdf --year 2025
```

### Current Data Status

✅ **Cutoff Data**: 1,271 records spanning 2022-2025 (all pages ingested)  
✅ **Firestore**: Fully populated with historical EAPCET cutoffs  
✅ **Special Categories**: SPORTS, CAP, NCC, OTHERS quotas included  
✅ **PH Codes**: Disability categories (PHO, PHH, PHV, PHM, PHA) supported

## Contact Request Management

When users are not satisfied or want to speak directly with the admission department, the chatbot can collect their contact information and store it for the admission team to follow up.

### How It Works

1. **User Triggers Contact Request**: Keywords like "talk to admission", "speak with someone", "not satisfied"
2. **Multi-Turn Conversation**: Bot collects:
   - Name
   - Email
   - Phone number (with privacy controls)
   - Query type (fraud report, general inquiry, dissatisfied, other)
   - Additional message (optional)
3. **Storage & Notification**:
   - Saved to Firebase Firestore `contact_requests` collection
   - Email notification sent to admission team
   - Reference ID provided to user

### Privacy & Security

**Phone Number Privacy:**
- Phone numbers are **ONLY shared** with admission department for:
  - ✅ Fraud reports (unauthorized agents)
  - ✅ Explicit contact requests (general inquiry)
  - ❌ Hidden for chatbot dissatisfaction cases

**Data Protection:**
- Secure Firestore storage
- Password-protected admin dashboard
- HTTPS encryption in production

### Admin Dashboard

Access the contact requests dashboard at:
```
https://your-domain/admin/contacts?password=YOUR_ADMIN_PASSWORD
```

**Features:**
- 📊 View all contact requests with status
- 🔍 Filter by status (pending/contacted/resolved)
- 📥 Export to CSV for reporting
- 📱 Mobile-responsive design
- 🔒 Password protected access

**Status Management:**
- **Pending**: New request, not yet contacted
- **Contacted**: Admission team reached out to user
- **Resolved**: Issue resolved, no further action needed

### Implementation Options

See [docs/contact_request_methods.md](docs/contact_request_methods.md) for 7 different methods to manage contact requests:

1. **Google Sheets API** ✅ **FULLY IMPLEMENTED** - [Setup Guide](docs/GOOGLE_SHEETS_SETUP.md)
2. **Firebase Firestore + Admin Dashboard** (Implemented)
3. **Airtable** (Most user-friendly UI)
4. **Email Notifications** (Immediate alerts)
5. **Simple Admin Dashboard** (Built-in)
6. **Telegram Bot** (Mobile notifications)
7. **Microsoft Excel Online** (Enterprise)

**Recommended: Google Sheets** - Familiar interface, no training needed, mobile access, real-time collaboration

### Google Sheets Setup (5 Minutes)

**Recommended method** - admission staff can use familiar Google Sheets interface:

1. **Create Google Sheet** - [Follow complete guide](docs/GOOGLE_SHEETS_SETUP.md)
2. **Enable Google Sheets API** in Google Cloud Console
3. **Create service account** and download JSON key
4. **Share sheet** with service account email
5. **Run setup script**:
   ```bash
   python setup_google_sheets.py
   ```

See [GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md) for detailed step-by-step instructions.

### Environment Variables

Add to your `.env` file:

```env
# Google Sheets (Recommended)
GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
GOOGLE_SERVICE_ACCOUNT_PATH=google-service-account.json

# Email notifications (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=chatbot@vnrvjiet.ac.in
SMTP_USERNAME=your-email@vnrvjiet.ac.in
SMTP_PASSWORD=your-app-specific-password
ADMISSION_EMAIL=admissions@vnrvjiet.ac.in

# Admin dashboard access (Optional)
ADMIN_PASSWORD=your-secure-password-here
```

### Chat Flow Example

See [docs/contact_collection_flow.md](docs/contact_collection_flow.md) for complete implementation details.

**Example conversation:**

```
User: "I'm not satisfied with this answer, I want to talk to someone"

Bot: "I'd be happy to connect you with our admission team! 😊
      May I have your name?"

User: "Rahul Kumar"

Bot: "Nice to meet you, Rahul! 👋
      What's your email address?"

User: "rahul.kumar@example.com"

Bot: "Great! What's your phone number? 📞"

User: "9876543210"

Bot: "Thank you! What is this regarding?
      1️⃣ Report fraud/unauthorized agent
      2️⃣ General admission inquiry
      3️⃣ Not satisfied with chatbot response
      4️⃣ Other"

User: "2"

Bot: "✅ Request Submitted Successfully
      
      Thank you, Rahul! Our admission team has received your request.
      
      Contact Details:
      📧 rahul.kumar@example.com
      📞 9876543210
      
      What's next:
      Our team will reach out to you within 24 hours.
      
      Reference ID: a3b4c5d6"
```

## Official Contact Information

For genuine admission inquiries, contact VNRVJIET directly:

**VNR Vignana Jyothi Institute of Engineering and Technology**

📍 **Address:**  
Vignana Jyothi Nagar, Pragathi Nagar  
Nizampet (S.O), Hyderabad – 500 090  
Telangana, India

📞 **Phone:**  
- Main Office: +91-40-2304 2758/59/60  
- 🚨 Fraud Reporting ONLY: +91 9391982884 (Report illegal agents/consultants)

📠 **Fax:** 040-23042761

📧 **Email:** postbox@vnrvjiet.ac.in

🌐 **Website:** www.vnrvjiet.ac.in

---

**Important:** VNRVJIET does not use agents or consultants for Category B & NRI admissions. Report fraudsters immediately to the admission section.

## License

Internal use — VNRVJIET.
