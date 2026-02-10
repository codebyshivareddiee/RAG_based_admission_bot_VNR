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
import time
import uuid
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from openai import OpenAI

from app.config import get_settings
from app.classifier.intent_classifier import IntentType, classify
from app.logic.cutoff_engine import (
    check_eligibility,
    get_cutoff,
    get_all_cutoffs_for_branch,
    list_branches,
)
from app.rag.retriever import retrieve
from app.utils.validators import (
    extract_branch,
    extract_branches,
    extract_category,
    extract_gender,
    extract_rank,
    extract_year,
    sanitise_input,
)

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

    # ── Check if session is in cutoff collection mode ─────────
    if session_id in _session_cutoff_data:
        # We're collecting cutoff details step by step
        collected = _session_cutoff_data[session_id]
        waiting_for = collected.get("_waiting_for")
        flow = collected.get("_flow", "cutoff")  # "cutoff" or "eligibility"
        questions = _ELIGIBILITY_QUESTIONS if flow == "eligibility" else _CUTOFF_QUESTIONS

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
