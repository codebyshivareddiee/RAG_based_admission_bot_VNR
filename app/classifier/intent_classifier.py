"""
Intent classifier – decides how to handle every incoming query.

Categories
----------
- informational   : general admission / college info → RAG
- cutoff          : rank / eligibility / cutoff questions → Cutoff Engine
- mixed           : needs both RAG context + cutoff data
- out_of_scope    : mentions other colleges, comparisons, predictions
- greeting        : hi / hello / thanks

MULTILINGUAL SUPPORT
--------------------
Uses a hybrid approach:
1. Fast keyword-based classification for English queries
2. LLM-based classification for non-English languages (universal support)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

from openai import OpenAI

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_openai_client: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client

# ── Known competitor / other-college keywords ─────────────────
_OTHER_COLLEGES: list[str] = [
    "iit", "nit", "iiit", "bits", "vit", "srm", "manipal",
    "amrita", "jntu", "osmania", "cbit", "chaitanya", "vasavi",
    "muffakham", "mgit", "cvr", "mlr", "anurag", "cmr",
    "gokaraju", "griet", "bvrit", "keshav", "matrusri",
    "stanley", "anna university", "mit", "harvard",
    "xyz college", "abc college",
]

_COMPARE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bcompar(e|ison|ing)\b", re.I),
    re.compile(r"\bvs\.?\b", re.I),
    re.compile(r"\bversus\b", re.I),
    re.compile(r"\bbetter\s+than\b", re.I),
    re.compile(r"\brankings?\s+(of|for)\b", re.I),
    re.compile(r"\bnational\s+cutoff\b", re.I),
    re.compile(r"\bpredict(ion|ed|ing)?\b", re.I),
]

_CUTOFF_KEYWORDS: list[str] = [
    "cutoff", "cut-off", "cut off",
    "last rank", "closing rank", "opening rank",
    "eapcet", "tseamcet", "ts eamcet", "ap eamcet", "tgeapcet",
    "seat allotment", "counselling", "counseling",
    "trend", "trends", "trending", "rank trend",
    "previous year", "previous years", "past year", "past years",
    "historical rank", "historical cutoff", "year by year",
    "over the years", "across years", "comparison over years",
]

_ELIGIBILITY_KEYWORDS: list[str] = [
    "eligible", "eligibility", "can i get", "will i get",
    "chance", "get admission", "my rank", "admission chance",
    "will i", "can i", "do i qualify", "am i eligible",
    "check eligibility", "seat eligibility", "rank check",
]

_GREETING_KEYWORDS: list[str] = [
    "hi", "hello", "hey", "thanks", "thank you", "bye",
    "good morning", "good afternoon", "good evening",
]


class IntentType(str, Enum):
    INFORMATIONAL = "informational"
    CUTOFF = "cutoff"
    ELIGIBILITY = "eligibility"
    MIXED = "mixed"
    OUT_OF_SCOPE = "out_of_scope"
    GREETING = "greeting"


@dataclass
class ClassificationResult:
    intent: IntentType
    confidence: float
    reason: str


def _mentions_other_college(query: str) -> bool:
    """Return True if query references any college other than VNRVJIET."""
    q = query.lower()
    # Allow mentions of VNRVJIET itself
    safe = settings.COLLEGE_SHORT_NAME.lower()
    safe_full = settings.COLLEGE_NAME.lower()
    for college in _OTHER_COLLEGES:
        # Use word boundary matching to avoid false positives like "mit" in "submit" or "nit" in "original"
        pattern = r'\b' + re.escape(college) + r'\b'
        if re.search(pattern, q, re.IGNORECASE) and college not in safe and college not in safe_full:
            return True
    return False


def _has_compare_intent(query: str) -> bool:
    return any(p.search(query) for p in _COMPARE_PATTERNS)


def _is_greeting(query: str) -> bool:
    """Check if query is a simple greeting."""
    q = query.strip().lower()
    return any(kw in q for kw in _GREETING_KEYWORDS) and len(q.split()) <= 3


def _has_cutoff_intent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _CUTOFF_KEYWORDS)


def _has_eligibility_intent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _ELIGIBILITY_KEYWORDS)


def _is_non_english(query: str) -> bool:
    """
    Detect if query contains significant non-ASCII characters (likely non-English).
    Uses a simple heuristic: if >30% of characters are non-ASCII, it's likely non-English.
    """
    if not query:
        return False
    non_ascii_count = sum(1 for c in query if ord(c) > 127)
    total_chars = len(query.replace(" ", ""))  # Exclude spaces
    if total_chars == 0:
        return False
    return (non_ascii_count / total_chars) > 0.3


def _classify_with_llm(query: str) -> ClassificationResult:
    """
    Use LLM to classify intent. Works for ANY language.
    This is the fallback for non-English queries or when keyword matching fails.
    """
    try:
        client = _get_openai()
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            messages=[
                {
                    "role": "system",
                    "content": """You are an intent classifier for a college admissions chatbot.
                    
Classify the user's query into ONE of these intents:
- informational: General questions about college, courses, facilities, placements, fees, hostel, campus, etc.
- cutoff: Questions about admission cutoff ranks, previous year ranks, rank trends (WITHOUT the user's own rank)
- eligibility: Questions about admission chances where user provides their rank (e.g., "Can I get admission with 5000 rank?")
- out_of_scope: Questions about OTHER colleges, comparisons with other institutions, predictions
- greeting: Simple greetings like hi, hello, thanks, bye (in any language)

Respond with ONLY the intent name in lowercase. Nothing else."""
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            temperature=0,
            max_tokens=10,
        )
        
        intent_str = response.choices[0].message.content.strip().lower()
        logger.info(f"LLM classified '{query[:50]}...' as: {intent_str}")
        
        # Map to IntentType
        intent_map = {
            "informational": IntentType.INFORMATIONAL,
            "cutoff": IntentType.CUTOFF,
            "eligibility": IntentType.ELIGIBILITY,
            "out_of_scope": IntentType.OUT_OF_SCOPE,
            "greeting": IntentType.GREETING,
        }
        
        intent = intent_map.get(intent_str, IntentType.INFORMATIONAL)
        return ClassificationResult(
            intent=intent,
            confidence=0.85,
            reason=f"LLM-based classification (multilingual)"
        )
        
    except Exception as e:
        logger.error(f"LLM classification failed: {e}")
        # Fallback to informational
        return ClassificationResult(
            intent=IntentType.INFORMATIONAL,
            confidence=0.5,
            reason="LLM classification failed, defaulting to informational"
        )


def _looks_like_cutoff_data(query: str) -> bool:
    """
    Detect structured follow-up answers like:
      'cse, bc-b, boy, 2022'
      'ECE BC-A girl 15000'
      'IT, OC, boys, 8000'
    These contain branch + category + gender + number but no cutoff keywords.
    """
    from app.utils.validators import extract_branch, extract_category, extract_gender, extract_rank
    branch = extract_branch(query)
    category = extract_category(query)
    gender = extract_gender(query)
    rank = extract_rank(query)
    # If we have at least 3 of the 4 fields, it's cutoff data
    fields_found = sum([
        branch is not None,
        category is not None,
        gender is not None,
        rank is not None,
    ])
    return fields_found >= 3


def classify(query: str) -> ClassificationResult:
    """
    Hybrid intent classifier with multilingual support.
    
    Strategy:
    1. Use fast keyword-based classification for English queries
    2. Use LLM-based classification for non-English queries (universal language support)
    3. Use LLM fallback if keyword-based classification is uncertain
    """
    # Check if query is in a non-English language
    if _is_non_english(query):
        logger.info(f"Non-English query detected, using LLM classifier: {query[:50]}...")
        return _classify_with_llm(query)
    
    # ── Fast keyword-based classification for English ───
    
    if _is_greeting(query):
        return ClassificationResult(
            intent=IntentType.GREETING,
            confidence=0.95,
            reason="Greeting detected",
        )

    if _mentions_other_college(query) or _has_compare_intent(query):
        return ClassificationResult(
            intent=IntentType.OUT_OF_SCOPE,
            confidence=0.95,
            reason="Query references another college or requests a comparison",
        )

    has_cutoff = _has_cutoff_intent(query)
    has_eligibility = _has_eligibility_intent(query)
    looks_like_data = _looks_like_cutoff_data(query)

    # Heuristic: if cutoff keywords are present AND the query is long
    # (more than 12 words) it likely also needs informational context.
    word_count = len(query.split())

    # Eligibility check ("will I get?", "can I get?", "check eligibility")
    if has_eligibility:
        return ClassificationResult(
            intent=IntentType.ELIGIBILITY,
            confidence=0.90,
            reason="Query is about eligibility / admission chance",
        )

    # Structured data with rank → eligibility; without rank → cutoff
    if looks_like_data:
        from app.utils.validators import extract_rank
        has_rank = extract_rank(query) is not None
        return ClassificationResult(
            intent=IntentType.ELIGIBILITY if has_rank else IntentType.CUTOFF,
            confidence=0.90,
            reason="Structured cutoff data detected",
        )

    if has_cutoff and word_count > 12:
        return ClassificationResult(
            intent=IntentType.MIXED,
            confidence=0.80,
            reason="Query involves cutoff data and additional context",
        )

    if has_cutoff:
        return ClassificationResult(
            intent=IntentType.CUTOFF,
            confidence=0.90,
            reason="Query is about cutoff ranks",
        )

    return ClassificationResult(
        intent=IntentType.INFORMATIONAL,
        confidence=0.85,
        reason="General informational query",
    )
