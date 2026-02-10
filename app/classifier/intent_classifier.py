"""
Intent classifier – decides how to handle every incoming query.

Categories
----------
- informational   : general admission / college info → RAG
- cutoff          : rank / eligibility / cutoff questions → Cutoff Engine
- mixed           : needs both RAG context + cutoff data
- out_of_scope    : mentions other colleges, comparisons, predictions
- greeting        : hi / hello / thanks
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.config import get_settings

settings = get_settings()

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
    "cutoff", "cut-off", "cut off", "rank", "eligible",
    "eligibility", "seat", "chance", "get admission",
    "last rank", "closing rank", "opening rank", "eamcet",
]

_GREETING_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(hi|hello|hey|good\s*(morning|afternoon|evening)|thanks|thank\s*you|bye)\s*[!.?]*\s*$", re.I),
]


class IntentType(str, Enum):
    INFORMATIONAL = "informational"
    CUTOFF = "cutoff"
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
        if college in q and college not in safe and college not in safe_full:
            return True
    return False


def _has_compare_intent(query: str) -> bool:
    return any(p.search(query) for p in _COMPARE_PATTERNS)


def _is_greeting(query: str) -> bool:
    return any(p.match(query) for p in _GREETING_PATTERNS)


def _has_cutoff_intent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _CUTOFF_KEYWORDS)


def classify(query: str) -> ClassificationResult:
    """
    Rule-based classifier.  Fast, deterministic, no LLM cost.
    """
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

    # Heuristic: if cutoff keywords are present AND the query is long
    # (more than 12 words) it likely also needs informational context.
    word_count = len(query.split())

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
            reason="Query is about cutoff / eligibility",
        )

    return ClassificationResult(
        intent=IntentType.INFORMATIONAL,
        confidence=0.85,
        reason="General informational query",
    )
