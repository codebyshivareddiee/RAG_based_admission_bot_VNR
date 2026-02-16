# 📁 Documents Organization

This directory is organized into subdirectories based on file type and purpose.

## Directory Structure

```
docs/
├── txt/                    # TXT files for RAG ingestion
│   ├── anti_fraud_notice.txt
│   ├── Hostel-25-26.txt
│   ├── vnrvjiet_admissions.txt
│   ├── vnrvjiet_branches_intake.txt
│   └── vnrvjiet_hostel_rules_2025.txt
│
├── pdfs/                   # Document PDFs (optional for RAG)
│   ├── 2024 Batch Placements Highlights.pdf
│   ├── VNR-Admissions-Procedure.pdf
│   └── Telangana Engineering Admissions 2024–25.docx
│
├── tables/                 # PDFs with cutoff tables (processed separately)
│   ├── 2025-TGEAPCET-Cutoff-Ranks.pdf
│   ├── EAPCET_First-and-Last-Ranks-2024.pdf
│   ├── First-and-Last-Ranks-2022.pdf
│   ├── First-and-Last-Ranks-2023-Eamcet.pdf
│   └── TGEAPCET24REVISED.pdf
│
└── *.md                    # Documentation (kept in root)
    ├── contact_collection_flow.md
    ├── CONTACT_SYSTEM_SUMMARY.md
    ├── GOOGLE_SHEETS_SETUP.md
    └── TOKEN_MANAGEMENT.md
```

## 🎯 Purpose

### **txt/** - RAG Ingestion
**Processed by:** `ingest_all_docs.py`

Contains clean, structured text files optimized for RAG (Retrieval-Augmented Generation):
- College information
- Admissions procedures
- Hostel details
- Anti-fraud notices

**To ingest:**
```bash
python ingest_all_docs.py
```

### **tables/** - Cutoff Data
**Processed by:** `app/data/ingest_eapcet.py`, specialized cutoff scripts

Contains PDF files with tabular cutoff rank data:
- EAPCET cutoff ranks by year
- Branch-wise closing ranks
- Category-wise admission data

These are **NOT** ingested for RAG - they're processed into structured Firestore database records.

### **pdfs/** - Document Archive
**Purpose:** Reference documents, not yet ingested

Contains rich document PDFs and DOCX files:
- Placement reports
- Admission procedure manuals
- Official guidelines

These can optionally be ingested later if needed.

### **Root MD files**
**Purpose:** Internal documentation

Markdown documentation for developers:
- API documentation
- System architecture
- Configuration guides

## 📝 Adding New Documents

### To add a new TXT file for RAG:
1. Place `.txt` file in `docs/txt/`
2. Run: `python ingest_all_docs.py`

### To add cutoff data PDF:
1. Place PDF in `docs/tables/`
2. Run appropriate cutoff ingestion script with PDF path

### To add reference documents:
1. Place in `docs/pdfs/` for archival

## 🔍 Current Status

- **5 TXT files** ready for RAG ingestion
- **5 cutoff PDFs** for structured data processing
- **3 document PDFs** archived for reference
- **6 MD files** for documentation
