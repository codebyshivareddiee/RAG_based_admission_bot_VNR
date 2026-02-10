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
    extract_category,
    extract_rank,
    extract_year,
    sanitise_input,
)

settings = get_settings()
router = APIRouter()

# ── Rate limiter (in-memory, per-IP) ─────────────────────────
_rate_buckets: dict[str, list[float]] = defaultdict(list)


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
) -> str:
    """Call OpenAI with the system prompt + context + user question."""
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

    client = _get_openai()
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n".join(user_content_parts)},
        ],
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

    # Classify
    classification = classify(user_msg)
    intent = classification.intent

    # ── Greeting ──────────────────────────────────────────────
    if intent == IntentType.GREETING:
        return ChatResponse(
            reply=_GREETING_REPLY,
            intent=intent.value,
            session_id=session_id,
        )

    # ── Out of scope ──────────────────────────────────────────
    if intent == IntentType.OUT_OF_SCOPE:
        return ChatResponse(
            reply=_OUT_OF_SCOPE_REPLY,
            intent=intent.value,
            session_id=session_id,
        )

    # ── Extract structured entities ───────────────────────────
    rank = extract_rank(user_msg)
    branch = extract_branch(user_msg)
    category = extract_category(user_msg)
    year = extract_year(user_msg)

    cutoff_info = ""
    sources: list[str] = []
    rag_context = ""

    # ── Cutoff / Eligibility path ─────────────────────────────
    if intent in (IntentType.CUTOFF, IntentType.MIXED):
        if rank and branch:
            cat = category or "OC"
            result = check_eligibility(rank, branch, cat, year)
            cutoff_info = result.message
            if result.all_results:
                sources.append("VNRVJIET Cutoff Database")
        elif branch:
            result = get_cutoff(branch, category or "OC", year)
            cutoff_info = result.message
            if result.all_results:
                rows_text = []
                for r in result.all_results:
                    rows_text.append(
                        f"  • {r['category']} / Round {r['round']} / {r['year']}: "
                        f"Rank {r['cutoff_rank']:,}"
                    )
                cutoff_info += "\n\nAll matching records:\n" + "\n".join(rows_text)
                sources.append("VNRVJIET Cutoff Database")
        elif rank and category:
            # No branch specified → show available branches
            branches = list_branches()
            cutoff_info = (
                f"You mentioned rank {rank:,} under {category} category, "
                f"but didn't specify a branch. Available branches: {', '.join(branches)}. "
                "Please specify which branch you are interested in."
            )

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
    reply = _generate_llm_response(user_msg, rag_context, cutoff_info)

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
