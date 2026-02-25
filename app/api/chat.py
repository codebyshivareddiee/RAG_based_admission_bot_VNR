"""
Chat API – the core endpoint that orchestrates:
  1. Input sanitisation
  2. Intent classification
  3. Cutoff engine (structured queries)
  4. RAG retrieval (informational queries)
  5. LLM answer generation with guardrails
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sys
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from openai import OpenAI, AsyncOpenAI
from app.config import get_settings
from app.classifier.intent_classifier import IntentType, classify
from app.logic.cutoff_engine import (
    check_eligibility,
    get_cutoff,
    get_all_cutoffs_for_branch,
    get_cutoffs_flexible,
    format_cutoffs_table,
    list_branches,
)
from app.rag.retriever import retrieve, retrieve_async
from app.utils.validators import (
    extract_branch,
    extract_branches,
    extract_category,
    extract_gender,
    extract_rank,
    extract_year,
    sanitise_input,
)
from app.utils.token_manager import (
    trim_history_smart,
    log_token_usage,
    count_messages_tokens,
    should_warn,
)
from app.utils.languages import (
    detect_language,
    detect_language_change_request,
    get_translation,
    get_language_instruction,
    get_language_selector_message,
    get_greeting_message,
    get_out_of_scope_message,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)

logger = logging.getLogger(__name__)

settings = get_settings()
router = APIRouter()

# ── Rate limiter (in-memory, per-IP) ─────────────────────────
_rate_buckets: dict[str, list[float]] = defaultdict(list)
# ── Conversation memory (in-memory, per-session) ──────────
# Stores last MAX_HISTORY messages per session for context continuity.
MAX_HISTORY = 10
_session_history: dict[str, list[dict]] = defaultdict(list)
_session_pending_intent: dict[str, str] = {}  # tracks if we asked for cutoff details
_session_language: dict[str, str] = {}  # stores language preference per session

# ── Response caching (in-memory) ──────────────────────────
# Cache common queries to reduce API calls and latency
CACHE_TTL = 1800  # 30 minutes
_response_cache: dict[str, tuple[str, float, str, list[str]]] = {}  # key -> (reply, timestamp, intent, sources)

# ── Cutoff collection state (per-session) ─────────────────
# Stores partially collected cutoff fields as user answers one by one.
# Keys: branch, category, gender, rank
_session_cutoff_data: dict[str, dict] = {}

# Stores the last successfully completed cutoff query details per session
# Used to offer reuse when user switches from cutoff to eligibility
_session_last_cutoff: dict[str, dict] = {}

# ── Contact request collection state (per-session) ────────
# Stores partially collected contact fields when user requests callback
# Keys: name, email, phone, programme, query_type, message
_session_contact_data: dict[str, dict] = {}

# ── Web search permission state (per-session) ─────────────
# Stores query awaiting user permission to search website
_session_pending_websearch: dict[str, str] = {}

# ── Clarification state (per-session) ─────────────────────
# Stores original query + category when we ask a narrowing question
# before running RAG/LLM for broad/vague informational topics.
_session_pending_clarification: dict[str, dict] = {}

# ── Document flow state (per-session) ─────────────────────
# Stores course and category selection for "Required Documents" queries
# Implements 2-layer guided flow: Course → Category → RAG
_session_pending_document_flow: dict[str, dict] = {}

# ── Fee flow state (per-session) ──────────────────────────
# Stores course, category, and fee type selection for fee structure queries
# Implements 2-3 layer guided flow: Course → Category → [Fee Type] → RAG
# This executes BEFORE clarification and RAG to provide focused results
_session_pending_fee_flow: dict[str, dict] = {}

# ── Active pipeline tracker (per-session) ─────────────────
# Tracks the currently active pipeline to enforce isolation.
# Values: "cutoff", "eligibility", "documents", "fee", "contact", "clarification", or None
_session_active_pipeline: dict[str, str | None] = {}

# Document flow questions (2-layer: course → category)
_DOCUMENT_FLOW_QUESTIONS = {
    "course": {
        "question": "For which course are you applying? 🎓",
        "clickable_options": [
            {"label": "B.Tech (Bachelor of Technology)", "value": "B.Tech"},
            {"label": "M.Tech (Master of Technology)", "value": "M.Tech"},
            {"label": "MCA (Master of Computer Applications)", "value": "MCA"},
        ],
        "options": {
            "1": "B.Tech",
            "b.tech": "B.Tech",
            "btech": "B.Tech",
            "bachelor": "B.Tech",
            "2": "M.Tech",
            "m.tech": "M.Tech",
            "mtech": "M.Tech",
            "master": "M.Tech",
            "3": "MCA",
            "mca": "MCA",
        }
    },
    "category": {
        "B.Tech": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "Category A – Convenor Quota (TG-EAPCET Rank)", "value": "Category A – Convenor Quota"},
                {"label": "Category B – JEE Mains (All India Open Rank)", "value": "Category B – JEE Mains"},
                {"label": "NRI / NRI Sponsored (11th & 12th Aggregate)", "value": "NRI / NRI Sponsored"},
                {"label": "Supernumerary Quota – FN / OCI / CIWG", "value": "Supernumerary Quota – FN / OCI / CIWG"},
            ],
            "options": {
                "1": "Category A – Convenor Quota",
                "category a": "Category A – Convenor Quota",
                "cat-a": "Category A – Convenor Quota",
                "cat a": "Category A – Convenor Quota",
                "convenor": "Category A – Convenor Quota",
                "eapcet": "Category A – Convenor Quota",
                "2": "Category B – JEE Mains",
                "category b": "Category B – JEE Mains",
                "cat-b": "Category B – JEE Mains",
                "cat b": "Category B – JEE Mains",
                "jee": "Category B – JEE Mains",
                "jee mains": "Category B – JEE Mains",
                "3": "NRI / NRI Sponsored",
                "nri": "NRI / NRI Sponsored",
                "nri sponsored": "NRI / NRI Sponsored",
                "4": "Supernumerary Quota – FN / OCI / CIWG",
                "supernumerary": "Supernumerary Quota – FN / OCI / CIWG",
                "fn": "Supernumerary Quota – FN / OCI / CIWG",
                "oci": "Supernumerary Quota – FN / OCI / CIWG",
                "ciwg": "Supernumerary Quota – FN / OCI / CIWG",
                "foreign": "Supernumerary Quota – FN / OCI / CIWG",
            }
        },
        "M.Tech": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "Category A – Convenor Quota (TG-PGECET Rank)", "value": "Category A – Convenor Quota"},
                {"label": "Category B – GATE (Score Based)", "value": "Category B – GATE"},
                {"label": "Management Quota", "value": "Management Quota"},
            ],
            "options": {
                "1": "Category A – Convenor Quota",
                "category a": "Category A – Convenor Quota",
                "cat-a": "Category A – Convenor Quota",
                "convenor": "Category A – Convenor Quota",
                "pgecet": "Category A – Convenor Quota",
                "2": "Category B – GATE",
                "category b": "Category B – GATE",
                "cat-b": "Category B – GATE",
                "gate": "Category B – GATE",
                "3": "Management Quota",
                "management": "Management Quota",
            }
        },
        "MCA": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "Category A – Convenor Quota (TG-ICET Rank)", "value": "Category A – Convenor Quota"},
                {"label": "Management Quota", "value": "Management Quota"},
            ],
            "options": {
                "1": "Category A – Convenor Quota",
                "category a": "Category A – Convenor Quota",
                "cat-a": "Category A – Convenor Quota",
                "convenor": "Category A – Convenor Quota",
                "icet": "Category A – Convenor Quota",
                "2": "Management Quota",
                "management": "Management Quota",
            }
        }
    }
}

# Fee flow questions (2-3 layers: course → category → [fee_type if unclear])
_FEE_FLOW_QUESTIONS = {
    "course": {
        "question": "I'd be happy to help with fee information! 💰\n\nFor which course are you applying?",
        "clickable_options": [
            {"label": "B.Tech (Bachelor of Technology)", "value": "B.Tech"},
            {"label": "M.Tech (Master of Technology)", "value": "M.Tech"},
            {"label": "MCA (Master of Computer Applications)", "value": "MCA"},
        ],
        "options": {
            "1": "B.Tech",
            "b.tech": "B.Tech",
            "btech": "B.Tech",
            "bachelor": "B.Tech",
            "2": "M.Tech",
            "m.tech": "M.Tech",
            "mtech": "M.Tech",
            "master": "M.Tech",
            "3": "MCA",
            "mca": "MCA",
        }
    },
    "category": {
        "B.Tech": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "Category A – Convenor Quota (TG-EAPCET Rank)", "value": "Category A"},
                {"label": "Category B – JEE Mains", "value": "Category B"},
                {"label": "NRI / NRI Sponsored", "value": "NRI"},
                {"label": "Management Quota", "value": "Management"},
            ],
            "options": {
                "1": "Category A",
                "category a": "Category A",
                "cat-a": "Category A",
                "cat a": "Category A",
                "convenor": "Category A",
                "eapcet": "Category A",
                "2": "Category B",
                "category b": "Category B",
                "cat-b": "Category B",
                "cat b": "Category B",
                "jee": "Category B",
                "jee mains": "Category B",
                "3": "NRI",
                "nri": "NRI",
                "nri sponsored": "NRI",
                "4": "Management",
                "management": "Management",
            }
        },
        "M.Tech": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "PGECET (Convenor Quota)", "value": "PGECET"},
                {"label": "GATE (Score Based)", "value": "GATE"},
                {"label": "Management Quota", "value": "Management"},
            ],
            "options": {
                "1": "PGECET",
                "pgecet": "PGECET",
                "convenor": "PGECET",
                "category a": "PGECET",
                "2": "GATE",
                "gate": "GATE",
                "category b": "GATE",
                "3": "Management",
                "management": "Management",
            }
        },
        "MCA": {
            "question": "Under which admission category? 📋",
            "clickable_options": [
                {"label": "ICET (Convenor Quota)", "value": "ICET"},
                {"label": "Management Quota", "value": "Management"},
            ],
            "options": {
                "1": "ICET",
                "icet": "ICET",
                "convenor": "ICET",
                "category a": "ICET",
                "2": "Management",
                "management": "Management",
            }
        }
    },
    "fee_type": {
        "question": "What specific information are you looking for? 💡",
        "clickable_options": [
            {"label": "Tuition Fees (yearly/semester breakdown)", "value": "tuition fees"},
            {"label": "Scholarships (fee reimbursement & financial aid)", "value": "scholarships"},
            {"label": "Complete Fee Structure (all fees including tuition)", "value": "complete fee structure"},
        ],
        "options": {
            "1": "tuition fees",
            "tuition": "tuition fees",
            "tuition fee": "tuition fees",
            "course fee": "tuition fees",
            "academic fee": "tuition fees",
            "2": "scholarships",
            "scholarship": "scholarships",
            "reimbursement": "scholarships",
            "fee reimbursement": "scholarships",
            "financial aid": "scholarships",
            "3": "complete fee structure",
            "all fees": "complete fee structure",
            "total fee": "complete fee structure",
            "complete": "complete fee structure",
            "full": "complete fee structure",
        }
    }
}

# Cutoff flow: collects branch → category → gender → year, then queries DB
_CUTOFF_QUESTIONS = [
    ("branch", "Which **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branches}"),
    ("category", "What is your **category / caste**?\n\n(e.g., OC, BC-A, BC-B, BC-C, BC-D, SC, ST, EWS)"),
    ("gender", "Are you looking for **Boys**, **Girls**, or **Both**?"),
    ("year", "Which **year**'s cutoff data would you like?\n\n(e.g., **2022**, **2023**, **2024**) — or reply **latest** for the most recent data."),
]

# Eligibility flow: collects branch → category → gender → year → rank, then queries DB
_ELIGIBILITY_QUESTIONS = [
    ("branch", "Which **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branches}"),
    ("category", "What is your **category / caste**?\n\n(e.g., OC, BC-A, BC-B, BC-C, BC-D, SC, ST, EWS)"),
    ("gender", "Are you looking for **Boys**, **Girls**, or **Both**?"),
    ("year", "Which **year**'s cutoff data would you like?\n\n(e.g., **2022**, **2023**, **2024**) — or reply **latest** for the most recent data."),
    ("rank", "What is your **EAPCET rank**?"),
]

# Contact request flow: collects user details for admission team callback
_CONTACT_QUESTIONS = [
    ("name", "I'd be happy to connect you with our admission team! 😊\n\nMay I have your **full name**?"),
    ("email", "Thank you, {name}! 👋\n\nWhat's your **email address**?"),
    ("phone", "Great! What's your **phone number**? 📞"),
    ("programme", "What programme are you interested in?\n\n1️⃣ **B.Tech** (Bachelor of Technology)\n2️⃣ **M.Tech** (Master of Technology)\n3️⃣ **MCA** (Master of Computer Applications)\n\nReply with the number or name."),
    ("query_type", "Thank you! What is this regarding?\n\n1️⃣ Report fraud / unauthorized agent\n2️⃣ General admission inquiry\n3️⃣ Not satisfied with chatbot response\n4️⃣ Other\n\nReply with the number or description."),
]

# ── Broad-topic clarification categories ──────────────────────
# When a user sends a vague/short query matching one of these categories,
# we ask a menu-style clarifying question BEFORE retrieving any context.
# This keeps the conversation focused and avoids dumping all information.
_CLARIFICATION_CATEGORIES: dict[str, dict] = {
    "fees": {
        "keywords": ["fee", "fees", "cost", "tuition", "payment", "charges", "installment", "fee structure"],
        "min_word_count": 1,
        "exclude_specific": [
            "hostel fee", "hostel fees", "mess fee", "transport fee",
            "b.tech fee", "btech fee", "m.tech fee", "mtech fee", "mca fee",
            "what is the fee", "how much is the fee",
            "total fee", "annual fee", "semester fee",
        ],
        "question": (
            "I'd be happy to help with fee information! 💰\n\n"
            "Could you specify which programme?\n\n"
            "1️⃣ **B.Tech** – Bachelor of Technology (4 years)\n"
            "2️⃣ **M.Tech** – Master of Technology (2 years)\n"
            "3️⃣ **MCA** – Master of Computer Applications\n"
            "4️⃣ **Scholarships / Fee Reimbursement**\n\n"
            "Reply with the number or programme name."
        ),
        "clarified_queries": {
            "1": "What is the B.Tech fee structure at VNRVJIET?",
            "b.tech": "What is the B.Tech fee structure at VNRVJIET?",
            "btech": "What is the B.Tech fee structure at VNRVJIET?",
            "bachelor": "What is the B.Tech fee structure at VNRVJIET?",
            "2": "What is the M.Tech fee structure at VNRVJIET?",
            "m.tech": "What is the M.Tech fee structure at VNRVJIET?",
            "mtech": "What is the M.Tech fee structure at VNRVJIET?",
            "master": "What is the M.Tech fee structure at VNRVJIET?",
            "3": "What is the MCA fee structure at VNRVJIET?",
            "mca": "What is the MCA fee structure at VNRVJIET?",
            "4": "What scholarships and fee reimbursement are available at VNRVJIET?",
            "scholarship": "What scholarships and fee reimbursement are available at VNRVJIET?",
            "reimbursement": "What scholarships and fee reimbursement are available at VNRVJIET?",
        },
    },
    "placements": {
        "keywords": [
            "placement", "placements", "placed", "recruiting",
            "campus recruitment", "tnp", "t&p", "training and placement",
            "training & placement", "hiring", "job placement",
        ],
        "min_word_count": 1,
        "exclude_specific": [
            "highest package", "average package", "top companies", "placement percentage",
            "placement statistics", "placement record", "how many placed",
            "which companies", "companies visit", "lpa", "internship", "intern",
        ],
        "question": (
            "Great question about placements! 🎓\n\n"
            "What specifically would you like to know?\n\n"
            "1️⃣ **Placement statistics** – percentage of students placed\n"
            "2️⃣ **Top recruiting companies** – which companies visit campus\n"
            "3️⃣ **Salary packages** – average and highest CTC\n"
            "4️⃣ **Internship opportunities** – internship details\n\n"
            "Reply with the number or topic."
        ),
        "clarified_queries": {
            "1": "What is the placement percentage and statistics at VNRVJIET?",
            "statistics": "What is the placement percentage and statistics at VNRVJIET?",
            "percentage": "What is the placement percentage and statistics at VNRVJIET?",
            "how many": "What is the placement percentage and statistics at VNRVJIET?",
            "2": "Which are the top recruiting companies at VNRVJIET?",
            "companies": "Which are the top recruiting companies at VNRVJIET?",
            "company": "Which are the top recruiting companies at VNRVJIET?",
            "recruiters": "Which are the top recruiting companies at VNRVJIET?",
            "3": "What is the average and highest salary package at VNRVJIET placements?",
            "package": "What is the average and highest salary package at VNRVJIET placements?",
            "salary": "What is the average and highest salary package at VNRVJIET placements?",
            "ctc": "What is the average and highest salary package at VNRVJIET placements?",
            "lpa": "What is the average and highest salary package at VNRVJIET placements?",
            "4": "What internship opportunities are available at VNRVJIET?",
            "internship": "What internship opportunities are available at VNRVJIET?",
            "intern": "What internship opportunities are available at VNRVJIET?",
        },
    },
    "hostel": {
        "keywords": ["hostel", "accommodation", "boarding", "staying on campus", "dormitory", "on-campus stay"],
        "min_word_count": 1,
        "exclude_specific": [
            "hostel fee", "hostel fees", "hostel cost", "hostel charges",
            "hostel rules", "hostel facility", "hostel facilities",
            "boys hostel", "girls hostel", "ladies hostel", "hostel available",
            "hostel warden", "hostel mess",
        ],
        "question": (
            "I can help with hostel information! 🏨\n\n"
            "What would you like to know about?\n\n"
            "1️⃣ **Hostel fees & charges** – annual costs and payment\n"
            "2️⃣ **Facilities** – rooms, mess, amenities\n"
            "3️⃣ **Rules & regulations** – hostel policies\n"
            "4️⃣ **Availability** – seats for boys/girls\n\n"
            "Reply with the number or topic."
        ),
        "clarified_queries": {
            "1": "What are the hostel fees and charges at VNRVJIET?",
            "fees": "What are the hostel fees and charges at VNRVJIET?",
            "fee": "What are the hostel fees and charges at VNRVJIET?",
            "charges": "What are the hostel fees and charges at VNRVJIET?",
            "cost": "What are the hostel fees and charges at VNRVJIET?",
            "2": "What are the hostel facilities at VNRVJIET?",
            "facilities": "What are the hostel facilities at VNRVJIET?",
            "facility": "What are the hostel facilities at VNRVJIET?",
            "amenities": "What are the hostel amenities at VNRVJIET?",
            "mess": "What are the hostel mess and food facilities at VNRVJIET?",
            "room": "What types of rooms are available in VNRVJIET hostel?",
            "3": "What are the hostel rules and regulations at VNRVJIET?",
            "rules": "What are the hostel rules and regulations at VNRVJIET?",
            "regulations": "What are the hostel rules and regulations at VNRVJIET?",
            "4": "What is the hostel seat availability for boys and girls at VNRVJIET?",
            "availability": "What is the hostel seat availability for boys and girls at VNRVJIET?",
            "available": "What is the hostel seat availability for boys and girls at VNRVJIET?",
            "seats": "What is the hostel seat availability for boys and girls at VNRVJIET?",
            "boys": "What is the boys hostel availability and details at VNRVJIET?",
            "girls": "What is the girls hostel availability and details at VNRVJIET?",
        },
    },
    "admissions": {
        "keywords": [
            "admission process", "how to apply", "how to get admission",
            "apply to vnrvjiet", "joining process", "admission procedure",
            "how admissions work", "apply for admission",
        ],
        "min_word_count": 3,
        "exclude_specific": [
            "lateral entry", "management quota", "nri quota", "cat-a", "cat a",
            "eapcet", "ecet", "documents required", "eligibility criteria",
            "admission date", "last date",
        ],
        "question": (
            "Here's what I can help you with regarding admissions! 📋\n\n"
            "What specifically are you looking for?\n\n"
            "1️⃣ **Step-by-step process** – how admissions work\n"
            "2️⃣ **Eligibility criteria** – qualification requirements\n"
            "3️⃣ **Required documents** – what to bring / submit\n"
            "4️⃣ **Important dates** – deadlines and schedule\n"
            "5️⃣ **Special quota** – Management / NRI / Lateral entry\n\n"
            "Reply with the number or topic."
        ),
        "clarified_queries": {
            "1": "What is the step-by-step admission process at VNRVJIET?",
            "process": "What is the step-by-step admission process at VNRVJIET?",
            "steps": "What is the step-by-step admission process at VNRVJIET?",
            "procedure": "What is the step-by-step admission process at VNRVJIET?",
            "2": "What are the eligibility criteria for admission to VNRVJIET?",
            "eligibility": "What are the eligibility criteria for admission to VNRVJIET?",
            "criteria": "What are the eligibility criteria for admission to VNRVJIET?",
            "qualification": "What are the eligibility criteria for admission to VNRVJIET?",
            "3": "What documents are required for admission to VNRVJIET?",
            "documents": "What documents are required for admission to VNRVJIET?",
            "document": "What documents are required for admission to VNRVJIET?",
            "certificate": "What certificates are required for admission to VNRVJIET?",
            "4": "What are the important admission dates and deadlines at VNRVJIET?",
            "dates": "What are the important admission dates and deadlines at VNRVJIET?",
            "date": "What are the important admission dates and deadlines at VNRVJIET?",
            "deadline": "What are the important admission dates and deadlines at VNRVJIET?",
            "5": "What is the management quota, NRI quota, and lateral entry admission process at VNRVJIET?",
            "management": "What is the management quota admission process at VNRVJIET?",
            "nri": "What is the NRI quota admission process at VNRVJIET?",
            "lateral": "What is the lateral entry admission process at VNRVJIET?",
            "quota": "What are the different quota options for admission at VNRVJIET?",
        },
    },
    "campus": {
        "keywords": [
            "campus life", "college life", "college facilities",
            "facilities at vnr", "facilities in college", "what facilities",
            "college infrastructure",
        ],
        "min_word_count": 2,
        "exclude_specific": [
            "campus location", "campus address", "how to reach",
            "labs", "library", "sports", "canteen", "transport", "bus",
            "hostel", "gym", "club", "department",
        ],
        "question": (
            "I can tell you about our campus! 🏫\n\n"
            "What aspect are you interested in?\n\n"
            "1️⃣ **Academic facilities** – labs, library, classrooms\n"
            "2️⃣ **Sports & recreation** – grounds, gym, student clubs\n"
            "3️⃣ **Canteen & dining** – food options on campus\n"
            "4️⃣ **Transport** – college bus routes and services\n"
            "5️⃣ **General overview** – overall campus information\n\n"
            "Reply with the number or topic."
        ),
        "clarified_queries": {
            "1": "What are the academic facilities like labs and library at VNRVJIET?",
            "academic": "What are the academic facilities like labs and library at VNRVJIET?",
            "lab": "What laboratory facilities are available at VNRVJIET?",
            "library": "What are the library facilities at VNRVJIET?",
            "2": "What sports and recreational facilities are available at VNRVJIET?",
            "sports": "What sports and recreational facilities are available at VNRVJIET?",
            "gym": "Is there a gym at VNRVJIET?",
            "clubs": "What student clubs and activities are available at VNRVJIET?",
            "3": "What are the canteen and food options at VNRVJIET?",
            "canteen": "What are the canteen and food options at VNRVJIET?",
            "food": "What are the food options at VNRVJIET?",
            "4": "What are the transport and bus facilities at VNRVJIET?",
            "transport": "What are the transport and bus facilities at VNRVJIET?",
            "bus": "What are the bus routes and transport facilities at VNRVJIET?",
            "5": "Give me an overview of VNRVJIET campus and facilities.",
            "general": "Give me an overview of VNRVJIET campus and facilities.",
            "overview": "Give me an overview of VNRVJIET campus and facilities.",
        },
    },
}

# ── Required Documents pipeline data ─────────────────────────
# RAG query templates per program – used to build the retrieval query
# so the LLM answers from the actual ingested knowledge base, not hardcoded text.
_DOCUMENTS_RAG_QUERIES: dict[str, str] = {
    "B.Tech": "What documents are required for B.Tech admission at VNRVJIET?",
    "M.Tech": "What documents are required for M.Tech admission at VNRVJIET?",
    "MCA": "What documents are required for MCA admission at VNRVJIET?",
}

# Keywords that strongly indicate user is asking about required documents
_REQUIRED_DOCUMENTS_KEYWORDS: list[str] = [
    "required documents", "required document",
    "documents required", "document required",
    "what documents", "which documents", "documents needed",
    "documents for admission", "document list",
    "certificates required", "certificates needed",
    "what certificate", "which certificate",
    "admission documents", "documents to bring",
    "documents to submit", "bring documents",
]


def _detect_required_documents_intent(message: str) -> bool:
    """
    Detect if the user is asking about required documents for admission.
    Returns True when the message clearly targets the documents pipeline.
    """
    msg_lower = message.lower().strip()
    # Exact / substring match on strong document phrases
    if any(kw in msg_lower for kw in _REQUIRED_DOCUMENTS_KEYWORDS):
        return True
    # Two-word shorthand: "required documents" (already covered above)
    # Also catch bare "documents" when it is the whole message
    if msg_lower in ("documents", "document", "docs", "certificates"):
        return True
    return False


def _resolve_program_selection(user_reply: str) -> str | None:
    """
    Map the user's response to a program name for the documents pipeline.
    Returns "B.Tech", "M.Tech", or "MCA", or None if unclear.
    """
    r = user_reply.lower().strip()
    if r in ("1", "b.tech", "btech", "be", "b.e", "bachelor", "b tech"):
        return "B.Tech"
    if r in ("2", "m.tech", "mtech", "me", "m.e", "master", "m tech", "masters"):
        return "M.Tech"
    if r in ("3", "mca", "m.c.a", "master of computer applications"):
        return "MCA"
    # Numeric prefix in longer reply
    if user_reply.strip().startswith("1"):
        return "B.Tech"
    if user_reply.strip().startswith("2"):
        return "M.Tech"
    if user_reply.strip().startswith("3"):
        return "MCA"
    return None


def _clear_other_pipelines(session_id: str, keep: str | None = None) -> None:
    """
    Clear all pipeline state objects for a session EXCEPT the one named in `keep`.
    Enforces pipeline isolation: no state from a previous pipeline bleeds into the new one.

    Args:
        session_id: The session to clean up.
        keep: Pipeline name to preserve ("cutoff", "documents", "fee", "contact",
              "clarification", "websearch"). Pass None to clear everything.
    """
    if keep != "cutoff":
        _session_cutoff_data.pop(session_id, None)
        _session_pending_intent.pop(session_id, None)
        _session_last_cutoff.pop(session_id, None)
    if keep != "documents":
        _session_pending_document_flow.pop(session_id, None)
    if keep != "fee":
        _session_pending_fee_flow.pop(session_id, None)
    if keep != "contact":
        _session_contact_data.pop(session_id, None)
    if keep != "clarification":
        _session_pending_clarification.pop(session_id, None)
    if keep != "websearch":
        _session_pending_websearch.pop(session_id, None)
    # Update active pipeline tracker
    _session_active_pipeline[session_id] = keep


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window = 60.0
    bucket = _rate_buckets[ip]
    # Purge old entries
    _rate_buckets[ip] = [t for t in bucket if now - t < window]
    if len(_rate_buckets[ip]) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a moment and try again.",
        )
    _rate_buckets[ip].append(now)


def _get_cache_key(query: str, intent: str, language: str = "en") -> str:
    """
    Generate cache key from normalized query + intent + language.
    Uses MD5 hash for efficient key lookup.
    """
    normalized = query.lower().strip()
    # Remove special characters and extra spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    key_string = f"{normalized}:{intent}:{language}"
    return hashlib.md5(key_string.encode()).hexdigest()


def _get_cached_response(query: str, intent: str, language: str = "en") -> tuple[str, list[str]] | None:
    """
    Get cached response if available and fresh.
    Returns (reply, sources) tuple or None.
    """
    key = _get_cache_key(query, intent, language)
    if key in _response_cache:
        reply, timestamp, cached_intent, sources = _response_cache[key]
        # Check if cache is still fresh
        if time.time() - timestamp < CACHE_TTL:
            logger.info(f"Cache HIT for query: {query[:50]}...")
            return (reply, sources)
        else:
            # Cache expired
            del _response_cache[key]
    return None


def _cache_response(query: str, intent: str, reply: str, sources: list[str], language: str = "en") -> None:
    """
    Cache a response for future reuse.
    Automatically manages cache size (keep last 1000 entries).
    """
    key = _get_cache_key(query, intent, language)
    _response_cache[key] = (reply, time.time(), intent, sources)
    
    # Limit cache size to prevent memory bloat
    if len(_response_cache) > 1000:
        # Remove oldest 200 entries
        sorted_keys = sorted(_response_cache.keys(), key=lambda k: _response_cache[k][1])
        for old_key in sorted_keys[:200]:
            del _response_cache[old_key]
        logger.info(f"Cache cleanup: removed 200 old entries, {len(_response_cache)} remaining")


def _detect_trend_request(message: str) -> bool:
    """
    Detect if user is asking for trend analysis / historical data.
    Returns True if trend-related keywords are found.
    """
    trend_keywords = [
        "trend", "history", "historical", "all years", "over years",
        "analysis", "analyze", "analyse", "past years", "progression",
        "how has", "changed over", "comparison", "compare years",
        "how it's been", "how its been", "show me all", "from past",
        "previous years", "over the years", "year by year", "yearly",
        "show trend", "give trend", "show all years", "all available years"
    ]
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in trend_keywords)


def _is_topic_change(message: str, current_flow: str = None) -> bool:
    """
    Detect if user is changing topic / wants to exit current collection flow.
    Returns True if user is clearly asking about something else.
    
    Args:
        message: User's message
        current_flow: Current collection mode ("cutoff", "eligibility", "contact_request", "document_flow", "fee_flow", or None)
    """
    msg_lower = message.lower().strip()
    
    # Explicit exit phrases
    exit_phrases = [
        "never mind", "nevermind", "forget it", "cancel", "stop",
        "go back", "start over", "new question", "different question",
        "something else", "change topic", "actually", "wait", "hold on"
    ]
    if any(phrase in msg_lower for phrase in exit_phrases):
        return True
    
    # Detect if user is now asking about required documents (any pipeline)
    if _detect_required_documents_intent(message):
        return True

    # If in cutoff/eligibility flow, detect informational questions
    if current_flow in ["cutoff", "eligibility"]:
        info_keywords = [
            "placement", "package", "salary", "company", "recruit",
            "campus", "hostel", "mess", "accommodation", "facility",
            "fee", "fees", "cost", "scholarship", "financial",
            "faculty", "professor", "teacher", "staff",
            "infrastructure", "library", "lab", "computer",
            "sports", "club", "extra", "cultural", "event",
            "location", "address", "how to reach", "transport",
            "admission process", "how to apply", "application",
            "document", "certificate", "eligibility criteria",
            "lateral", "management", "nri", "seat", "quota"
        ]
        # If message has 2+ words and contains informational keywords, it's a topic change
        word_count = len(msg_lower.split())
        if word_count >= 2 and any(kw in msg_lower for kw in info_keywords):
            return True
    
    # If in contact flow, detect cutoff/info questions
    if current_flow == "contact_request":
        cutoff_keywords = [
            "cutoff", "cut-off", "rank", "eapcet", "eligible",
            "admission", "seat", "can i get", "will i get"
        ]
        info_keywords = [
            "placement", "fee", "campus", "hostel", "faculty",
            "course", "branch", "program"
        ]
        if any(kw in msg_lower for kw in cutoff_keywords + info_keywords):
            return True
    
    # If in document flow, detect if asking something unrelated to documents
    if current_flow == "document_flow":
        unrelated_keywords = [
            "cutoff", "rank", "eligible", "placement", "package",
            "hostel", "fee", "campus", "faculty"
        ]
        if any(kw in msg_lower for kw in unrelated_keywords):
            return True
    
    # If in fee flow, detect if asking something unrelated to fees/scholarships
    if current_flow == "fee_flow":
        unrelated_keywords = [
            "cutoff", "rank", "eligible", "placement", "package",
            "hostel", "campus", "faculty", "document", "certificate",
            "admission process", "how to apply"
        ]
        # Exclude scholarship/reimbursement keywords as they're fee-related
        if any(kw in msg_lower for kw in unrelated_keywords) and "scholarship" not in msg_lower and "reimbursement" not in msg_lower:
            return True
    
    # Check if message is a full question (has question words + multiple words)
    question_words = ["what", "when", "where", "how", "why", "which", "who", "tell me", "show me", "give me"]
    word_count = len(msg_lower.split())
    if word_count >= 4 and any(qw in msg_lower for qw in question_words):
        return True
    
    return False


def _detect_url_category(query: str) -> str:
    """
    Determine which website URL category to fetch based on query keywords.
    Returns category key for VNRVJIET_WEBSITE_URLS dict.
    """
    query_lower = query.lower()
    
    # International admissions
    if any(kw in query_lower for kw in ["international", "foreign", "nri", "overseas", "abroad student"]):
        return "international_admissions"
    
    # Transport/bus
    if any(kw in query_lower for kw in ["transport", "bus", "travel", "route", "vehicle", "commute"]):
        return "transport"
    
    # Library
    if any(kw in query_lower for kw in ["library", "book", "reading room", "digital library", "e-resource"]):
        return "library"
    
    # Syllabus/books
    if any(kw in query_lower for kw in ["syllabus", "curriculum", "textbook", "book download", "course material"]):
        return "syllabus"
    
    # Academic calendar
    if any(kw in query_lower for kw in ["calendar", "schedule", "academic year", "semester date", "exam date", "holiday"]):
        return "academic_calendar"
    
    # Specific department pages
    if any(kw in query_lower for kw in ["cse", "computer science", "csbs", "cs business"]):
        return "dept_cse"
    if any(kw in query_lower for kw in ["ai", "ml", "aiml", "artificial intelligence", "machine learning", "iot", "internet of things", "robotics"]):
        return "dept_cse_aiml_iot"
    if any(kw in query_lower for kw in ["data science", "ds", "aids", "ai ds", "cyber security", "cys"]):
        return "dept_cse_ds_cys"
    if "information technology" in query_lower or query_lower.startswith("it ") or " it" in query_lower:
        return "dept_it"
    if any(kw in query_lower for kw in ["mechanical", "mech"]):
        return "dept_mech"
    if "civil" in query_lower:
        return "dept_civil"
    if any(kw in query_lower for kw in ["ece", "electronics communication"]):
        return "dept_ece"
    if any(kw in query_lower for kw in ["eee", "electrical electronics"]):
        return "dept_eee"
    if any(kw in query_lower for kw in ["eie", "instrumentation"]):
        return "dept_eie"
    if any(kw in query_lower for kw in ["automobile", "auto", "automotive"]):
        return "dept_automobile"
    if any(kw in query_lower for kw in ["biotechnology", "biotech", "bio tech"]):
        return "dept_biotechnology"
    if any(kw in query_lower for kw in ["chemistry", "chem"]):
        return "dept_chemistry"
    if any(kw in query_lower for kw in ["english", "humanities", "communication"]):
        return "dept_english"
    if any(kw in query_lower for kw in ["physics", "phy"]):
        return "dept_physics"
    if any(kw in query_lower for kw in ["mathematics", "math", "maths", "management"]):
        return "dept_mathematics"
    
    # General departments/exams (when asking about all departments)
    if any(kw in query_lower for kw in ["all departments", "department list", "examination", "exam", "faculty", "hod"]):
        return "departments"
    
    # Placement keywords
    if any(kw in query_lower for kw in ["placement", "package", "salary", "company", "recruited", "job", "career", "training"]):
        return "placements"
    
    # Scholarship
    if any(kw in query_lower for kw in ["scholarship", "financial aid", "fee concession", "waiver", "reimbursement"]):
        return "scholarship"
    
    # Fee keywords
    if any(kw in query_lower for kw in ["fee", "cost", "tuition", "payment", "installment"]):
        return "fees"
    
    # Hostel specific
    if any(kw in query_lower for kw in ["hostel", "accommodation", "room", "boarding", "mess", "warden"]):
        return "hostel"
    
    # Campus/facilities
    if any(kw in query_lower for kw in ["campus", "facility", "infrastructure", "lab", "sports", "gym", "canteen"]):
        return "campus"
    
    # About/general
    if any(kw in query_lower for kw in ["about", "history", "established", "founder", "college info", "accreditation"]):
        return "about"
    
    # Admissions (default for admission-related)
    if any(kw in query_lower for kw in ["admission", "apply", "application", "eligibility", "document", "counselling", "seat"]):
        return "admissions"
    
    # Default to general homepage
    return "home"


def _is_yes_response(message: str) -> bool:
    """Check if message is a positive confirmation."""
    msg_lower = message.lower().strip()
    yes_patterns = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "fine",
        "go ahead", "please", "do it", "search", "yes please",
        "👍", "✓", "✔"
    ]
    return any(p in msg_lower for p in yes_patterns)


def _is_no_response(message: str) -> bool:
    """Check if message is a negative response."""
    msg_lower = message.lower().strip()
    no_patterns = [
        "no", "nope", "nah", "don't", "dont", "not now",
        "skip", "cancel", "never mind", "nevermind"
    ]
    return any(p in msg_lower for p in no_patterns)


def _detect_category_needing_clarification(message: str) -> str | None:
    """
    Detect if the user's message is a broad / vague informational query
    that benefits from a clarifying question before we look up the answer.

    Returns the category key (e.g. 'fees', 'placements') when clarification
    is needed, or None when the query is already specific enough.
    """
    msg_lower = message.lower().strip()
    word_count = len(msg_lower.split())

    for category, config in _CLARIFICATION_CATEGORIES.items():
        # Must match at least one keyword for this category
        if not any(kw in msg_lower for kw in config["keywords"]):
            continue

        # Skip if the query is already specific (matches an exclude phrase)
        if any(excl in msg_lower for excl in config.get("exclude_specific", [])):
            continue

        # If the message is long (10+ words) it's likely already specific
        if word_count >= 10:
            continue

        return category

    return None


def _resolve_clarification_response(user_reply: str, category: str) -> str | None:
    """
    Map the user's answer to a clarifying question to a refined query string.
    Returns the refined query, or None if the reply doesn't match any option.
    """
    config = _CLARIFICATION_CATEGORIES.get(category)
    if not config:
        return None

    msg_lower = user_reply.lower().strip()
    clarified_queries = config["clarified_queries"]

    # 1. Try exact key match
    if msg_lower in clarified_queries:
        return clarified_queries[msg_lower]

    # 2. Try substring match (longest key wins to avoid false positives)
    best_key = max(
        (k for k in clarified_queries if k in msg_lower),
        key=len,
        default=None,
    )
    if best_key:
        return clarified_queries[best_key]

    return None


def _detect_cutoff_query(message: str) -> bool:
    """
    Detect if query is about cutoff ranks or eligibility.
    Uses keyword matching to identify cutoff-related queries before intent classification.
    """
    msg_lower = message.lower().strip()
    cutoff_keywords = [
        "cutoff", "cut off", "cut-off", "closing rank", "last rank",
        "eapcet", "tseamcet", "ts eamcet", "ts-eapcet", "opening rank",
        "counselling", "counseling", "rank required", "minimum rank",
        "eligible", "eligibility", "can i get", "will i get", "my rank",
        "admission rank", "qualifying rank", "required rank",
        "branch cutoff", "cutoffs", "cut offs", "admission chances",
    ]
    return any(kw in msg_lower for kw in cutoff_keywords)


def _detect_document_query(message: str) -> bool:
    """Detect if query is about required documents."""
    msg_lower = message.lower().strip()
    keywords = [
        "required document", "documents required", "document needed",
        "documents needed", "what documents", "which documents",
        "certificates required", "certificates needed",
        "documents for admission", "admission documents",
        "papers required", "papers needed",
    ]
    return any(kw in msg_lower for kw in keywords)


def _extract_course_from_message(message: str) -> str | None:
    """Extract course name from message."""
    msg_lower = message.lower().strip()
    if any(kw in msg_lower for kw in ["b.tech", "btech", "bachelor"]):
        return "B.Tech"
    if any(kw in msg_lower for kw in ["m.tech", "mtech", "master"]):
        return "M.Tech"
    if "mca" in msg_lower:
        return "MCA"
    return None


def _extract_category_from_message(message: str, course: str) -> str | None:
    """Extract admission category from message for a given course."""
    msg_lower = message.lower().strip()
    
    if course not in _DOCUMENT_FLOW_QUESTIONS["category"]:
        return None
    
    options = _DOCUMENT_FLOW_QUESTIONS["category"][course]["options"]
    
    # Try longest match first to avoid false positives
    for key in sorted(options.keys(), key=len, reverse=True):
        if key in msg_lower:
            return options[key]
    
    return None


def _resolve_course_response(user_reply: str) -> str | None:
    """Map user's course selection to standard course name."""
    msg_lower = user_reply.lower().strip()
    options = _DOCUMENT_FLOW_QUESTIONS["course"]["options"]
    
    # Try exact match
    if msg_lower in options:
        return options[msg_lower]
    
    # Try substring match
    for key, value in options.items():
        if key in msg_lower:
            return value
    
    return None


def _resolve_category_response(user_reply: str, course: str) -> str | None:
    """Map user's category selection to standard category name."""
    if course not in _DOCUMENT_FLOW_QUESTIONS["category"]:
        return None
    
    msg_lower = user_reply.lower().strip()
    options = _DOCUMENT_FLOW_QUESTIONS["category"][course]["options"]
    
    # Try exact match
    if msg_lower in options:
        return options[msg_lower]
    
    # Try substring match (longest first)
    for key in sorted(options.keys(), key=len, reverse=True):
        if key in msg_lower:
            return options[key]
    
    return None


# ═══════════════════════════════════════════════════════════
# Fee Flow Helper Functions
# ═══════════════════════════════════════════════════════════

def _detect_fee_query(message: str) -> bool:
    """
    Detect if query is about fee structure or scholarships.
    
    This function identifies queries that should trigger the fee flow
    before clarification and RAG systems are engaged.
    """
    msg_lower = message.lower().strip()
    
    # Primary fee keywords
    fee_keywords = [
        "fee structure", "fees", "fee", "cost", "tuition", "tuition fee",
        "course fee", "academic fee", "fee details", "fee information",
        "how much", "total fee", "annual fee", "semester fee",
        "pay", "payment", "charges", "fee breakdown",
    ]
    
    # Scholarship keywords
    scholarship_keywords = [
        "scholarship", "scholarships", "reimbursement", "fee reimbursement",
        "financial aid", "fee waiver", "concession",
    ]
    
    # Check if message matches fee or scholarship keywords
    has_fee_keyword = any(kw in msg_lower for kw in fee_keywords)
    has_scholarship_keyword = any(kw in msg_lower for kw in scholarship_keywords)
    
    # Exclude if it's specifically about hostel or mess fees (different category)
    exclude_keywords = ["hostel fee", "mess fee", "transport fee"]
    is_excluded = any(kw in msg_lower for kw in exclude_keywords)
    
    return (has_fee_keyword or has_scholarship_keyword) and not is_excluded


def _extract_fee_category_from_message(message: str, course: str) -> str | None:
    """
    Extract admission category from message for fee queries.
    Uses a simplified mapping compared to document flow.
    """
    msg_lower = message.lower().strip()
    
    if course not in _FEE_FLOW_QUESTIONS["category"]:
        return None
    
    options = _FEE_FLOW_QUESTIONS["category"][course]["options"]
    
    # Try longest match first to avoid false positives
    for key in sorted(options.keys(), key=len, reverse=True):
        if key in msg_lower:
            return options[key]
    
    return None


def _extract_fee_type_from_message(message: str) -> str | None:
    """
    Extract specific fee type from message (tuition, scholarship, etc.).
    Returns None if not clearly specified.
    """
    msg_lower = message.lower().strip()
    
    # Check for explicit fee type mentions
    if any(kw in msg_lower for kw in ["scholarship", "reimbursement", "financial aid"]):
        return "scholarships"
    
    if any(kw in msg_lower for kw in ["tuition fee", "tuition", "course fee", "academic fee"]):
        return "tuition fees"
    
    if any(kw in msg_lower for kw in ["hostel fee", "hostel"]):
        return "hostel fees"
    
    if any(kw in msg_lower for kw in ["complete", "all fees", "total fee", "full fee"]):
        return "complete fee structure"
    
    # If query is very specific, consider fee type clear
    # e.g., "What is the B.Tech fee?" - we know user wants tuition
    if any(kw in msg_lower for kw in ["what is the", "tell me the", "how much is"]):
        return "tuition fees"
    
    return None


def _is_fee_type_clear_from_query(message: str) -> bool:
    """
    Determine if the query clearly indicates what fee information is needed.
    If clear, we can skip the fee_type layer.
    """
    msg_lower = message.lower().strip()
    
    # Clear indicators
    clear_indicators = [
        "scholarship", "reimbursement", "financial aid",
        "tuition fee", "tuition", "course fee",
        "hostel fee", "hostel",
        "complete fee", "all fees", "total fee",
        "fee structure", "fee details",
    ]
    
    return any(indicator in msg_lower for indicator in clear_indicators)


def _resolve_fee_course_response(user_reply: str) -> str | None:
    """Map user's course selection for fee flow to standard course name."""
    msg_lower = user_reply.lower().strip()
    options = _FEE_FLOW_QUESTIONS["course"]["options"]
    
    # Try exact match
    if msg_lower in options:
        return options[msg_lower]
    
    # Try substring match
    for key, value in options.items():
        if key in msg_lower:
            return value
    
    return None


def _resolve_fee_category_response(user_reply: str, course: str) -> str | None:
    """Map user's category selection for fee flow to standard category name."""
    if course not in _FEE_FLOW_QUESTIONS["category"]:
        return None
    
    msg_lower = user_reply.lower().strip()
    options = _FEE_FLOW_QUESTIONS["category"][course]["options"]
    
    # Try exact match
    if msg_lower in options:
        return options[msg_lower]
    
    # Try substring match (longest first)
    for key in sorted(options.keys(), key=len, reverse=True):
        if key in msg_lower:
            return options[key]
    
    return None


def _resolve_fee_type_response(user_reply: str) -> str | None:
    """Map user's fee type selection to standard fee type."""
    msg_lower = user_reply.lower().strip()
    options = _FEE_FLOW_QUESTIONS["fee_type"]["options"]
    
    # Try exact match
    if msg_lower in options:
        return options[msg_lower]
    
    # Try substring match (longest first)
    for key in sorted(options.keys(), key=len, reverse=True):
        if key in msg_lower:
            return options[key]
    
    return None


def _build_multi_branch_reply(
    branches: list[str],
    category: str,
    gender: str,
    rank: int | None = None,
    show_trend: bool = False,
    year: int | None = None,
) -> str:
    """
    Query cutoff/eligibility for one or more branches and build
    a combined response.
    
    Handles "ALL" values for category and gender to show comprehensive data.
    
    Args:
        branches: List of branch codes or ["ALL"] for all branches
        category: Category code or "ALL" for all categories
        gender: "Boys", "Girls", or "ALL" for both genders
        rank: Optional rank for eligibility check
        show_trend: If True, shows all years with trend analysis
        year: Specific year to query (e.g., 2023, 2024). None for latest
    """
    # Handle "ALL" cases with flexible query (ALL branches, categories, or genders)
    if branches == ["ALL"] or "ALL" in branches or category == "ALL" or gender == "ALL":
        # Use flexible query function
        # Determine branches to query
        query_branches = []
        if branches == ["ALL"] or (isinstance(branches, list) and "ALL" in branches):
            query_branches = [None]  # Query all branches
        else:
            query_branches = branches if isinstance(branches, list) else [branches]
        
        all_cutoffs = []
        for branch in query_branches:
            cutoffs = get_cutoffs_flexible(
                branch=branch,
                category=None if category == "ALL" else category,
                gender=None if gender == "ALL" else gender,
                year=year,
                limit=200,
            )
            all_cutoffs.extend(cutoffs)
        
        if not all_cutoffs:
            cat_str = "all categories" if category == "ALL" else category
            gen_str = "both Boys and Girls" if gender == "ALL" else gender
            branch_str = "all departments" if branches == ["ALL"] else ", ".join(branches)
            return f"No cutoff data found for {branch_str} / {cat_str} / {gen_str}. The data may not be available yet."
        
        # Format the results
        title_parts = []
        if branches == ["ALL"]:
            title_parts.append("All Departments")
        else:
            title_parts.append(", ".join(branches))
        
        if category == "ALL":
            title_parts.append("All Categories")
        else:
            title_parts.append(category)
        
        if gender == "ALL":
            title_parts.append("Boys & Girls")
        else:
            title_parts.append(gender)
        
        title = "Cutoff Ranks: " + " | ".join(title_parts)
        return format_cutoffs_table(all_cutoffs, title=title, max_rows=50)
    
    # Original logic for specific branch(es) / category.
    # gender=None is now handled in get_cutoff / check_eligibility:
    # the gender filter is skipped and the best available row is returned.
    parts: list[str] = []
    for b in branches:
        if rank is not None:
            result = check_eligibility(rank, b, category, year=year, gender=gender if gender else "Boys")
        else:
            result = get_cutoff(b, category, year=year, gender=gender, show_trend=show_trend)
        parts.append(result.message)

    if len(parts) == 1:
        return parts[0]

    # Multiple branches – format as a numbered list
    lines = []
    for i, msg in enumerate(parts, 1):
        lines.append(f"**{i}.** {msg}")
    return "\n\n".join(lines)


# ── Request / Response models ─────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None
    language: str | None = None  # User's preferred language code (e.g., 'en', 'hi', 'te')


class ChatResponse(BaseModel):
    reply: str
    intent: str
    session_id: str
    sources: list[str] = []
    language: str = DEFAULT_LANGUAGE  # Current language for this session
    options: list[dict] = []  # Clickable options for guided flows


# ── LLM caller ────────────────────────────────────────────────

_openai_client: OpenAI | None = None
_async_openai_client: AsyncOpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _get_async_openai() -> AsyncOpenAI:
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_openai_client


def _load_system_prompt() -> str:
    path = Path(settings.SYSTEM_PROMPT_PATH)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        f"You are the official admissions assistant for {settings.COLLEGE_NAME}. "
        "Answer only from the provided context. Never discuss other colleges."
    )


_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _load_system_prompt()
    return _SYSTEM_PROMPT


def _generate_llm_response(
    user_message: str,
    context: str = "",
    cutoff_info: str = "",
    history: list[dict] | None = None,
    session_id: str = "unknown",
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Call OpenAI with smart token management and multilingual support.
    
    Features:
    - Token counting and monitoring
    - Smart history trimming with summarization
    - Automatic context truncation on overflow
    - Warning logs when approaching limits
    - Multilingual response generation
    """
    system = _get_system_prompt()
    
    # Add language instruction to system prompt
    lang_instruction = get_language_instruction(language)
    system_with_lang = f"{system}\n\n**IMPORTANT: {lang_instruction}**"
    
    client = _get_openai()

    user_content_parts = [f"User question: {user_message}"]

    if cutoff_info:
        user_content_parts.append(f"\n--- Cutoff Data (from database) ---\n{cutoff_info}")

    if context:
        user_content_parts.append(f"\n--- Retrieved Context ---\n{context}")

    if not cutoff_info and not context:
        user_content_parts.append(
            "\n[No specific context was retrieved. Answer based on general VNRVJIET knowledge "
            "in the system prompt, or state that the information is unavailable.]"
        )

    user_content = "\n".join(user_content_parts)

    # Smart history trimming with summarization
    trimmed_history = []
    if history:
        try:
            trimmed_history = trim_history_smart(
                history=history,
                system_prompt=system_with_lang,
                user_message=user_content,
                context=context,
                cutoff_info=cutoff_info,
                client=client,
                model=settings.OPENAI_MODEL,
            )
        except Exception as e:
            logger.error(f"Failed to trim history smartly: {e}. Using basic trimming.")
            # Fallback to basic trimming
            trimmed_history = history[-MAX_HISTORY:] if history else []

    # Build messages
    messages: list[dict] = [{"role": "system", "content": system_with_lang}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": user_content})

    # Log token usage
    try:
        log_token_usage(messages, settings.OPENAI_MODEL, session_id)
    except Exception as e:
        logger.warning(f"Failed to log token usage: {e}")

    # Call OpenAI with error handling
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        error_str = str(e).lower()
        
        # Handle token limit errors
        if "maximum context length" in error_str or "token" in error_str:
            logger.error(
                f"Token limit exceeded for session {session_id}. "
                f"Attempting recovery with minimal context."
            )
            
            # Emergency fallback: use only system prompt + current message
            minimal_messages = [
                {"role": "system", "content": system_with_lang},
                {"role": "user", "content": user_message}  # No context
            ]
            
            try:
                response = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=minimal_messages,
                    temperature=0.3,
                    max_tokens=600,
                )
                return response.choices[0].message.content.strip()
            except Exception as e2:
                logger.error(f"Recovery attempt failed: {e2}")
                raise HTTPException(
                    status_code=500,
                    detail="Context too large. Please start a new conversation."
                )
        
        # Re-raise other errors
        logger.error(f"OpenAI API error: {e}")
        raise


async def _generate_llm_response_async(
    user_message: str,
    context: str = "",
    cutoff_info: str = "",
    history: list[dict] | None = None,
    session_id: str = "unknown",
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Async version of _generate_llm_response for better performance.
    Uses AsyncOpenAI client to avoid blocking the event loop.
    """
    system = _get_system_prompt()
    
    # Add language instruction to system prompt
    lang_instruction = get_language_instruction(language)
    system_with_lang = f"{system}\n\n**IMPORTANT: {lang_instruction}**"
    
    client = _get_async_openai()

    user_content_parts = [f"User question: {user_message}"]

    if cutoff_info:
        user_content_parts.append(f"\n--- Cutoff Data (from database) ---\n{cutoff_info}")

    if context:
        user_content_parts.append(f"\n--- Retrieved Context ---\n{context}")

    if not cutoff_info and not context:
        user_content_parts.append(
            "\n[No specific context was retrieved. Answer based on general VNRVJIET knowledge "
            "in the system prompt, or state that the information is unavailable.]"
        )

    user_content = "\n".join(user_content_parts)

    # Smart history trimming (use sync client for now, can be optimized later)
    trimmed_history = []
    if history:
        try:
            # Use sync client for trimming (trim_history_smart is sync)
            sync_client = _get_openai()
            trimmed_history = trim_history_smart(
                history=history,
                system_prompt=system_with_lang,
                user_message=user_content,
                context=context,
                cutoff_info=cutoff_info,
                client=sync_client,
                model=settings.OPENAI_MODEL,
            )
        except Exception as e:
            logger.error(f"Failed to trim history smartly: {e}. Using basic trimming.")
            trimmed_history = history[-MAX_HISTORY:] if history else []

    # Build messages
    messages: list[dict] = [{"role": "system", "content": system_with_lang}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": user_content})

    # Log token usage
    try:
        log_token_usage(messages, settings.OPENAI_MODEL, session_id)
    except Exception as e:
        logger.warning(f"Failed to log token usage: {e}")

    # Call OpenAI async with error handling
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        error_str = str(e).lower()
        
        # Handle token limit errors
        if "maximum context length" in error_str or "token" in error_str:
            logger.error(
                f"Token limit exceeded for session {session_id}. "
                f"Attempting recovery with minimal context."
            )
            
            # Emergency fallback: use only system prompt + current message
            minimal_messages = [
                {"role": "system", "content": system_with_lang},
                {"role": "user", "content": user_message}  # No context
            ]
            
            try:
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=minimal_messages,
                    temperature=0.3,
                    max_tokens=600,
                )
                return response.choices[0].message.content.strip()
            except Exception as e2:
                logger.error(f"Recovery attempt failed: {e2}")
                raise HTTPException(
                    status_code=500,
                    detail="Context too large. Please start a new conversation."
                )
        
        # Re-raise other errors
        logger.error(f"OpenAI API error: {e}")
        raise


# ── Greeting handler ──────────────────────────────────────────

_GREETING_REPLY = (
    f"Hello! 👋 Welcome to the **{settings.COLLEGE_NAME} ({settings.COLLEGE_SHORT_NAME})** "
    "admissions assistant.\n\n"
    "I can help you with:\n"
    "• Admission process & eligibility\n"
    "• Branch-wise cutoff ranks\n"
    "• Required documents\n"
    "• Fee structure & scholarships\n"
    "• Campus & hostel information\n\n"
    "How can I assist you today?"
)

_OUT_OF_SCOPE_REPLY = (
    f"I can assist only with admissions information related to **{settings.COLLEGE_NAME}** "
    f"({settings.COLLEGE_SHORT_NAME}). "
    "For other colleges, please refer to their official websites or counselling authorities."
)


# ── Main endpoints ────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streaming chat endpoint - provides ChatGPT-like typing effect.
    
    Hybrid approach:
    - Uses cache for repeat questions (instant response)
    - Streams new responses token-by-token for better UX
    - Automatically saves streamed responses to cache
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    
    user_msg = sanitise_input(req.message)
    session_id = req.session_id or str(uuid.uuid4())
    
    if not user_msg:
        async def error_stream():
            yield f"data: {json.dumps({'error': 'Message cannot be empty', 'done': True})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    # Get current language
    current_language = _session_language.get(session_id, DEFAULT_LANGUAGE)
    if req.language and req.language in SUPPORTED_LANGUAGES:
        current_language = req.language
        _session_language[session_id] = current_language
    else:
        detected_lang = detect_language(user_msg)
        if detected_lang != current_language:
            current_language = detected_lang
            _session_language[session_id] = detected_lang
    
    async def generate():
        try:
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 0: Check if session is in document flow (HIGHEST PRIORITY)
            # This must execute BEFORE fee flow, intent classification, and RAG retrieval
            # ═══════════════════════════════════════════════════════════
            if session_id in _session_pending_document_flow:
                pending = _session_pending_document_flow[session_id]
                waiting_for = pending.get("_waiting_for")
                
                # Check for topic change
                if _is_topic_change(user_msg, current_flow="document_flow"):
                    logger.info(f"Topic change detected during document flow for session {session_id}")
                    del _session_pending_document_flow[session_id]
                    # Fall through to normal processing below
                else:
                    # Continue document flow - handle course/category collection
                    if waiting_for == "course":
                        course = _resolve_course_response(user_msg)
                        if course:
                            pending["course"] = course
                            pending["_waiting_for"] = "category"
                            
                            # Ask for category based on course
                            category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(course)
                            if category_config:
                                ask = category_config["question"]
                                options = category_config.get("clickable_options", [])
                                
                                # Stream the question
                                words = ask.split()
                                for word in words:
                                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                    await asyncio.sleep(0.02)
                                yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'document_flow', 'session_id': session_id, 'options': options})}\n\n"
                                
                                _session_history[session_id].append({"role": "user", "content": user_msg})
                                _session_history[session_id].append({"role": "assistant", "content": ask})
                                return
                        else:
                            # Invalid course response
                            ask = (
                                "I didn't understand that. Please choose one:\n\n"
                                + _DOCUMENT_FLOW_QUESTIONS["course"]["question"]
                            )
                            options = _DOCUMENT_FLOW_QUESTIONS["course"].get("clickable_options", [])
                            words = ask.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'document_flow', 'session_id': session_id, 'options': options})}\n\n"
                            
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": ask})
                            return
                    
                    elif waiting_for == "category":
                        course = pending.get("course")
                        category = _resolve_category_response(user_msg, course)
                        
                        if category:
                            # Both course and category collected - construct refined query
                            del _session_pending_document_flow[session_id]
                            
                            refined_query = f"Required documents for {course} {category} admission"
                            logger.info(
                                f"Document flow completed for session {session_id}: "
                                f"course={course}, category={category}"
                            )
                            
                            # Now retrieve context using refined query
                            try:
                                rag_result = await retrieve_async(refined_query, top_k=8)
                                doc_context = rag_result.context_text
                                doc_sources = list({
                                    f"{c.filename} ({c.source})" for c in rag_result.chunks
                                })
                            except Exception as e:
                                logger.error("RAG retrieval failed during document flow: %s", e, exc_info=True)
                                doc_context = ""
                                doc_sources = []
                            
                            # Stream LLM response with document context
                            system = _get_system_prompt()
                            lang_instruction = get_language_instruction(current_language)
                            system_with_lang = f"{system}\n\n**IMPORTANT: {lang_instruction}**"
                            
                            user_content = f"User question: {refined_query}\n\n--- Context ---\n{doc_context}"
                            
                            history = _session_history.get(session_id, [])
                            trimmed_history = history[-MAX_HISTORY:] if history else []
                            
                            messages = [{"role": "system", "content": system_with_lang}]
                            messages.extend(trimmed_history)
                            messages.append({"role": "user", "content": user_content})
                            
                            # Stream from OpenAI
                            client = _get_async_openai()
                            stream = await client.chat.completions.create(
                                model=settings.OPENAI_MODEL,
                                messages=messages,
                                temperature=0.3,
                                max_tokens=600,
                                stream=True,
                            )
                            
                            full_reply = ""
                            async for chunk in stream:
                                if chunk.choices[0].delta.content:
                                    token = chunk.choices[0].delta.content
                                    full_reply += token
                                    yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                            
                            # Send completion signal with metadata
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'informational', 'sources': doc_sources, 'session_id': session_id})}\n\n"
                            
                            # Update history
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": full_reply})
                            return
                        else:
                            # Invalid category response
                            category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(course)
                            ask = (
                                "I didn't understand that. Please choose one:\n\n"
                                + (category_config["question"] if category_config else "Please specify the admission category.")
                            )
                            words = ask.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'document_flow', 'session_id': session_id})}\n\n"
                            
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": ask})
                            return
            
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 1: Check if this is a NEW document query
            # Detect and start document flow BEFORE fee flow, classification, and RAG
            # ═══════════════════════════════════════════════════════════
            if _detect_document_query(user_msg):
                # Check if user already provided both course and category
                detected_course = _extract_course_from_message(user_msg)
                detected_category = None
                if detected_course:
                    detected_category = _extract_category_from_message(user_msg, detected_course)
                
                if detected_course and detected_category:
                    # User provided both - construct refined query and continue to RAG
                    refined_query = f"Required documents for {detected_course} {detected_category} admission"
                    logger.info(
                        f"Document query with both course and category: "
                        f"course={detected_course}, category={detected_category}"
                    )
                    # Override user_msg for RAG but DON'T start flow - just fall through
                    # Set a flag to use refined query later
                    user_msg_override = refined_query
                elif not detected_course:
                    # Start document flow - ask for course
                    _session_pending_document_flow[session_id] = {
                        "_waiting_for": "course",
                    }
                    ask = _DOCUMENT_FLOW_QUESTIONS["course"]["question"]
                    options = _DOCUMENT_FLOW_QUESTIONS["course"].get("clickable_options", [])
                    logger.info(f"Document flow started for session {session_id}")
                    
                    # Stream the question
                    words = ask.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'document_flow', 'session_id': session_id, 'options': options})}\n\n"
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return
                else:
                    # Has course but no category - ask for category
                    _session_pending_document_flow[session_id] = {
                        "course": detected_course,
                        "_waiting_for": "category",
                    }
                    category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(detected_course)
                    ask = category_config["question"] if category_config else "Please specify the admission category."
                    options = category_config.get("clickable_options", []) if category_config else []
                    logger.info(f"Document flow started (course detected) for session {session_id}: course={detected_course}")
                    
                    # Stream the question
                    words = ask.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'document_flow', 'session_id': session_id, 'options': options})}\n\n"
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return
            
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 2: Check if session is in fee flow
            # This must execute BEFORE intent classification and RAG
            # Provides focused, layered guidance for fee structure queries
            # ═══════════════════════════════════════════════════════════
            if session_id in _session_pending_fee_flow:
                pending = _session_pending_fee_flow[session_id]
                waiting_for = pending.get("_waiting_for")
                
                # Check for topic change
                if _is_topic_change(user_msg, current_flow="fee_flow"):
                    logger.info(f"Topic change detected during fee flow for session {session_id}")
                    del _session_pending_fee_flow[session_id]
                    # Fall through to normal processing below
                else:
                    # Continue fee flow - handle course/category/fee_type collection
                    if waiting_for == "course":
                        course = _resolve_fee_course_response(user_msg)
                        if course:
                            pending["course"] = course
                            pending["_waiting_for"] = "category"
                            
                            # Ask for category based on course
                            category_config = _FEE_FLOW_QUESTIONS["category"].get(course)
                            if category_config:
                                ask = category_config["question"]
                                options = category_config.get("clickable_options", [])
                                
                                # Stream the question
                                words = ask.split()
                                for word in words:
                                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                    await asyncio.sleep(0.02)
                                yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                                
                                _session_history[session_id].append({"role": "user", "content": user_msg})
                                _session_history[session_id].append({"role": "assistant", "content": ask})
                                return
                        else:
                            # Invalid course response
                            ask = (
                                "I didn't understand that. Please choose one:\n\n"
                                + _FEE_FLOW_QUESTIONS["course"]["question"]
                            )
                            options = _FEE_FLOW_QUESTIONS["course"].get("clickable_options", [])
                            words = ask.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                            
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": ask})
                            return
                    
                    elif waiting_for == "category":
                        course = pending.get("course")
                        category = _resolve_fee_category_response(user_msg, course)
                        
                        if category:
                            pending["category"] = category
                            
                            # Check if fee type is needed
                            # Skip if query already clearly indicates fee type
                            fee_type_from_original = pending.get("_original_fee_type")
                            if fee_type_from_original:
                                # Fee type was already clear from original query
                                pending["fee_type"] = fee_type_from_original
                                # Complete flow - construct refined query
                                del _session_pending_fee_flow[session_id]
                                
                                refined_query = f"{pending['fee_type']} for {course} {category} at VNRVJIET"
                                logger.info(
                                    f"Fee flow completed for session {session_id}: "
                                    f"course={course}, category={category}, fee_type={pending['fee_type']}"
                                )
                                
                                # Fall through to RAG retrieval below
                                # Set a flag to use refined query
                                user_msg_override = refined_query
                            else:
                                # Ask for fee type
                                pending["_waiting_for"] = "fee_type"
                                ask = _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                                options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                                
                                # Stream the question
                                words = ask.split()
                                for word in words:
                                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                    await asyncio.sleep(0.02)
                                yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                                
                                _session_history[session_id].append({"role": "user", "content": user_msg})
                                _session_history[session_id].append({"role": "assistant", "content": ask})
                                return
                        else:
                            # Invalid category response
                            category_config = _FEE_FLOW_QUESTIONS["category"].get(course)
                            ask = (
                                "I didn't understand that. Please choose one:\n\n"
                                + (category_config["question"] if category_config else "Please specify the admission category.")
                            )
                            options = category_config.get("clickable_options", []) if category_config else []
                            words = ask.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                            
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": ask})
                            return
                    
                    elif waiting_for == "fee_type":
                        fee_type = _resolve_fee_type_response(user_msg)
                        
                        if fee_type:
                            # All info collected - construct refined query
                            pending["fee_type"] = fee_type
                            del _session_pending_fee_flow[session_id]
                            
                            course = pending["course"]
                            category = pending["category"]
                            refined_query = f"{fee_type} for {course} {category} at VNRVJIET"
                            
                            logger.info(
                                f"Fee flow completed for session {session_id}: "
                                f"course={course}, category={category}, fee_type={fee_type}"
                            )
                            
                            # Fall through to RAG below - set override
                            user_msg_override = refined_query
                        else:
                            # Invalid fee type response
                            ask = (
                                "I didn't understand that. Please choose one:\n\n"
                                + _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                            )
                            options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                            words = ask.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                            
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": ask})
                            return
                
                # If we reach here with user_msg_override set, proceed to RAG
                if 'user_msg_override' in locals():
                    # Retrieve context using refined query
                    try:
                        rag_result = await retrieve_async(user_msg_override, top_k=8)
                        fee_context = rag_result.context_text
                        fee_sources = list({
                            f"{c.filename} ({c.source})" for c in rag_result.chunks
                        })
                    except Exception as e:
                        logger.error("RAG retrieval failed during fee flow: %s", e, exc_info=True)
                        fee_context = ""
                        fee_sources = []
                    
                    # Stream LLM response with fee context
                    system = _get_system_prompt()
                    lang_instruction = get_language_instruction(current_language)
                    system_with_lang = f"{system}\n\n**IMPORTANT: {lang_instruction}**"
                    
                    user_content = f"User question: {user_msg_override}\n\n--- Context ---\n{fee_context}"
                    
                    history = _session_history.get(session_id, [])
                    trimmed_history = history[-MAX_HISTORY:] if history else []
                    
                    messages = [{"role": "system", "content": system_with_lang}]
                    messages.extend(trimmed_history)
                    messages.append({"role": "user", "content": user_content})
                    
                    # Stream from OpenAI
                    client = _get_async_openai()
                    stream = await client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=600,
                        stream=True,
                    )
                    
                    full_reply = ""
                    async for chunk in stream:
                        if chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            full_reply += token
                            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                    
                    # Send completion signal with metadata
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'informational', 'sources': fee_sources, 'session_id': session_id})}\n\n"
                    
                    # Update history
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": full_reply})
                    return
            
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 3: Detect NEW fee query
            # Start fee flow if query is about fees/scholarships
            # ═══════════════════════════════════════════════════════════
            if _detect_fee_query(user_msg):
                # Check if user already provided course and/or category
                detected_course = _extract_course_from_message(user_msg)
                detected_category = None
                if detected_course:
                    detected_category = _extract_fee_category_from_message(user_msg, detected_course)
                
                # Check if fee type is clear from query
                detected_fee_type = _extract_fee_type_from_message(user_msg)
                
                # Smart flow: skip layers if info is already provided
                if detected_course and detected_category and detected_fee_type:
                    # User provided everything - construct refined query and go to RAG
                    refined_query = f"{detected_fee_type} for {detected_course} {detected_category} at VNRVJIET"
                    logger.info(
                        f"Fee query with all details: "
                        f"course={detected_course}, category={detected_category}, fee_type={detected_fee_type}"
                    )
                    # Set override to use refined query
                    user_msg_override = refined_query
                    # Continue to normal flow with override
                elif detected_course and detected_category:
                    # Has course and category but no fee type
                    # Check if fee type is implicitly clear
                    if _is_fee_type_clear_from_query(user_msg):
                        # Fee type is clear enough - continue to RAG
                        fee_type_inferred = detected_fee_type or "fee structure"
                        refined_query = f"{fee_type_inferred} for {detected_course} {detected_category} at VNRVJIET"
                        logger.info(f"Fee query with inferred fee type: {refined_query}")
                        user_msg_override = refined_query
                        # Continue to normal flow
                    else:
                        # Ask for fee type
                        _session_pending_fee_flow[session_id] = {
                            "course": detected_course,
                            "category": detected_category,
                            "_waiting_for": "fee_type",
                        }
                        ask = _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                        options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                        logger.info(f"Fee flow started (course+category detected) for session {session_id}")
                        
                        # Stream the question
                        words = ask.split()
                        for word in words:
                            yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                            await asyncio.sleep(0.02)
                        yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                        
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": ask})
                        return
                elif detected_course:
                    # Has course but no category - ask for category
                    _session_pending_fee_flow[session_id] = {
                        "course": detected_course,
                        "_waiting_for": "category",
                    }
                    # Store detected fee type if present
                    if detected_fee_type:
                        _session_pending_fee_flow[session_id]["_original_fee_type"] = detected_fee_type
                    
                    category_config = _FEE_FLOW_QUESTIONS["category"].get(detected_course)
                    ask = category_config["question"] if category_config else "Please specify the admission category."
                    options = category_config.get("clickable_options", []) if category_config else []
                    logger.info(f"Fee flow started (course detected) for session {session_id}: course={detected_course}")
                    
                    # Stream the question
                    words = ask.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return
                else:
                    # No course detected - start fee flow from beginning
                    _session_pending_fee_flow[session_id] = {
                        "_waiting_for": "course",
                    }
                    # Store detected fee type if present
                    if detected_fee_type:
                        _session_pending_fee_flow[session_id]["_original_fee_type"] = detected_fee_type
                    
                    ask = _FEE_FLOW_QUESTIONS["course"]["question"]
                    options = _FEE_FLOW_QUESTIONS["course"].get("clickable_options", [])
                    logger.info(f"Fee flow started for session {session_id}")
                    
                    # Stream the question
                    words = ask.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'fee_flow', 'session_id': session_id, 'options': options})}\n\n"
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return
            
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 4: Check if session is in cutoff flow (EXISTING SESSION HANDLER)
            # This must execute BEFORE new cutoff detection and intent classification
            # ═══════════════════════════════════════════════════════════
            if session_id in _session_cutoff_data:
                collected_s = _session_cutoff_data[session_id]
                flow_s = collected_s.get("_flow", "cutoff")
                is_elig_s = (flow_s == "eligibility")

                # Dynamic re-extraction on every reply
                if "branch" not in collected_s:
                    _sb = extract_branches(user_msg)
                    # When actively waiting for branch, allow ALL and also fall back
                    # to raw input so short answers like "AID" or "all" are accepted.
                    if collected_s.get("_waiting_for") == "branch":
                        if _sb:
                            collected_s["branch"] = _sb  # includes ["ALL"]
                        else:
                            # Check if user said some variant of "all"
                            _um_b = user_msg.strip().lower()
                            if re.search(r"\b(all|every|each|any)\b", _um_b):
                                collected_s["branch"] = ["ALL"]
                            elif _um_b:  # treat raw input as a branch code
                                collected_s["branch"] = [user_msg.strip().upper()]
                    elif _sb and "ALL" not in _sb:
                        collected_s["branch"] = _sb
                if "category" not in collected_s:
                    _sc = extract_category(user_msg)
                    if not _sc and collected_s.get("_waiting_for") == "category":
                        _um_c = user_msg.strip().lower()
                        if re.search(r"\b(all|every|each|any)\b", _um_c):
                            _sc = "ALL"
                        elif user_msg.strip():
                            _sc = user_msg.strip().upper()  # treat as raw category
                    if _sc:
                        collected_s["category"] = _sc
                if "gender" not in collected_s:
                    _sg = extract_gender(user_msg)
                    # When the pipeline is actively waiting for gender, apply an
                    # extended check: a short standalone reply like "1", "b", "g",
                    # "m", "f" or number-style answers should also be resolved here.
                    if not _sg and collected_s.get("_waiting_for") == "gender":
                        _um = user_msg.lower().strip()
                        if _um in ("1", "m", "b", "male", "boy"):
                            _sg = "Boys"
                        elif _um in ("2", "f", "g", "female", "girl"):
                            _sg = "Girls"
                        elif _um in ("3", "0", "a", "all", "both", "either", "any"):
                            _sg = "ALL"
                    if _sg:
                        collected_s["gender"] = _sg
                if "year" not in collected_s:
                    _sy = extract_year(user_msg)
                    if _sy:
                        collected_s["year"] = _sy
                    elif re.search(r"\b(latest|recent|current|now|last)\b", user_msg, re.I):
                        collected_s["year"] = None  # use latest available
                if is_elig_s and "rank" not in collected_s:
                    _sr = extract_rank(user_msg)
                    if _sr:
                        collected_s["rank"] = _sr

                _qs = _ELIGIBILITY_QUESTIONS if is_elig_s else _CUTOFF_QUESTIONS
                _req_s = [f for f, _ in _qs]
                _done_s = all(f in collected_s for f in _req_s)

                if _done_s:
                    _bl = collected_s["branch"]
                    if isinstance(_bl, str):
                        _bl = [_bl]
                    _cutoff_r = _build_multi_branch_reply(
                        _bl,
                        collected_s["category"],
                        collected_s.get("gender"),
                        collected_s.get("rank") if is_elig_s else None,
                        show_trend=collected_s.get("_show_trend", False),
                        year=collected_s.get("year"),
                    )
                    _session_last_cutoff[session_id] = {
                        "branch": _bl,
                        "category": collected_s["category"],
                        "gender": collected_s.get("gender"),
                        "year": collected_s.get("year"),
                    }
                    del _session_cutoff_data[session_id]
                    words = _cutoff_r.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.015)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'cutoff', 'sources': ['VNRVJIET Cutoff Database'], 'session_id': session_id})}\n\n"
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": _cutoff_r})
                    return
                else:
                    # Ask next missing field
                    for _fld, _qtmpl in _qs:
                        if _fld not in collected_s:
                            collected_s["_waiting_for"] = _fld
                            if _fld == "branch":
                                avail_b = list_branches()
                                _ask_s = _qtmpl.format(branches=", ".join(avail_b))
                            else:
                                _ask_s = _qtmpl
                            words = _ask_s.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'cutoff', 'session_id': session_id})}\n\n"
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": _ask_s})
                            return

            # ── Branch-change follow-up (stream): inherit previous cutoff context ────
            # Catches queries like "what about CSM and CSO?" sent after a prior cutoff
            # answer.  These messages carry branch codes but no category / year keywords,
            # so the classifier often returns INFORMATIONAL.  We intercept here and serve
            # Firestore data directly — the LLM is never involved.
            elif (
                extract_branches(user_msg)
                and session_id in _session_last_cutoff
                and not extract_category(user_msg)
            ):
                _last_s = _session_last_cutoff[session_id]
                _follow_branches = extract_branches(user_msg)
                _follow_category = _last_s.get("category")
                _follow_gender = extract_gender(user_msg) or _last_s.get("gender")
                _follow_year = extract_year(user_msg)
                if _follow_year is None and _last_s.get("year") is not None:
                    _follow_year = _last_s["year"]
                elif re.search(r"\b(latest|recent|current|now|last)\b", user_msg, re.I):
                    _follow_year = None
                if _follow_category and _follow_branches:
                    _follow_reply = _build_multi_branch_reply(
                        _follow_branches, _follow_category, _follow_gender,
                        rank=None, show_trend=_detect_trend_request(user_msg),
                        year=_follow_year,
                    )
                    _session_last_cutoff[session_id] = {
                        "branch": _follow_branches,
                        "category": _follow_category,
                        "gender": _follow_gender,
                        "year": _follow_year,
                    }
                    words = _follow_reply.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.015)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'cutoff', 'sources': ['VNRVJIET Cutoff Database'], 'session_id': session_id})}\n\n"
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": _follow_reply})
                    return

            # ── New cutoff / eligibility query (no active session) ───────────
            # Only start a fresh collection pipeline when the intent is cutoff/eligibility.
            elif intent in (IntentType.CUTOFF, IntentType.ELIGIBILITY):
                is_elig_n = (intent == IntentType.ELIGIBILITY)
                _flow_n = "eligibility" if is_elig_n else "cutoff"
                _qs_n = _ELIGIBILITY_QUESTIONS if is_elig_n else _CUTOFF_QUESTIONS
                _coll_n: dict = {"_flow": _flow_n}
                
                if _detect_trend_request(user_msg):
                    _coll_n["_show_trend"] = True
                
                # Extract any provided information
                _bn = extract_branches(user_msg)
                # Allow ALL on first message only when user explicitly says "all branches"
                # (not a bare "all" which is ambiguous in context of the first query).
                _all_explicit = bool(re.search(
                    r"\ball\s*(?:branch|dept|depart|stream|course|program)|"
                    r"(?:branch|dept|depart|stream|course|program)\s*all",
                    user_msg, re.I
                ))
                if _bn:
                    if "ALL" not in _bn or _all_explicit:
                        _coll_n["branch"] = _bn
                _cn = extract_category(user_msg)
                if _cn:
                    _coll_n["category"] = _cn
                _gn = extract_gender(user_msg)
                if _gn:
                    _coll_n["gender"] = _gn
                _yn = extract_year(user_msg)
                if _yn:
                    _coll_n["year"] = _yn
                elif re.search(r"\b(latest|recent|current|now|last)\b", user_msg, re.I):
                    _coll_n["year"] = None  # use latest available
                _rn = extract_rank(user_msg)
                if _rn and is_elig_n:
                    _coll_n["rank"] = _rn

                # ── Context inheritance for branch-change follow-ups (stream) ──────
                # If user provides branches but omits category/gender/year, inherit
                # those filters from the previous cutoff query in this session.
                if (
                    "branch" in _coll_n
                    and session_id in _session_last_cutoff
                    and "category" not in _coll_n
                ):
                    _prev_s = _session_last_cutoff[session_id]
                    if _prev_s.get("category"):
                        _coll_n["category"] = _prev_s["category"]
                    if "gender" not in _coll_n and _prev_s.get("gender"):
                        _coll_n["gender"] = _prev_s["gender"]
                    if "year" not in _coll_n and _prev_s.get("year") is not None:
                        _coll_n["year"] = _prev_s["year"]

                _req_n = [f for f, _ in _qs_n]
                _done_n = all(f in _coll_n for f in _req_n)

                if _done_n:
                    # All information collected - provide answer immediately
                    _bl_n = _coll_n["branch"]
                    if isinstance(_bl_n, str):
                        _bl_n = [_bl_n]
                    _cr_n = _build_multi_branch_reply(
                        _bl_n, _coll_n["category"], _coll_n.get("gender"),
                        _coll_n.get("rank") if is_elig_n else None,
                        show_trend=_coll_n.get("_show_trend", False),
                        year=_coll_n.get("year"),
                    )
                    _session_last_cutoff[session_id] = {
                        "branch": _bl_n, "category": _coll_n["category"],
                        "gender": _coll_n.get("gender"), "year": _coll_n.get("year"),
                    }
                    words = _cr_n.split()
                    for word in words:
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        await asyncio.sleep(0.015)
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'cutoff', 'sources': ['VNRVJIET Cutoff Database'], 'session_id': session_id})}\n\n"
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": _cr_n})
                    return
                else:
                    # Start step-by-step collection — ask first missing field
                    for _fld_n, _qtmpl_n in _qs_n:
                        if _fld_n not in _coll_n:
                            _coll_n["_waiting_for"] = _fld_n
                            _clear_other_pipelines(session_id, keep="cutoff")
                            _session_cutoff_data[session_id] = _coll_n
                            _intro_n = "Sure! Let me help you check your eligibility." if is_elig_n else "Sure! Let me show you the cutoff ranks."
                            if _fld_n == "branch":
                                avail_b_n = list_branches()
                                _ask_n = f"{_intro_n}\n\n{_qtmpl_n.format(branches=', '.join(avail_b_n))}"
                            else:
                                _ask_n = _qtmpl_n
                            words = _ask_n.split()
                            for word in words:
                                yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                                await asyncio.sleep(0.02)
                            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'cutoff', 'session_id': session_id})}\n\n"
                            _session_history[session_id].append({"role": "user", "content": user_msg})
                            _session_history[session_id].append({"role": "assistant", "content": _ask_n})
                            return
            
            # ═══════════════════════════════════════════════════════════
            # PRIORITY 6: Normal flow - Intent classification and processing
            # Only reached if NOT in fee, document, or cutoff flow
            # ═══════════════════════════════════════════════════════════
            
            # Extract query data
            branch = extract_branch(user_msg)
            category = extract_category(user_msg)
            gender = extract_gender(user_msg)
            rank = extract_rank(user_msg)
            year = extract_year(user_msg)
            
            # Use overridden query if set (for document queries with both course and category)
            query_for_processing = locals().get('user_msg_override', user_msg)
            
            # Classify intent
            classification = classify(query_for_processing)
            intent = classification.intent
            
            # Check cache first for informational queries
            if intent == IntentType.INFORMATIONAL:
                cached = _get_cached_response(query_for_processing, intent.value, current_language)
                if cached:
                    reply, cached_sources = cached
                    logger.info(f"Cache HIT (streaming): {query_for_processing[:50]}...")
                    
                    # Stream cached response word by word for consistent UX
                    words = reply.split()
                    for i, word in enumerate(words):
                        yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                        if i % 5 == 0:  # Brief pause every 5 words
                            await asyncio.sleep(0.02)
                    
                    # Send metadata
                    yield f"data: {json.dumps({'token': '', 'done': True, 'intent': intent.value, 'sources': cached_sources, 'session_id': session_id})}\n\n"
                    
                    # Update history
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": reply})
                    return
            
            # Handle greetings quickly (no streaming needed)
            if intent == IntentType.GREETING:
                greeting = get_greeting_message(current_language)
                words = greeting.split()
                for word in words:
                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                    await asyncio.sleep(0.02)
                yield f"data: {json.dumps({'token': '', 'done': True, 'intent': 'greeting', 'session_id': session_id})}\n\n"
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": greeting})
                return
            
            # For complex queries, gather context and stream LLM response
            rag_context = ""
            cutoff_info = ""
            sources = []

            # ═══════════════════════════════════════════════════════════
            # PRIORITY 7: KNOWLEDGE-FIRST RAG - Search knowledge database first
            # Skip RAG for cutoff/eligibility queries (already handled above)
            # ═══════════════════════════════════════════════════════════
            _kf_cutoff_indicators = [
                "cutoff", "cut off", "cut-off", "closing rank", "last rank",
                "eapcet", "tseamcet", "ts eamcet", "opening rank", "counselling",
                "eligible", "eligibility", "can i get", "will i get", "my rank",
            ]
            _kf_skip_stream = any(kw in user_msg.lower() for kw in _kf_cutoff_indicators)
            if not _kf_skip_stream:
                try:
                    top_k = 8 if intent == IntentType.MIXED else 5
                    rag_result = await retrieve_async(query_for_processing, top_k=top_k)
                    rag_context = rag_result.context_text
                    for chunk in rag_result.chunks:
                        sources.append(f"{chunk.filename} ({chunk.source})")
                    logger.info(
                        "Knowledge-First RAG (stream): retrieved %d chunks, context length: %d chars",
                        len(rag_result.chunks),
                        len(rag_context),
                    )
                except Exception as e:
                    logger.error("Knowledge-First RAG (stream) failed: %s", e)
                    rag_context = ""

            # ═══════════════════════════════════════════════════════════
            # PRIORITY 8: Regular RAG retrieval for non-cutoff queries
            # CUTOFF/ELIGIBILITY data comes exclusively from Firestore
            # ═══════════════════════════════════════════════════════════
            if not rag_context and not _detect_cutoff_query(user_msg):
                try:
                    top_k = 8 if intent == IntentType.MIXED else 6
                    rag_result = await retrieve_async(query_for_processing, top_k=top_k)
                    rag_context = rag_result.context_text
                    for chunk in rag_result.chunks:
                        sources.append(f"{chunk.filename} ({chunk.source})")
                    logger.info(
                        "RAG (stream) retrieved %d chunks (intent=%s), context length: %d chars",
                        len(rag_result.chunks),
                        intent.value,
                        len(rag_context),
                    )
                except Exception as e:
                    logger.error(f"RAG retrieval failed: {e}")
            
            # Stream LLM response
            system = _get_system_prompt()
            lang_instruction = get_language_instruction(current_language)
            system_with_lang = f"{system}\n\n**IMPORTANT: {lang_instruction}**"
            
            user_content_parts = [f"User question: {query_for_processing}"]
            if cutoff_info:
                user_content_parts.append(f"\n--- Cutoff Data ---\n{cutoff_info}")
            if rag_context:
                user_content_parts.append(f"\n--- Context ---\n{rag_context}")
            user_content = "\n".join(user_content_parts)
            
            history = _session_history.get(session_id, [])
            trimmed_history = history[-MAX_HISTORY:] if history else []
            
            messages = [{"role": "system", "content": system_with_lang}]
            messages.extend(trimmed_history)
            messages.append({"role": "user", "content": user_content})
            
            # Stream from OpenAI
            client = _get_async_openai()
            stream = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=600,
                stream=True,
            )
            
            full_reply = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply += token
                    yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
            
            # Send completion signal with metadata
            yield f"data: {json.dumps({'token': '', 'done': True, 'intent': intent.value, 'sources': list(set(sources)), 'session_id': session_id})}\n\n"
            
            # Cache the response for future use
            if intent == IntentType.INFORMATIONAL:
                _cache_response(query_for_processing, intent.value, full_reply, sources, current_language)
            
            # Update history
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": full_reply})
            
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """
    Process a user query through the hybrid RAG + cutoff pipeline.
    """
    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

     # Sanitise
    user_msg = sanitise_input(req.message)
    session_id = req.session_id or str(uuid.uuid4())

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # ── Language detection and management ──────────────────────
    # Get current language for this session (default to English if not set)
    current_language = _session_language.get(session_id, DEFAULT_LANGUAGE)
    
    # Update language from request if provided (explicit language selection from UI)
    if req.language and req.language in SUPPORTED_LANGUAGES:
        current_language = req.language
        _session_language[session_id] = current_language
    else:
        # Dynamic language detection - always detect from user input
        detected_lang = detect_language(user_msg)
        
        # If detected language differs from current language, automatically switch
        # This enables seamless language adaptation during conversation
        if detected_lang != current_language:
            logger.info(
                f"Language change detected for session {session_id}: "
                f"{current_language} -> {detected_lang}"
            )
            current_language = detected_lang
            _session_language[session_id] = detected_lang
    
    # Check if user is requesting language change (e.g., "switch to Hindi")
    lang_change_request = detect_language_change_request(user_msg, current_language)
    if lang_change_request:
        if lang_change_request == "show_selector":
            # Show language selector
            reply = get_language_selector_message(current_language)
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(
                reply=reply,
                intent="language_selection",
                session_id=session_id,
                language=current_language,
            )
        else:
            # Change to specific language
            current_language = lang_change_request
            _session_language[session_id] = current_language
            reply = get_translation("language_changed", current_language)
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(
                reply=reply,
                intent="language_changed",
                session_id=session_id,
                language=current_language,
            )

    # ── Check if pending web search permission ────────────────
    if session_id in _session_pending_websearch:
        original_query = _session_pending_websearch[session_id]
        
        if _is_yes_response(user_msg):
            # User agreed - fetch website
            del _session_pending_websearch[session_id]
            
            try:
                # Determine which URL to fetch
                url_category = _detect_url_category(original_query)
                
                # Check if it's a department-specific URL
                if url_category.startswith("dept_"):
                    dept_key = url_category.replace("dept_", "")
                    url_to_fetch = settings.DEPARTMENT_URLS.get(dept_key, settings.VNRVJIET_WEBSITE_URLS["departments"])
                else:
                    url_to_fetch = settings.VNRVJIET_WEBSITE_URLS.get(url_category, settings.VNRVJIET_WEBSITE_URLS["general"])
                
                # Load and use fetch_webpage tool
                from app.utils.web_fetcher import fetch_webpage_content
                web_content = fetch_webpage_content(url_to_fetch)
                
                # Generate response using web content
                history = _session_history.get(session_id, [])
                reply = _generate_llm_response(
                    original_query,
                    web_content[:4000],  # Limit content to 4000 chars
                    "",  # No cutoff info
                    history=history,
                    session_id=session_id,
                    language=current_language
                )
                
                _session_history[session_id].append({"role": "user", "content": original_query})
                _session_history[session_id].append({"role": "assistant", "content": reply})
                
                return ChatResponse(
                    reply=reply,
                    intent="informational",
                    session_id=session_id,
                    sources=[f"VNRVJIET Website ({url_to_fetch})"],
                    language=current_language,
                )
                
            except Exception as e:
                logger.error(f"Web fetch failed: {e}", exc_info=True)
                reply = (
                    "I tried searching our website but encountered an issue. "
                    "Please contact our admissions office directly:\n\n"
                    "📧 admissionsenquiry@vnrvjiet.in\n"
                    "📞 +91-40-2304 2758/59/60"
                )
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": reply})
                return ChatResponse(reply=reply, intent="informational", session_id=session_id, language=current_language)
        
        elif _is_no_response(user_msg):
            # User declined web search
            del _session_pending_websearch[session_id]
            reply = (
                "No problem! If you have any other questions, feel free to ask. "
                "You can also contact our admissions team directly:\n\n"
                "📧 admissionsenquiry@vnrvjiet.in\n"
                "📞 +91-40-2304 2758/59/60"
            )
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(reply=reply, intent="informational", session_id=session_id, language=current_language)
        
        else:
            # Unclear response - ask again
            reply = "I didn't quite understand. Would you like me to search our official website? Please reply **yes** or **no**."
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(reply=reply, intent="web_search_permission", session_id=session_id, language=current_language)

    # ── Check if session is in fee flow (HIGHEST PRIORITY) ────
    # This must execute BEFORE document flow, intent classification, and RAG
    if session_id in _session_pending_fee_flow:
        pending = _session_pending_fee_flow[session_id]
        waiting_for = pending.get("_waiting_for")
        
        # Check for topic change
        if _is_topic_change(user_msg, current_flow="fee_flow"):
            logger.info(f"Topic change detected during fee flow for session {session_id}")
            del _session_pending_fee_flow[session_id]
            # Fall through to normal processing below
        else:
            if waiting_for == "course":
                course = _resolve_fee_course_response(user_msg)
                if course:
                    pending["course"] = course
                    pending["_waiting_for"] = "category"
                    
                    # Ask for category based on course
                    category_config = _FEE_FLOW_QUESTIONS["category"].get(course)
                    if category_config:
                        ask = category_config["question"]
                        options = category_config.get("clickable_options", [])
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": ask})
                        return ChatResponse(
                            reply=ask,
                            intent="fee_flow",
                            session_id=session_id,
                            language=current_language,
                            options=options,
                        )
                else:
                    # Invalid course response
                    ask = (
                        "I didn't understand that. Please choose one:\n\n"
                        + _FEE_FLOW_QUESTIONS["course"]["question"]
                    )
                    options = _FEE_FLOW_QUESTIONS["course"].get("clickable_options", [])
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(
                        reply=ask,
                        intent="fee_flow",
                        session_id=session_id,
                        language=current_language,
                        options=options,
                    )
            
            elif waiting_for == "category":
                course = pending.get("course")
                category = _resolve_fee_category_response(user_msg, course)
                
                if category:
                    pending["category"] = category
                    
                    # Check if fee type is needed
                    fee_type_from_original = pending.get("_original_fee_type")
                    if fee_type_from_original:
                        # Fee type was already clear from original query - complete flow
                        pending["fee_type"] = fee_type_from_original
                        del _session_pending_fee_flow[session_id]
                        
                        refined_query = f"{pending['fee_type']} for {course} {category} at VNRVJIET"
                        logger.info(
                            f"Fee flow completed for session {session_id}: "
                            f"course={course}, category={category}, fee_type={pending['fee_type']}"
                        )
                        
                        # Retrieve and generate response
                        try:
                            rag_result = await retrieve_async(refined_query, top_k=8)
                            fee_context = rag_result.context_text
                            fee_sources = list({
                                f"{c.filename} ({c.source})" for c in rag_result.chunks
                            })
                        except Exception as e:
                            logger.error("RAG retrieval failed during fee flow: %s", e, exc_info=True)
                            fee_context = ""
                            fee_sources = []
                        
                        history = _session_history.get(session_id, [])
                        fee_reply = await _generate_llm_response_async(
                            refined_query,
                            fee_context,
                            "",
                            history=history,
                            session_id=session_id,
                            language=current_language,
                        )
                        
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": fee_reply})
                        
                        return ChatResponse(
                            reply=fee_reply,
                            intent="informational",
                            session_id=session_id,
                            sources=fee_sources,
                            language=current_language,
                        )
                    else:
                        # Ask for fee type
                        pending["_waiting_for"] = "fee_type"
                        ask = _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                        options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": ask})
                        return ChatResponse(
                            reply=ask,
                            intent="fee_flow",
                            session_id=session_id,
                            language=current_language,
                            options=options,
                        )
                else:
                    # Invalid category response
                    category_config = _FEE_FLOW_QUESTIONS["category"].get(course)
                    ask = (
                        "I didn't understand that. Please choose one:\n\n"
                        + (category_config["question"] if category_config else "Please specify the admission category.")
                    )
                    options = category_config.get("clickable_options", []) if category_config else []
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(
                        reply=ask,
                        intent="fee_flow",
                        session_id=session_id,
                        language=current_language,
                        options=options,
                    )
            
            elif waiting_for == "fee_type":
                fee_type = _resolve_fee_type_response(user_msg)
                
                if fee_type:
                    # All info collected - construct refined query
                    pending["fee_type"] = fee_type
                    course = pending["course"]
                    category = pending["category"]
                    del _session_pending_fee_flow[session_id]
                    
                    refined_query = f"{fee_type} for {course} {category} at VNRVJIET"
                    logger.info(
                        f"Fee flow completed for session {session_id}: "
                        f"course={course}, category={category}, fee_type={fee_type}"
                    )
                    
                    # Retrieve and generate response
                    try:
                        rag_result = await retrieve_async(refined_query, top_k=8)
                        fee_context = rag_result.context_text
                        fee_sources = list({
                            f"{c.filename} ({c.source})" for c in rag_result.chunks
                        })
                    except Exception as e:
                        logger.error("RAG retrieval failed during fee flow: %s", e, exc_info=True)
                        fee_context = ""
                        fee_sources = []
                    
                    history = _session_history.get(session_id, [])
                    fee_reply = await _generate_llm_response_async(
                        refined_query,
                        fee_context,
                        "",
                        history=history,
                        session_id=session_id,
                        language=current_language,
                    )
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": fee_reply})
                    
                    return ChatResponse(
                        reply=fee_reply,
                        intent="informational",
                        session_id=session_id,
                        sources=fee_sources,
                        language=current_language,
                    )
                else:
                    # Invalid fee type response
                    ask = (
                        "I didn't understand that. Please choose one:\n\n"
                        + _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                    )
                    options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(
                        reply=ask,
                        intent="fee_flow",
                        session_id=session_id,
                        language=current_language,
                        options=options,
                    )
    
    # ── Detect NEW fee query (before document flow) ───────────
    # Start fee flow if query is about fees/scholarships
    if _detect_fee_query(user_msg):
        # Check if user already provided course and/or category
        detected_course = _extract_course_from_message(user_msg)
        detected_category = None
        if detected_course:
            detected_category = _extract_fee_category_from_message(user_msg, detected_course)
        
        # Check if fee type is clear from query
        detected_fee_type = _extract_fee_type_from_message(user_msg)
        
        # Smart flow: skip layers if info is already provided
        if detected_course and detected_category and detected_fee_type:
            # User provided everything - construct refined query and go to RAG
            refined_query = f"{detected_fee_type} for {detected_course} {detected_category} at VNRVJIET"
            logger.info(
                f"Fee query with all details: "
                f"course={detected_course}, category={detected_category}, fee_type={detected_fee_type}"
            )
            # Continue to normal flow - will be picked up by document flow override pattern
            user_msg = refined_query
        elif detected_course and detected_category:
            # Has course and category but no fee type
            if _is_fee_type_clear_from_query(user_msg):
                # Fee type is clear enough - continue to RAG
                fee_type_inferred = detected_fee_type or "fee structure"
                refined_query = f"{fee_type_inferred} for {detected_course} {detected_category} at VNRVJIET"
                logger.info(f"Fee query with inferred fee type: {refined_query}")
                user_msg = refined_query
            else:
                # Ask for fee type
                _session_pending_fee_flow[session_id] = {
                    "course": detected_course,
                    "category": detected_category,
                    "_waiting_for": "fee_type",
                }
                ask = _FEE_FLOW_QUESTIONS["fee_type"]["question"]
                options = _FEE_FLOW_QUESTIONS["fee_type"].get("clickable_options", [])
                logger.info(f"Fee flow started (course+category detected) for session {session_id}")
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(
                    reply=ask,
                    intent="fee_flow",
                    session_id=session_id,
                    language=current_language,
                    options=options,
                )
        elif detected_course:
            # Has course but no category - ask for category
            _session_pending_fee_flow[session_id] = {
                "course": detected_course,
                "_waiting_for": "category",
            }
            # Store detected fee type if present
            if detected_fee_type:
                _session_pending_fee_flow[session_id]["_original_fee_type"] = detected_fee_type
            
            category_config = _FEE_FLOW_QUESTIONS["category"].get(detected_course)
            ask = category_config["question"] if category_config else "Please specify the admission category."
            options = category_config.get("clickable_options", []) if category_config else []
            logger.info(f"Fee flow started (course detected) for session {session_id}: course={detected_course}")
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": ask})
            return ChatResponse(
                reply=ask,
                intent="fee_flow",
                session_id=session_id,
                language=current_language,
                options=options,
            )
        else:
            # No course detected - start fee flow from beginning
            _session_pending_fee_flow[session_id] = {
                "_waiting_for": "course",
            }
            # Store detected fee type if present
            if detected_fee_type:
                _session_pending_fee_flow[session_id]["_original_fee_type"] = detected_fee_type
            
            ask = _FEE_FLOW_QUESTIONS["course"]["question"]
            options = _FEE_FLOW_QUESTIONS["course"].get("clickable_options", [])
            logger.info(f"Fee flow started for session {session_id}")
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": ask})
            return ChatResponse(
                reply=ask,
                intent="fee_flow",
                session_id=session_id,
                language=current_language,
                options=options,
            )

    # ── Check if session is in document flow ──────────────────
    if session_id in _session_pending_document_flow:
        pending = _session_pending_document_flow[session_id]
        waiting_for = pending.get("_waiting_for")
        
        # Check for topic change
        if _is_topic_change(user_msg, current_flow="document_flow"):
            logger.info(f"Topic change detected during document flow for session {session_id}")
            del _session_pending_document_flow[session_id]
            # Fall through to normal processing below
        else:
            if waiting_for == "course":
                course = _resolve_course_response(user_msg)
                if course:
                    pending["course"] = course
                    pending["_waiting_for"] = "category"
                    
                    # Ask for category based on course
                    category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(course)
                    if category_config:
                        ask = category_config["question"]
                        options = category_config.get("clickable_options", [])
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": ask})
                        return ChatResponse(
                            reply=ask,
                            intent="document_flow",
                            session_id=session_id,
                            language=current_language,
                            options=options,
                        )
                else:
                    # Invalid course response
                    ask = (
                        "I didn't understand that. Please choose one:\n\n"
                        + _DOCUMENT_FLOW_QUESTIONS["course"]["question"]
                    )
                    options = _DOCUMENT_FLOW_QUESTIONS["course"].get("clickable_options", [])
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(
                        reply=ask,
                        intent="document_flow",
                        session_id=session_id,
                        language=current_language,
                        options=options,
                    )
            
            elif waiting_for == "category":
                course = pending.get("course")
                category = _resolve_category_response(user_msg, course)
                
                if category:
                    # Both course and category collected - construct refined query
                    del _session_pending_document_flow[session_id]
                    
                    refined_query = f"Required documents for {course} {category} admission"
                    logger.info(
                        f"Document flow completed for session {session_id}: "
                        f"course={course}, category={category}"
                    )
                    
                    # Retrieve context using refined query
                    try:
                        rag_result = await retrieve_async(refined_query, top_k=8)
                        doc_context = rag_result.context_text
                        doc_sources = list({
                            f"{c.filename} ({c.source})" for c in rag_result.chunks
                        })
                    except Exception as e:
                        logger.error("RAG retrieval failed during document flow: %s", e, exc_info=True)
                        doc_context = ""
                        doc_sources = []
                    
                    history = _session_history.get(session_id, [])
                    doc_reply = await _generate_llm_response_async(
                        refined_query,
                        doc_context,
                        "",
                        history=history,
                        session_id=session_id,
                        language=current_language,
                    )
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": doc_reply})
                    
                    return ChatResponse(
                        reply=doc_reply,
                        intent="informational",
                        session_id=session_id,
                        sources=doc_sources,
                        language=current_language,
                    )
                else:
                    # Invalid category response
                    category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(course)
                    ask = (
                        "I didn't understand that. Please choose one:\n\n"
                        + (category_config["question"] if category_config else "Please specify the admission category.")
                    )
                    options = category_config.get("clickable_options", []) if category_config else []
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(
                        reply=ask,
                        intent="document_flow",
                        session_id=session_id,
                        language=current_language,
                        options=options,
                    )

    # ── Check if session is awaiting a clarifying answer ──────
    if session_id in _session_pending_clarification:
        pending = _session_pending_clarification[session_id]
        original_query = pending["original_query"]
        category = pending["category"]

        # If user wants to change topic, clear state and fall through
        if _is_topic_change(user_msg, current_flow="clarification"):
            logger.info(f"Topic change detected during clarification for session {session_id}")
            del _session_pending_clarification[session_id]
            # Fall through to normal processing below
        else:
            refined_query = _resolve_clarification_response(user_msg, category)

            if refined_query:
                del _session_pending_clarification[session_id]
                logger.info(
                    f"Clarification resolved for session {session_id}: "
                    f"'{user_msg}' -> '{refined_query}'"
                )

                # Retrieve context using the refined (specific) query
                try:
                    rag_result = retrieve(refined_query, top_k=8)
                    clari_context = rag_result.context_text
                    clari_sources = list({
                        f"{c.filename} ({c.source})" for c in rag_result.chunks
                    })
                except Exception as e:
                    logger.error("RAG retrieval failed during clarification: %s", e, exc_info=True)
                    clari_context = ""
                    clari_sources = []

                history = _session_history.get(session_id, [])
                clari_reply = _generate_llm_response(
                    refined_query,
                    clari_context,
                    "",
                    history=history,
                    session_id=session_id,
                    language=current_language,
                )

                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": clari_reply})

                return ChatResponse(
                    reply=clari_reply,
                    intent="informational",
                    session_id=session_id,
                    sources=clari_sources,
                    language=current_language,
                )
            else:
                # Response didn't match – ask again with the same menu
                cat_config = _CLARIFICATION_CATEGORIES.get(category, {})
                re_ask = (
                    "I'm not sure I understood that option.\n\n"
                    + cat_config.get("question", "Could you please be more specific?")
                )
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": re_ask})
                return ChatResponse(
                    reply=re_ask,
                    intent="clarification",
                    session_id=session_id,
                    language=current_language,
                )

    # ── Check if session is in contact collection mode ────────
    if session_id in _session_contact_data:
        # Check if user wants to change topic/exit collection flow
        if _is_topic_change(user_msg, current_flow="contact_request"):
            del _session_contact_data[session_id]
            # Don't return - continue processing the new query below
        else:
            collected = _session_contact_data[session_id]
            waiting_for = collected.get("_waiting_for")
            
            # Extract and validate the user's input based on what we're waiting for
            if waiting_for == "name":
                # Accept any non-empty text as name
                name = user_msg.strip()
                if len(name) < 2:
                    ask = "Please provide your **full name** (at least 2 characters)."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
                collected["name"] = name
            
            elif waiting_for == "email":
                # Basic email validation
                email = user_msg.strip()
                if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                    ask = "That doesn't look like a valid email address. Please enter your **email** (e.g., student@example.com)."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
                collected["email"] = email
            
            elif waiting_for == "phone":
                # Extract phone number (10 digits)
                phone_match = re.search(r"\b(\d{10})\b", user_msg)
                if not phone_match:
                    ask = "Please provide a valid **10-digit phone number** (e.g., 9876543210)."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
                collected["phone"] = phone_match.group(1)
            
            elif waiting_for == "programme":
                # Parse programme choice
                msg_lower = user_msg.lower().strip()
                programme = None
                if '1' in msg_lower or 'b.tech' in msg_lower or 'btech' in msg_lower or 'bachelor' in msg_lower:
                    programme = "B.Tech"
                elif '2' in msg_lower or 'm.tech' in msg_lower or 'mtech' in msg_lower or 'master' in msg_lower:
                    programme = "M.Tech"
                elif '3' in msg_lower or 'mca' in msg_lower:
                    programme = "MCA"
                
                if not programme:
                    ask = "Please choose a programme:\n\n1️⃣ B.Tech\n2️⃣ M.Tech\n3️⃣ MCA\n\nReply with the number (1, 2, or 3)."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
                collected["programme"] = programme
            
            elif waiting_for == "query_type":
                # Parse query type
                msg_lower = user_msg.lower().strip()
                query_type = None
                if '1' in msg_lower or 'fraud' in msg_lower or 'agent' in msg_lower or 'scam' in msg_lower:
                    query_type = "fraud_report"
                elif '2' in msg_lower or 'general' in msg_lower or 'inquiry' in msg_lower or 'admission' in msg_lower:
                    query_type = "general_inquiry"
                elif '3' in msg_lower or 'not satisfied' in msg_lower or 'dissatisfied' in msg_lower or 'chatbot' in msg_lower:
                    query_type = "dissatisfied"
                elif '4' in msg_lower or 'other' in msg_lower:
                    query_type = "other"
                
                if not query_type:
                    ask = "Please choose an option:\n\n1️⃣ Report fraud\n2️⃣ General inquiry\n3️⃣ Not satisfied with chatbot\n4️⃣ Other\n\nReply with the number (1-4)."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
                collected["query_type"] = query_type
            
            elif waiting_for == "message":
                # Optional message - accept anything
                if len(user_msg.strip()) > 0:
                    collected["message"] = user_msg.strip()
                else:
                    collected["message"] = None
            
            # Check what's still missing and ask the next question
            for field, question_template in _CONTACT_QUESTIONS:
                if field not in collected or collected[field] is None:
                    collected["_waiting_for"] = field
                    # Format question with collected data if needed
                    if "{name}" in question_template:
                        ask = question_template.format(name=collected.get("name", "there"))
                    else:
                        ask = question_template
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
            
            # All required fields collected! Ask for optional message
            if "message" not in collected:
                collected["_waiting_for"] = "message"
                ask = "Almost done! Would you like to add any **additional message** or details?\n\n(Or reply **skip** to submit now)"
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)
            
            # Handle skip for message
            if collected.get("_waiting_for") == "message" and user_msg.lower().strip() == "skip":
                collected["message"] = None
            
            # Everything collected - save to Google Sheets
            try:
                from app.logic.google_sheets_service import save_contact_to_sheets
                
                success, ref_id = await save_contact_to_sheets(
                    name=collected["name"],
                    email=collected["email"],
                    phone=collected["phone"],
                    programme=collected["programme"],
                    query_type=collected["query_type"],
                    message=collected.get("message")
                )
                
                if success:
                    # Show privacy note for phone number
                    phone_note = ""
                    if collected["query_type"] not in ["fraud_report", "general_inquiry"]:
                        phone_note = "\n\n🔒 **Note:** Your phone number is kept private and will not be shared with the admission team for this request type."
                    
                    reply = (
                        f"✅ **Request Submitted Successfully**\n\n"
                        f"Thank you, **{collected['name']}**! Our admission team has received your request.\n\n"
                        f"**Contact Details:**\n"
                        f"📧 {collected['email']}\n"
                        f"📞 {collected['phone']}\n"
                        f"🎓 Programme: {collected['programme']}\n\n"
                        f"**What's next:**\n"
                        f"Our team will reach out to you within **24 hours**.\n\n"
                        f"**Reference ID:** `{ref_id}`{phone_note}"
                    )
                else:
                    reply = (
                        "⚠️ There was an issue submitting your request. "
                        "Please contact our admission team directly:\n\n"
                        "📧 admissionsenquiry@vnrvjiet.in\n"
                        "📞 +91-40-2304 2758"
                    )
                
                # Clean up session state
                del _session_contact_data[session_id]
                
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": reply})
                return ChatResponse(reply=reply, intent="contact_request", session_id=session_id, language=current_language)
            
            except Exception as e:
                logger.error(f"Failed to save contact request: {e}", exc_info=True)
                reply = (
                    "⚠️ There was an error processing your request. "
                    "Please contact our admission team directly:\n\n"
                    "📧 admissionsenquiry@vnrvjiet.in\n"
                    "📞 +91-40-2304 2758"
                )
                del _session_contact_data[session_id]
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": reply})
                return ChatResponse(reply=reply, intent="contact_request", session_id=session_id, language=current_language)

    # ── Check if session is in cutoff collection mode ─────────
    if session_id in _session_cutoff_data:
        # Check if user wants to change topic/exit collection flow
        collected = _session_cutoff_data[session_id]
        flow = collected.get("_flow", "cutoff")
        
        if _is_topic_change(user_msg, current_flow=flow):
            del _session_cutoff_data[session_id]
            _session_pending_intent.pop(session_id, None)
            # Don't return - continue processing the new query below
        else:
            # We're collecting cutoff details step by step
            waiting_for = collected.get("_waiting_for")
            questions = _ELIGIBILITY_QUESTIONS if flow == "eligibility" else _CUTOFF_QUESTIONS

            # Handle reuse confirmation
            if waiting_for == "_confirm_reuse":
                response = user_msg.strip().lower()
                if response in ("yes", "y", "yeah", "yep", "sure", "ok", "okay"):
                    # User confirmed reuse - copy data
                    reuse_data = collected.get("_reuse_data", {})
                    collected["branch"] = reuse_data.get("branch")
                    collected["category"] = reuse_data.get("category")
                    collected["gender"] = reuse_data.get("gender")
                    
                    # Check if rank was already extracted from previous message
                    extracted_rank = collected.get("_extracted_rank")
                    if extracted_rank:
                        # We have everything - complete the eligibility check
                        del _session_cutoff_data[session_id]
                        _session_pending_intent.pop(session_id, None)
                        
                        branches_list = collected["branch"]
                        if isinstance(branches_list, str):
                            branches_list = [branches_list]
                        
                        show_trend = collected.get("_show_trend", False)
                        reply = _build_multi_branch_reply(
                            branches_list, 
                            collected["category"], 
                            collected["gender"], 
                            extracted_rank,
                            show_trend=show_trend,
                            year=collected.get("year")
                        )
                        
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": reply})
                        return ChatResponse(
                            reply=reply, intent="eligibility", session_id=session_id,
                            sources=["VNRVJIET Cutoff Database"],
                            language=current_language,
                        )
                    else:
                        # Still need to ask for rank
                        collected["_waiting_for"] = "rank"
                        ask = "Great! What is your **EAPCET rank**?"
                        _session_history[session_id].append({"role": "user", "content": user_msg})
                        _session_history[session_id].append({"role": "assistant", "content": ask})
                        return ChatResponse(reply=ask, intent="cutoff", session_id=session_id, language=current_language)
                else:
                    # User wants different details - start fresh
                    show_trend_flag = collected.get("_show_trend", False)  # Preserve trend flag
                    collected.clear()
                    collected["_flow"] = "eligibility"
                    if show_trend_flag:
                        collected["_show_trend"] = True
                    collected["_waiting_for"] = "branch"
                    
                    avail_branches = list_branches()
                    branch_list = ", ".join(avail_branches)
                    ask = f"Sure! Let me help you check your eligibility.\n\nWhich **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branch_list}"
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="cutoff", session_id=session_id, language=current_language)
            
            # A3 – Dynamic completeness: after EVERY user reply, re-scan for ALL
            # fields the user may have volunteered. This lets power users who
            # provide extra info (e.g. "CSE OC" when asked for branch) skip steps.
            if waiting_for not in ("_confirm_reuse",):
                if "branch" not in collected:
                    _dyn_b = extract_branches(user_msg)
                    if _dyn_b:
                        collected["branch"] = _dyn_b
                if "category" not in collected:
                    _dyn_c = extract_category(user_msg)
                    if _dyn_c:
                        collected["category"] = _dyn_c
                if "gender" not in collected:
                    _dyn_g = extract_gender(user_msg)
                    if _dyn_g:
                        collected["gender"] = _dyn_g
                if "year" not in collected:
                    _dyn_y = extract_year(user_msg)
                    if _dyn_y:
                        collected["year"] = _dyn_y
                    elif re.search(r"\b(latest|recent|current|now|last)\b", user_msg, re.I):
                        collected["year"] = None  # use latest available
                if flow == "eligibility" and "rank" not in collected:
                    _dyn_r = extract_rank(user_msg)
                    if _dyn_r:
                        collected["rank"] = _dyn_r

            # Try to extract what we asked for from the user's reply
            if waiting_for == "branch":
                vals = extract_branches(user_msg)
                if vals:
                    # Keep "ALL" as-is so _build_multi_branch_reply can use flexible query
                    collected["branch"] = vals
                else:
                    # Try raw text as a single branch name
                    collected["branch"] = [user_msg.strip().upper()]

            elif waiting_for == "category":
                val = extract_category(user_msg)
                if not val:
                    # Check if user said "all" in any form
                    msg_lower = user_msg.strip().lower()
                    if any(word in msg_lower for word in ["all", "every", "each", "any"]):
                        val = "ALL"
                    else:
                        val = user_msg.strip().upper()
                collected["category"] = val

            elif waiting_for == "gender":
                val = extract_gender(user_msg)
                if not val:
                    t = user_msg.strip().lower()
                    # Check for "all" or "both" responses
                    if any(word in t for word in ["all", "both", "any", "either"]):
                        val = "ALL"
                    elif t in ("boy", "boys", "male", "m"):
                        val = "Boys"
                    elif t in ("girl", "girls", "female", "f"):
                        val = "Girls"
                    else:
                        val = user_msg.strip()
                collected["gender"] = val

            elif waiting_for == "year":
                # Accept a specific year or "latest"/"recent" to mean no filter (use latest available)
                val = extract_year(user_msg)
                t = user_msg.strip().lower()
                if val:
                    collected["year"] = val
                elif any(w in t for w in ["latest", "recent", "current", "new", "now", "last", "2025"]):
                    collected["year"] = None  # None = use latest available in DB
                else:
                    # Unrecognisable input — default to latest and move on
                    collected["year"] = None

            elif waiting_for == "rank":
                # Check if user says they don't have a rank
                no_rank_phrases = ["no rank", "don't have", "dont have", "no", "don\x27t know", "not sure", "skip"]
                if any(p in user_msg.lower() for p in no_rank_phrases):
                    # User doesn't have rank → just show cutoff ranks instead
                    branches_list = collected.get("branch", [])
                    if isinstance(branches_list, str):
                        branches_list = [branches_list]
                    category = collected.get("category") or "OC"
                    gender = collected.get("gender") or "Boys"
                    del _session_cutoff_data[session_id]
                    _session_pending_intent.pop(session_id, None)

                    reply = "No worries! Here are the cutoff ranks for reference:\n\n"
                    show_trend = collected.get("_show_trend", False)
                    reply += _build_multi_branch_reply(branches_list, category, gender, rank=None, show_trend=show_trend, year=collected.get("year"))
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": reply})
                    return ChatResponse(
                        reply=reply, intent="cutoff", session_id=session_id,
                        sources=["VNRVJIET Cutoff Database"],
                        language=current_language,
                    )

                val = extract_rank(user_msg)
                if val:
                    collected["rank"] = val
                else:
                    num_match = re.search(r"\b(\d+)\b", user_msg)
                    if num_match and int(num_match.group(1)) > 200000:
                        ask = "That rank seems too high. EAPCET ranks typically range from **1 to 2,00,000**. Please re-enter your correct rank."
                    else:
                        ask = "I couldn't understand that. Please enter your **EAPCET rank** as a number (e.g., 5000).\n\nOr reply **no** if you just want to see cutoff ranks."
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="cutoff", session_id=session_id, language=current_language)

            # Check what's still missing and ask the next question
            # Note: year can be stored as None (meaning "latest"), so we only
            # gate on key presence, not value truthiness.
            for field, question_template in questions:
                if field not in collected:
                    collected["_waiting_for"] = field
                    if field == "branch":
                        branches = list_branches()
                        branch_list = ", ".join(branches)
                        ask = question_template.format(branches=branch_list)
                    else:
                        ask = question_template
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="cutoff", session_id=session_id, language=current_language)

            # All fields collected!
            branches_list = collected["branch"]
            if isinstance(branches_list, str):
                branches_list = [branches_list]
            category = collected["category"]
            gender = collected["gender"]
            
            # Save this cutoff query for potential reuse in eligibility check
            if not collected.get("rank"):
                _session_last_cutoff[session_id] = {
                    "branch": branches_list,
                    "category": category,
                    "gender": gender,
                    "year": collected.get("year"),
                }
            
            del _session_cutoff_data[session_id]
            _session_pending_intent.pop(session_id, None)

            has_rank = "rank" in collected
            rank_val = collected.get("rank")
            show_trend = collected.get("_show_trend", False)

            # Query each branch and combine results
            reply = _build_multi_branch_reply(branches_list, category, gender, rank_val if has_rank else None, show_trend=show_trend, year=collected.get("year"))

            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})

            return ChatResponse(
                reply=reply, intent="cutoff", session_id=session_id,
                sources=["VNRVJIET Cutoff Database"],
                language=current_language,
            )

    # ── Check for contact request keywords ───────────────────
    contact_keywords = [
        "talk to admission", "speak with admission", "speak to someone", "talk to someone",
        "contact admission", "call me", "callback", "call back", "reach out",
        "not satisfied", "dissatisfied", "want to speak", "want to talk",
        "admission department", "admission team", "admission office"
    ]
    
    msg_lower = user_msg.lower()
    is_contact_request = any(keyword in msg_lower for keyword in contact_keywords)
    
    if is_contact_request and session_id not in _session_contact_data:
        # Clear all other pipelines before starting contact pipeline
        _clear_other_pipelines(session_id, keep="contact")
        # Start contact collection flow
        _session_contact_data[session_id] = {"_waiting_for": "name"}
        ask = _CONTACT_QUESTIONS[0][1]  # First question (name)
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": ask})
        return ChatResponse(reply=ask, intent="contact_request", session_id=session_id, language=current_language)

    # ═══════════════════════════════════════════════════════════
    # PRIORITY: Check for NEW Required Documents query
    # Detect and start document flow BEFORE classification/RAG
    # ═══════════════════════════════════════════════════════════
    if _detect_document_query(user_msg):
        # Check if user already provided both course and category
        detected_course = _extract_course_from_message(user_msg)
        detected_category = None
        if detected_course:
            detected_category = _extract_category_from_message(user_msg, detected_course)
        
        if detected_course and detected_category:
            # User provided both - skip flow, construct query and retrieve directly
            refined_query = f"Required documents for {detected_course} {detected_category} admission"
            logger.info(
                f"Document query with both course and category: "
                f"course={detected_course}, category={detected_category}"
            )
            # Retrieve context using refined query
            try:
                rag_result = await retrieve_async(refined_query, top_k=8)
                doc_context = rag_result.context_text
                doc_sources = list({
                    f"{c.filename} ({c.source})" for c in rag_result.chunks
                })
            except Exception as e:
                logger.error("RAG retrieval failed during document flow: %s", e, exc_info=True)
                doc_context = ""
                doc_sources = []
            
            history = _session_history.get(session_id, [])
            doc_reply = await _generate_llm_response_async(
                refined_query,
                doc_context,
                "",
                history=history,
                session_id=session_id,
                language=current_language,
            )
            
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": doc_reply})
            
            return ChatResponse(
                reply=doc_reply,
                intent="informational",
                session_id=session_id,
                sources=doc_sources,
                language=current_language,
            )
        elif not detected_course:
            # Start document flow - need to collect course first
            _session_pending_document_flow[session_id] = {
                "_waiting_for": "course",
            }
            ask = _DOCUMENT_FLOW_QUESTIONS["course"]["question"]
            options = _DOCUMENT_FLOW_QUESTIONS["course"].get("clickable_options", [])
            logger.info(f"Document flow started for session {session_id}")
            
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": ask})
            
            return ChatResponse(
                reply=ask,
                intent="document_flow",
                session_id=session_id,
                language=current_language,
                options=options,
            )
        else:
            # Has course but no category - start at category question
            _session_pending_document_flow[session_id] = {
                "course": detected_course,
                "_waiting_for": "category",
            }
            category_config = _DOCUMENT_FLOW_QUESTIONS["category"].get(detected_course)
            ask = category_config["question"] if category_config else "Please specify the admission category."
            options = category_config.get("clickable_options", []) if category_config else []
            logger.info(f"Document flow started (course detected) for session {session_id}: course={detected_course}")
            
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": ask})
            
            return ChatResponse(
                reply=ask,
                intent="document_flow",
                session_id=session_id,
                language=current_language,
                options=options,
            )

    # Classify
    classification = classify(user_msg)
    intent = classification.intent

    # If we previously asked this session for cutoff details,
    # and the classifier didn't detect cutoff intent on its own,
    # force it to CUTOFF so the follow-up is handled correctly.
    pending = _session_pending_intent.get(session_id)
    if pending == "awaiting_cutoff_details" and intent == IntentType.INFORMATIONAL:
        intent = IntentType.CUTOFF

    # ── Greeting ──────────────────────────────────────────────
    if intent == IntentType.GREETING:
        greeting = get_greeting_message(current_language)
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": greeting})
        return ChatResponse(
            reply=greeting,
            intent=intent.value,
            session_id=session_id,
            language=current_language,
        )

    # ── Out of scope ──────────────────────────────────────
    if intent == IntentType.OUT_OF_SCOPE:
        out_of_scope_msg = get_out_of_scope_message(current_language)
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": out_of_scope_msg})
        return ChatResponse(
            reply=out_of_scope_msg,
            intent=intent.value,
            session_id=session_id,
            language=current_language,
        )

    # ── Check for follow-up trend request ─────────────────────
    # If user asks for trend after receiving normal cutoff, reuse previous query
    if _detect_trend_request(user_msg) and session_id in _session_last_cutoff:
        last = _session_last_cutoff[session_id]
        branches_list = last["branch"] if isinstance(last["branch"], list) else [last["branch"]]
        
        reply = _build_multi_branch_reply(
            branches_list,
            last["category"],
            last["gender"],
            rank=None,
            show_trend=True,
            year=last.get("year")
        )
        
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": reply})
        return ChatResponse(
            reply=reply,
            intent="cutoff",
            session_id=session_id,
            sources=["VNRVJIET Cutoff Database"],
            language=current_language,
        )

    # ── Extract structured entities ───────────────────────────
    rank = extract_rank(user_msg)
    branch = extract_branch(user_msg)
    category = extract_category(user_msg)
    gender = extract_gender(user_msg)
    # Extract year for ALL query types (including cutoff/eligibility)
    # Users often ask "What was CSE cutoff in 2023?"
    year = extract_year(user_msg)

    cutoff_info = ""
    sources: list[str] = []
    rag_context = ""

    # ── KNOWLEDGE-FIRST: Search full knowledge database before ANY pipeline ───
    # IMPORTANT: Skip RAG for CUTOFF/ELIGIBILITY at this stage — the cutoff engine
    # queries Firestore (the authoritative structured DB) and must NOT be polluted
    # by RAG text documents that may contain stale/sample rank values.
    # RAG is only applied for informational, mixed, and general queries.
    _is_cutoff_intent = False  # resolved below after early-pipeline sections
    try:
        # We do NOT yet know the intent here; we use a lightweight keyword pre-check
        # to avoid retrieving RAG for clear cutoff queries.
        _pre_cutoff_indicators = [
            "cutoff", "cut off", "cut-off", "closing rank", "last rank",
            "eapcet", "tseamcet", "ts eamcet", "opening rank", "counselling",
            "eligible", "eligibility", "can i get", "will i get", "my rank",
        ]
        _kf_skip = any(kw in user_msg.lower() for kw in _pre_cutoff_indicators)
        if not _kf_skip:
            _kf_result = await retrieve_async(user_msg, top_k=8)
            rag_context = _kf_result.context_text
            for _kf_chunk in _kf_result.chunks:
                sources.append(f"{_kf_chunk.filename} ({_kf_chunk.source})")
            logger.info(
                "Knowledge-First RAG: retrieved %d chunks, context length: %d chars",
                len(_kf_result.chunks),
                len(rag_context),
            )
        else:
            logger.info("Knowledge-First RAG: skipped (cutoff/eligibility query detected)")
    except Exception as _kf_exc:
        logger.error("Knowledge-First RAG retrieval failed: %s", _kf_exc)
        rag_context = ""

    # ── Gender-change follow-up (early catch regardless of intent) ────────────
    # e.g. user says "for girl" / "for boys" after a cutoff query was shown.
    # Handle here so even if the intent classifier misses CUTOFF, we still respond correctly.
    if (
        gender and not branch and not category and not rank
        and session_id in _session_last_cutoff
        and intent not in (IntentType.ELIGIBILITY,)
    ):
        last = _session_last_cutoff[session_id]
        last_branches = last["branch"] if isinstance(last["branch"], list) else [last["branch"]]
        last_category = last["category"]
        last_year = year or last.get("year")
        _session_last_cutoff[session_id] = {
            "branch": last_branches,
            "category": last_category,
            "gender": gender,
            "year": last_year,
        }
        reply_text = _build_multi_branch_reply(
            last_branches, last_category, gender,
            rank=None, show_trend=_detect_trend_request(user_msg), year=last_year
        )
        sources.append("VNRVJIET Cutoff Database")
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": reply_text})
        return ChatResponse(
            reply=reply_text, intent="cutoff",
            session_id=session_id,
            sources=["VNRVJIET Cutoff Database"],
            language=current_language,
        )

    # ── Cutoff / Eligibility path ─────────────────────────────
    if intent in (IntentType.CUTOFF, IntentType.ELIGIBILITY, IntentType.MIXED):
        # Determine flow type
        is_eligibility = (intent == IntentType.ELIGIBILITY)
        flow = "eligibility" if is_eligibility else "cutoff"
        questions = _ELIGIBILITY_QUESTIONS if is_eligibility else _CUTOFF_QUESTIONS

        # Pre-fill whatever we already extracted from this message
        collected = {"_flow": flow}
        
        # Detect if user is asking for trend analysis
        show_trend = _detect_trend_request(user_msg)
        if show_trend:
            collected["_show_trend"] = True
        
        # Extract multiple branches
        branches_extracted = extract_branches(user_msg)
        # A1: Only return ALL branches when the user EXPLICITLY requests it.
        # Never auto-show all branches for a generic/vague cutoff query.
        _all_branches_explicit = any(
            phrase in user_msg.lower()
            for phrase in [
                "all branches", "all branch", "show all", "branch-wise for all",
                "every branch", "all departments", "all btech", "all b.tech",
            ]
        )
        if branches_extracted and "ALL" in branches_extracted and not _all_branches_explicit:
            # User didn't explicitly ask for all branches → treat as no branch provided
            branches_extracted = []
        if branches_extracted:
            # Keep "ALL" as-is so _build_multi_branch_reply can use flexible query
            collected["branch"] = branches_extracted
        if category:
            collected["category"] = category
        if gender:
            collected["gender"] = gender
        if year:
            collected["year"] = year
        elif re.search(r"\b(latest|recent|current|now|last)\b", user_msg, re.I):
            collected["year"] = None  # use latest available
        if rank and is_eligibility:
            collected["rank"] = rank

        # ── Context inheritance for branch-change follow-ups ─────────────────
        # When user provides only new branches (e.g. "what about csm and cso")
        # but omits category/gender/year, inherit those from the previous cutoff
        # query stored in _session_last_cutoff.  This prevents the bot from
        # asking all questions again when the user is simply switching branches.
        if (
            "branch" in collected
            and session_id in _session_last_cutoff
            and "category" not in collected
        ):
            _last = _session_last_cutoff[session_id]
            if _last.get("category"):
                collected["category"] = _last["category"]
                category = _last["category"]
            if "gender" not in collected and _last.get("gender"):
                collected["gender"] = _last["gender"]
                gender = _last["gender"]
            if "year" not in collected and _last.get("year") is not None:
                collected["year"] = _last["year"]
                year = _last["year"]

        # Check if all required fields are already provided
        required = [f for f, _ in questions]
        all_present = all(f in collected for f in required)

        if all_present:
            b_list = collected["branch"]
            if isinstance(b_list, str):
                b_list = [b_list]
            show_trend = collected.get("_show_trend", False)
            _cutoff_year = collected.get("year")
            cutoff_reply = _build_multi_branch_reply(
                b_list, category, gender,
                rank if is_eligibility else None,
                show_trend=show_trend,
                year=_cutoff_year,
            )
            # Save for gender-change follow-ups
            if not is_eligibility and not rank:
                _session_last_cutoff[session_id] = {
                    "branch": b_list,
                    "category": category,
                    "gender": gender,
                    "year": _cutoff_year,
                }
            # ─ Return DIRECTLY from the structured Firestore data. ─────────
            # NEVER pass cutoff data through the LLM — it can introduce wrong
            # ranks by blending RAG context with structured data.
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": cutoff_reply})
            return ChatResponse(
                reply=cutoff_reply,
                intent=intent.value,
                session_id=session_id,
                sources=["VNRVJIET Cutoff Database"],
                language=current_language,
            )
        else:
            # Check if user is changing gender for the same branch/category (cutoff query)
            # e.g., user said "for girl" after seeing boys cutoff → re-query with new gender
            if not is_eligibility and session_id in _session_last_cutoff and gender and "branch" not in collected:
                last = _session_last_cutoff[session_id]
                last_branches = last["branch"] if isinstance(last["branch"], list) else [last["branch"]]
                last_category = last["category"]
                last_year = collected.get("year") or last.get("year")

                # Update last cutoff record with new gender
                _session_last_cutoff[session_id] = {
                    "branch": last_branches,
                    "category": last_category,
                    "gender": gender,
                    "year": last_year,
                }

                reply_text = _build_multi_branch_reply(
                    last_branches, last_category, gender,
                    rank=None, show_trend=show_trend, year=last_year
                )
                sources.append("VNRVJIET Cutoff Database")
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": reply_text})
                return ChatResponse(
                    reply=reply_text, intent=intent.value,
                    session_id=session_id,
                    sources=["VNRVJIET Cutoff Database"],
                    language=current_language,
                )

            # Check if we can reuse recent cutoff data for eligibility query
            if is_eligibility and session_id in _session_last_cutoff and "branch" not in collected:
                last = _session_last_cutoff[session_id]
                branch_str = ", ".join(last["branch"]) if isinstance(last["branch"], list) else last["branch"]
                
                # Check if rank was already provided in this message
                has_rank_now = "rank" in collected
                
                # Ask user if they want to reuse previous details
                collected["_waiting_for"] = "_confirm_reuse"
                collected["_reuse_data"] = last
                if has_rank_now:
                    collected["_extracted_rank"] = collected["rank"]
                _session_cutoff_data[session_id] = collected
                
                ask = (
                    f"I see you just asked about **{branch_str}** / **{last['category']}** category / **{last['gender']}**. "
                    f"Would you like me to check eligibility for the same?\n\n"
                    f"Reply **YES** to use these details, or provide new branch/category/gender."
                )
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent=intent.value, session_id=session_id, language=current_language)
            
            # Start step-by-step collection
            for field, question_template in questions:
                if field not in collected:
                    collected["_waiting_for"] = field
                    # Clear other pipelines before activating cutoff pipeline
                    _clear_other_pipelines(session_id, keep="cutoff")
                    _session_cutoff_data[session_id] = collected

                    intro = "Sure! Let me help you check your eligibility." if is_eligibility else "Sure! Let me show you the cutoff ranks."
                    if field == "branch":
                        avail_branches = list_branches()
                        branch_list = ", ".join(avail_branches)
                        ask = f"{intro}\n\n{question_template.format(branches=branch_list)}"
                    else:
                        ask = question_template

                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent=intent.value, session_id=session_id, language=current_language)

    # ── Clarification gate (informational only, no cutoff data yet) ──
    # For broad/vague informational topics, ask a narrowing question first.
    if intent == IntentType.INFORMATIONAL and not cutoff_info:
        clari_category = _detect_category_needing_clarification(user_msg)
        if clari_category:
            clari_config = _CLARIFICATION_CATEGORIES[clari_category]
            clari_question = clari_config["question"]

            _session_pending_clarification[session_id] = {
                "original_query": user_msg,
                "category": clari_category,
            }
            logger.info(
                f"Clarification triggered for session {session_id}: "
                f"category='{clari_category}', query='{user_msg}'"
            )

            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": clari_question})

            return ChatResponse(
                reply=clari_question,
                intent="clarification",
                session_id=session_id,
                language=current_language,
            )

    # ── Cache check (informational only) ─────────────────────
    # For specific queries that don't need clarification, check cache first.
    if intent == IntentType.INFORMATIONAL and not cutoff_info:
        cached = _get_cached_response(user_msg, intent.value, current_language)
        if cached:
            reply, cached_sources = cached
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(
                reply=reply,
                intent=intent.value,
                session_id=session_id,
                sources=cached_sources,
                language=current_language,
            )

    # ── RAG retrieval ───────────────────────────────────────────────
    # Only for informational / general queries. CUTOFF and ELIGIBILITY intents
    # always return via Firestore before reaching this point. Running RAG for
    # cutoff queries would put wrong rank values into the LLM context.
    if not rag_context and intent not in (IntentType.CUTOFF, IntentType.ELIGIBILITY):
        try:
            top_k = 8 if intent == IntentType.MIXED else 6
            rag_result = await retrieve_async(user_msg, top_k=top_k)
            rag_context = rag_result.context_text
            for chunk in rag_result.chunks:
                sources.append(f"{chunk.filename} ({chunk.source})")
            logger.info(
                "RAG retrieved %d chunks (intent=%s), context length: %d chars",
                len(rag_result.chunks),
                intent.value,
                len(rag_context),
            )
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e, exc_info=True)
            rag_context = ""

    # ── Generate final answer ─────────────────────────────────
    # Always call LLM first - it has knowledge in system prompt even without RAG context
    history = _session_history.get(session_id, [])
    # Use async LLM generation for better performance
    reply = await _generate_llm_response_async(
        user_msg, 
        rag_context, 
        cutoff_info, 
        history=history,
        session_id=session_id,
        language=current_language
    )
    
    # ── Web search fallback (only if LLM explicitly doesn't know) ──
    # Check if LLM response indicates lack of information (multilingual support)
    lacks_info_phrases = [
        # English
        "don't have that specific information",
        "don't have that information",
        "information is unavailable",
        "I don't have",
        "not available in my database",
        # Hindi
        "मुझे वह विशिष्ट जानकारी नहीं है",
        "मुझे उस जानकारी नहीं है",
        "जानकारी उपलब्ध नहीं है",
        "मेरे पास नहीं है",
        # Telugu
        "నాకు ఆ సమాచారం లేదు",
        "సమాచారం అందుబాటులో లేదు",
        # Tamil
        "என்னிடம் தகவல் இல்லை",
        # Common patterns
        "नहीं है", "లేదు", "இல்லை",
    ]
    
    if (
        settings.WEB_SEARCH_ENABLED 
        and intent == IntentType.INFORMATIONAL 
        and not rag_context 
        and not cutoff_info
        and session_id not in _session_pending_websearch
        and any(phrase.lower() in reply.lower() for phrase in lacks_info_phrases)
    ):
        # LLM couldn't answer - ask permission to search website
        _session_pending_websearch[session_id] = user_msg
        
        reply = (
            f"{reply}\n\n"
            "Would you like me to search our official **VNRVJIET website** for this information? "
            "(Reply **yes** or **no**)"
        )
        
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": reply})
        
        return ChatResponse(
            reply=reply,
            intent="web_search_permission",
            session_id=session_id,
            language=current_language,
        )

    # Clear pending intent since we got a full answer
    _session_pending_intent.pop(session_id, None)

    # Save to conversation history
    _session_history[session_id].append({"role": "user", "content": user_msg})
    _session_history[session_id].append({"role": "assistant", "content": reply})

    # Cache informational responses for future reuse (skip cutoff queries as they're user-specific)
    if intent == IntentType.INFORMATIONAL and not cutoff_info:
        _cache_response(user_msg, intent.value, reply, sources, current_language)

    # Trim history to prevent unbounded growth
    if len(_session_history[session_id]) > MAX_HISTORY * 2:
        _session_history[session_id] = _session_history[session_id][-(MAX_HISTORY * 2):]

    return ChatResponse(
        reply=reply,
        intent=intent.value,
        session_id=session_id,
        sources=list(set(sources)),
        language=current_language,
    )


# ── Health & metadata ─────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "college": settings.COLLEGE_SHORT_NAME}


@router.get("/branches")
async def branches():
    return {"branches": list_branches()}


@router.post("/clear-session")
async def clear_session(req: ChatRequest):
    """
    Clear all session data for a fresh start.
    
    This endpoint removes:
    - Conversation history
    - Pending intents
    - Cutoff collection state
    - Contact request state
    - Last cutoff query cache
    - Document flow state
    - Fee flow state
    - Language preference
    """
    session_id = req.session_id
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    # Clear all session-related data
    cleared = []
    
    if session_id in _session_history:
        del _session_history[session_id]
        cleared.append("history")
    
    if session_id in _session_pending_intent:
        del _session_pending_intent[session_id]
        cleared.append("pending_intent")
    
    if session_id in _session_cutoff_data:
        del _session_cutoff_data[session_id]
        cleared.append("cutoff_data")
    
    if session_id in _session_contact_data:
        del _session_contact_data[session_id]
        cleared.append("contact_data")
    
    if session_id in _session_last_cutoff:
        del _session_last_cutoff[session_id]
        cleared.append("last_cutoff")
    
    if session_id in _session_pending_websearch:
        del _session_pending_websearch[session_id]
        cleared.append("pending_websearch")
    
    if session_id in _session_pending_clarification:
        del _session_pending_clarification[session_id]
        cleared.append("pending_clarification")
    
    if session_id in _session_pending_document_flow:
        del _session_pending_document_flow[session_id]
        cleared.append("pending_document_flow")
    
    if session_id in _session_pending_fee_flow:
        del _session_pending_fee_flow[session_id]
        cleared.append("pending_fee_flow")
    
    if session_id in _session_active_pipeline:
        del _session_active_pipeline[session_id]
        cleared.append("active_pipeline")

    if session_id in _session_language:
        del _session_language[session_id]
        cleared.append("language")
    
    return {
        "status": "ok",
        "session_id": session_id,
        "cleared": cleared
    }
