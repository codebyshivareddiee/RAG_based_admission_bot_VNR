"""
Chat API – the core endpoint that orchestrates:
  1. Input sanitisation
  2. Intent classification
  3. Cutoff engine (structured queries)
  4. RAG retrieval (informational queries)
  5. LLM answer generation with guardrails
"""

from __future__ import annotations

import logging
import re
import sys
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)
logger.info("chat.py: starting imports...")

try:
    from fastapi import APIRouter, HTTPException, Request
    from pydantic import BaseModel, Field
    from openai import OpenAI
    logger.info("chat.py: FastAPI/Pydantic/OpenAI imports OK")
except Exception as e:
    logger.error(f"chat.py: FAILED FastAPI/Pydantic/OpenAI imports: {e}")
    traceback.print_exc()
    raise

try:
    from app.config import get_settings
    logger.info("chat.py: app.config OK")
except Exception as e:
    logger.error(f"chat.py: FAILED app.config: {e}")
    traceback.print_exc()
    raise

try:
    from app.classifier.intent_classifier import IntentType, classify
    logger.info("chat.py: intent_classifier OK")
except Exception as e:
    logger.error(f"chat.py: FAILED intent_classifier: {e}")
    traceback.print_exc()
    raise

try:
    from app.logic.cutoff_engine import (
        check_eligibility,
        get_cutoff,
        get_all_cutoffs_for_branch,
        list_branches,
    )
    logger.info("chat.py: cutoff_engine OK")
except Exception as e:
    logger.error(f"chat.py: FAILED cutoff_engine: {e}")
    traceback.print_exc()
    raise

try:
    from app.rag.retriever import retrieve
    logger.info("chat.py: retriever OK")
except Exception as e:
    logger.error(f"chat.py: FAILED retriever: {e}")
    traceback.print_exc()
    raise

try:
    from app.utils.validators import (
        extract_branch,
        extract_branches,
        extract_category,
        extract_gender,
        extract_rank,
        extract_year,
        sanitise_input,
    )
    logger.info("chat.py: validators OK")
except Exception as e:
    logger.error(f"chat.py: FAILED validators: {e}")
    traceback.print_exc()
    raise

logger.info("chat.py: all imports succeeded")

settings = get_settings()
router = APIRouter()

# ── Rate limiter (in-memory, per-IP) ─────────────────────────
_rate_buckets: dict[str, list[float]] = defaultdict(list)
# ── Conversation memory (in-memory, per-session) ──────────
# Stores last MAX_HISTORY messages per session for context continuity.
MAX_HISTORY = 10
_session_history: dict[str, list[dict]] = defaultdict(list)
_session_pending_intent: dict[str, str] = {}  # tracks if we asked for cutoff details

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

# Cutoff flow: only needs branch, category, gender (shows cutoff ranks)
_CUTOFF_QUESTIONS = [
    ("branch", "Which **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branches}"),
    ("category", "What is your **category / caste**?\n\n(e.g., OC, BC-A, BC-B, BC-C, BC-D, SC, ST, EWS)"),
    ("gender", "Are you a **Boy** or a **Girl**?"),
]

# Eligibility flow: needs branch, category, gender + rank (checks if eligible)
_ELIGIBILITY_QUESTIONS = [
    ("branch", "Which **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branches}"),
    ("category", "What is your **category / caste**?\n\n(e.g., OC, BC-A, BC-B, BC-C, BC-D, SC, ST, EWS)"),
    ("gender", "Are you a **Boy** or a **Girl**?"),
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


def _build_multi_branch_reply(
    branches: list[str],
    category: str,
    gender: str,
    rank: int | None = None,
) -> str:
    """
    Query cutoff/eligibility for one or more branches and build
    a combined response.
    """
    parts: list[str] = []
    for b in branches:
        if rank is not None:
            result = check_eligibility(rank, b, category, year=None, gender=gender)
        else:
            result = get_cutoff(b, category, year=None, gender=gender)
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


class ChatResponse(BaseModel):
    reply: str
    intent: str
    session_id: str
    sources: list[str] = []


# ── LLM caller ────────────────────────────────────────────────

_openai_client: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


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
) -> str:
    """Call OpenAI with the system prompt + history + context + user question."""
    system = _get_system_prompt()

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

    messages: list[dict] = [{"role": "system", "content": system}]

    # Add conversation history for continuity
    if history:
        for h in history[-MAX_HISTORY:]:
            messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": "\n".join(user_content_parts)})

    client = _get_openai()
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()


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


# ── Main endpoint ─────────────────────────────────────────────

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

    # ── Check if session is in contact collection mode ────────
    if session_id in _session_contact_data:
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
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
            collected["name"] = name
        
        elif waiting_for == "email":
            # Basic email validation
            email = user_msg.strip()
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                ask = "That doesn't look like a valid email address. Please enter your **email** (e.g., student@example.com)."
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
            collected["email"] = email
        
        elif waiting_for == "phone":
            # Extract phone number (10 digits)
            phone_match = re.search(r"\b(\d{10})\b", user_msg)
            if not phone_match:
                ask = "Please provide a valid **10-digit phone number** (e.g., 9876543210)."
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
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
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
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
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
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
                return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
        
        # All required fields collected! Ask for optional message
        if "message" not in collected:
            collected["_waiting_for"] = "message"
            ask = "Almost done! Would you like to add any **additional message** or details?\n\n(Or reply **skip** to submit now)"
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": ask})
            return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)
        
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
                    "📧 admissions@vnrvjiet.ac.in\n"
                    "📞 +91-40-2304 2758"
                )
            
            # Clean up session state
            del _session_contact_data[session_id]
            
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(reply=reply, intent="contact_request", session_id=session_id)
        
        except Exception as e:
            logger.error(f"Failed to save contact request: {e}", exc_info=True)
            reply = (
                "⚠️ There was an error processing your request. "
                "Please contact our admission team directly:\n\n"
                "📧 admissions@vnrvjiet.ac.in\n"
                "📞 +91-40-2304 2758"
            )
            del _session_contact_data[session_id]
            _session_history[session_id].append({"role": "user", "content": user_msg})
            _session_history[session_id].append({"role": "assistant", "content": reply})
            return ChatResponse(reply=reply, intent="contact_request", session_id=session_id)

    # ── Check if session is in cutoff collection mode ─────────
    if session_id in _session_cutoff_data:
        # We're collecting cutoff details step by step
        collected = _session_cutoff_data[session_id]
        waiting_for = collected.get("_waiting_for")
        flow = collected.get("_flow", "cutoff")  # "cutoff" or "eligibility"
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
                    
                    reply = _build_multi_branch_reply(
                        branches_list, 
                        collected["category"], 
                        collected["gender"], 
                        extracted_rank
                    )
                    
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": reply})
                    return ChatResponse(
                        reply=reply, intent="eligibility", session_id=session_id,
                        sources=["VNRVJIET Cutoff Database"],
                    )
                else:
                    # Still need to ask for rank
                    collected["_waiting_for"] = "rank"
                    ask = "Great! What is your **EAPCET rank**?"
                    _session_history[session_id].append({"role": "user", "content": user_msg})
                    _session_history[session_id].append({"role": "assistant", "content": ask})
                    return ChatResponse(reply=ask, intent="cutoff", session_id=session_id)
            else:
                # User wants different details - start fresh
                collected.clear()
                collected["_flow"] = "eligibility"
                collected["_waiting_for"] = "branch"
                
                avail_branches = list_branches()
                branch_list = ", ".join(avail_branches)
                ask = f"Sure! Let me help you check your eligibility.\n\nWhich **branch(es)** are you interested in? You can pick one, multiple (e.g. CSE, ECE, IT), or say **all**.\n\n{branch_list}"
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent="cutoff", session_id=session_id)
        
        # Try to extract what we asked for from the user's reply
        if waiting_for == "branch":
            vals = extract_branches(user_msg)
            if vals:
                # Resolve "ALL" to actual branch list from DB
                if vals == ["ALL"]:
                    vals = list_branches()
                collected["branch"] = vals
            else:
                # Try raw text as a single branch name
                collected["branch"] = [user_msg.strip().upper()]

        elif waiting_for == "category":
            val = extract_category(user_msg)
            if not val:
                val = user_msg.strip().upper()
            collected["category"] = val

        elif waiting_for == "gender":
            val = extract_gender(user_msg)
            if not val:
                t = user_msg.strip().lower()
                if t in ("boy", "boys", "male", "m"):
                    val = "Boys"
                elif t in ("girl", "girls", "female", "f"):
                    val = "Girls"
                else:
                    val = user_msg.strip()
            collected["gender"] = val

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
                reply += _build_multi_branch_reply(branches_list, category, gender, rank=None)
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": reply})
                return ChatResponse(
                    reply=reply, intent="cutoff", session_id=session_id,
                    sources=["VNRVJIET Cutoff Database"],
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
                return ChatResponse(reply=ask, intent="cutoff", session_id=session_id)

        # Check what's still missing and ask the next question
        for field, question_template in questions:
            if field not in collected or collected[field] is None:
                collected["_waiting_for"] = field
                if field == "branch":
                    branches = list_branches()
                    branch_list = ", ".join(branches)
                    ask = question_template.format(branches=branch_list)
                else:
                    ask = question_template
                _session_history[session_id].append({"role": "user", "content": user_msg})
                _session_history[session_id].append({"role": "assistant", "content": ask})
                return ChatResponse(reply=ask, intent="cutoff", session_id=session_id)

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
            }
        
        del _session_cutoff_data[session_id]
        _session_pending_intent.pop(session_id, None)

        has_rank = "rank" in collected
        rank_val = collected.get("rank")

        # Query each branch and combine results
        reply = _build_multi_branch_reply(branches_list, category, gender, rank_val if has_rank else None)

        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": reply})

        return ChatResponse(
            reply=reply, intent="cutoff", session_id=session_id,
            sources=["VNRVJIET Cutoff Database"],
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
        # Start contact collection flow
        _session_contact_data[session_id] = {"_waiting_for": "name"}
        ask = _CONTACT_QUESTIONS[0][1]  # First question (name)
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": ask})
        return ChatResponse(reply=ask, intent="contact_request", session_id=session_id)

    # Classify
    classification = classify(user_msg)
    intent = classification.intent

    # If we previously asked this session for cutoff details,
    # and the classifier didn't detect cutoff intent on its own,
    # force it to CUTOFF so the follow-up is handled correctly.
    pending = _session_pending_intent.get(session_id)
    if pending == "awaiting_cutoff_details" and intent == IntentType.INFORMATIONAL:
        intent = IntentType.CUTOFF
        logger.info("Overriding intent to CUTOFF (session was awaiting details)")

    # ── Greeting ──────────────────────────────────────────────
    if intent == IntentType.GREETING:
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": _GREETING_REPLY})
        return ChatResponse(
            reply=_GREETING_REPLY,
            intent=intent.value,
            session_id=session_id,
        )

    # ── Out of scope ──────────────────────────────────────
    if intent == IntentType.OUT_OF_SCOPE:
        _session_history[session_id].append({"role": "user", "content": user_msg})
        _session_history[session_id].append({"role": "assistant", "content": _OUT_OF_SCOPE_REPLY})
        return ChatResponse(
            reply=_OUT_OF_SCOPE_REPLY,
            intent=intent.value,
            session_id=session_id,
        )

    # ── Extract structured entities ───────────────────────────
    rank = extract_rank(user_msg)
    branch = extract_branch(user_msg)
    category = extract_category(user_msg)
    gender = extract_gender(user_msg)
    year = extract_year(user_msg) if intent not in (IntentType.CUTOFF, IntentType.ELIGIBILITY, IntentType.MIXED) else None

    cutoff_info = ""
    sources: list[str] = []
    rag_context = ""

    # ── Cutoff / Eligibility path ─────────────────────────────
    if intent in (IntentType.CUTOFF, IntentType.ELIGIBILITY, IntentType.MIXED):
        # Determine flow type
        is_eligibility = (intent == IntentType.ELIGIBILITY)
        flow = "eligibility" if is_eligibility else "cutoff"
        questions = _ELIGIBILITY_QUESTIONS if is_eligibility else _CUTOFF_QUESTIONS

        # Pre-fill whatever we already extracted from this message
        collected = {"_flow": flow}
        # Extract multiple branches
        branches_extracted = extract_branches(user_msg)
        if branches_extracted:
            if branches_extracted == ["ALL"]:
                branches_extracted = list_branches()
            collected["branch"] = branches_extracted
        if category:
            collected["category"] = category
        if gender:
            collected["gender"] = gender
        if rank and is_eligibility:
            collected["rank"] = rank

        # Check if all required fields are already provided
        required = [f for f, _ in questions]
        all_present = all(f in collected for f in required)

        if all_present:
            b_list = collected["branch"]
            if isinstance(b_list, str):
                b_list = [b_list]
            cutoff_info = _build_multi_branch_reply(b_list, category, gender, rank if is_eligibility else None)
            sources.append("VNRVJIET Cutoff Database")
        else:
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
                return ChatResponse(reply=ask, intent=intent.value, session_id=session_id)
            
            # Start step-by-step collection
            for field, question_template in questions:
                if field not in collected:
                    collected["_waiting_for"] = field
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
                    return ChatResponse(reply=ask, intent=intent.value, session_id=session_id)

    # ── RAG path ──────────────────────────────────────────────
    if intent in (IntentType.INFORMATIONAL, IntentType.MIXED):
        try:
            rag_result = retrieve(user_msg, top_k=5)
            rag_context = rag_result.context_text
            for chunk in rag_result.chunks:
                sources.append(f"{chunk.filename} ({chunk.source})")
            logger.info(
                "RAG retrieved %d chunks, context length: %d chars",
                len(rag_result.chunks),
                len(rag_context),
            )
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e, exc_info=True)
            rag_context = ""

    # ── Generate final answer ─────────────────────────────────
    history = _session_history.get(session_id, [])
    reply = _generate_llm_response(user_msg, rag_context, cutoff_info, history=history)

    # Clear pending intent since we got a full answer
    _session_pending_intent.pop(session_id, None)

    # Save to conversation history
    _session_history[session_id].append({"role": "user", "content": user_msg})
    _session_history[session_id].append({"role": "assistant", "content": reply})

    # Trim history to prevent unbounded growth
    if len(_session_history[session_id]) > MAX_HISTORY * 2:
        _session_history[session_id] = _session_history[session_id][-(MAX_HISTORY * 2):]

    return ChatResponse(
        reply=reply,
        intent=intent.value,
        session_id=session_id,
        sources=list(set(sources)),
    )


# ── Health & metadata ─────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "college": settings.COLLEGE_SHORT_NAME}


@router.get("/branches")
async def branches():
    return {"branches": list_branches()}
