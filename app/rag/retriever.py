"""
Retriever – queries Pinecone with mandatory college filter.

Every query is filtered to VNRVJIET to guarantee no cross-college leakage.

MULTILINGUAL SUPPORT:
- Translates non-English queries to English before embedding
- Ensures effective retrieval from English knowledge base
- LLM can still respond in the original language
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from openai import OpenAI
from pinecone import Pinecone

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_openai_client: OpenAI | None = None
_pinecone_index = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _get_index():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        _pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)
    return _pinecone_index


def _is_non_english(text: str) -> bool:
    """
    Detect if text contains significant non-ASCII characters (likely non-English).
    Uses a simple heuristic: if >30% of characters are non-ASCII, it's likely non-English.
    """
    if not text:
        return False
    non_ascii_count = sum(1 for c in text if ord(c) > 127)
    total_chars = len(text.replace(" ", ""))  # Exclude spaces
    if total_chars == 0:
        return False
    return (non_ascii_count / total_chars) > 0.3


def _translate_to_english(query: str) -> str:
    """
    Translate non-English query to English for better retrieval from English knowledge base.
    Uses GPT-4o-mini for fast, accurate translation.
    """
    try:
        client = _get_openai()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Translate the following query to English. Respond with ONLY the English translation, nothing else."
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            temperature=0,
            max_tokens=100,
        )
        
        translation = response.choices[0].message.content.strip()
        logger.info(f"Translated '{query[:50]}...' to '{translation}'")
        return translation
        
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        # Fallback to original query
        return query


@dataclass
class RetrievedChunk:
    text: str
    score: float
    source: str
    year: int
    filename: str


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    context_text: str = ""


def retrieve(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.25,  # Lowered default for more inclusive retrieval
) -> RetrievalResult:
    """
    Embed the query and search Pinecone with a strict college filter.
    Uses semantic search to find relevant documents across all categories.
    
    MULTILINGUAL: Translates non-English queries to English before embedding
    to improve retrieval accuracy from English knowledge base.

    Parameters
    ----------
    query : str – user's question (in any language)
    top_k : int – maximum chunks to return (default: 5, can go higher for comprehensive search)
    score_threshold : float – minimum similarity to include (default: 0.25 for inclusive retrieval)

    Returns
    -------
    RetrievalResult with ranked chunks and combined context text.
    """
    # Translate non-English queries to English for better retrieval
    search_query = query
    if _is_non_english(query):
        logger.info(f"Non-English query detected, translating for retrieval: {query[:50]}...")
        search_query = _translate_to_english(query)
    
    # Embed the query (use translated version if non-English)
    client = _get_openai()
    response = client.embeddings.create(
        input=[search_query],
        model=settings.OPENAI_EMBEDDING_MODEL,
    )
    query_embedding = response.data[0].embedding

    # Query Pinecone with MANDATORY college filter
    index = _get_index()
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
        filter={"college": {"$eq": settings.COLLEGE_SHORT_NAME}},
    )

    # Use attribute access (works with Pinecone client v3+/v4+/v5+)
    matches = getattr(results, "matches", None) or []

    if search_query != query:
        logger.info(
            "Pinecone returned %d matches for translated query: '%s' (original: '%s')",
            len(matches),
            search_query[:80],
            query[:80],
        )
    else:
        logger.info(
            "Pinecone returned %d matches for query: '%s'",
            len(matches),
            query[:80],
        )

    chunks: list[RetrievedChunk] = []
    for match in matches:
        score = getattr(match, "score", 0.0)
        meta = getattr(match, "metadata", {}) or {}

        logger.info(
            "  Match: score=%.3f, file=%s",
            score,
            meta.get("filename", "?"),
        )
        if score < score_threshold:
            continue
        chunks.append(
            RetrievedChunk(
                text=meta.get("text", ""),
                score=score,
                source=meta.get("source", "unknown"),
                year=meta.get("year", 0),
                filename=meta.get("filename", ""),
            )
        )

    # Build combined context
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk.filename} ({chunk.source}, {chunk.year}), "
            f"relevance: {chunk.score:.2f}]\n{chunk.text}"
        )

    return RetrievalResult(
        chunks=chunks,
        context_text="\n\n---\n\n".join(context_parts) if context_parts else "",
    )
