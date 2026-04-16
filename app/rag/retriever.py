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
import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re

from openai import OpenAI, AsyncOpenAI
from pinecone import Pinecone

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_openai_client: OpenAI | None = None
_async_openai_client: AsyncOpenAI | None = None
_pinecone_index = None
_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


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


def _should_translate(query: str) -> bool:
    """
    Determine if query should be translated.
    Skip translation for simple queries (1-2 words) or queries with numbers/ranks.
    """
    if not _is_non_english(query):
        return False
    
    # Skip translation for very short queries or queries with numbers
    word_count = len(query.strip().split())
    has_numbers = any(char.isdigit() for char in query)
    
    # Don't translate single words or queries with numbers (likely rank queries)
    if word_count <= 2 or has_numbers:
        return False
    
    return True


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


@lru_cache(maxsize=1)
def _load_local_document_chunks() -> list[tuple[str, str]]:
    """Load local docs text files as a fallback retrieval corpus."""
    if not _DOCS_DIR.exists():
        return []

    chunks: list[tuple[str, str]] = []
    for path in sorted(_DOCS_DIR.rglob("*.txt")) + sorted(_DOCS_DIR.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for block in re.split(r"\n\s*\n+", text):
            snippet = block.strip()
            if len(snippet) < 40:
                continue
            chunks.append((path.name, snippet))

    return chunks


def _fallback_local_retrieve(query: str, top_k: int, score_threshold: float) -> RetrievalResult:
    """Keyword-based fallback over local docs when OpenAI embeddings are unavailable."""
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return RetrievalResult()

    scored_chunks: list[RetrievedChunk] = []
    for filename, text in _load_local_document_chunks():
        text_tokens = set(_tokenize(text))
        if not text_tokens:
            continue

        overlap = query_tokens & text_tokens
        if not overlap:
            continue

        score = len(overlap) / max(len(query_tokens), 1)
        if score < score_threshold:
            continue

        scored_chunks.append(
            RetrievedChunk(
                text=text[:2000],
                score=score,
                source="local_docs",
                year=0,
                filename=filename,
            )
        )

    scored_chunks.sort(key=lambda item: item.score, reverse=True)
    selected = scored_chunks[:top_k]

    context_parts = []
    for i, chunk in enumerate(selected, 1):
        context_parts.append(
            f"[Source {i}: {chunk.filename} ({chunk.source}), relevance: {chunk.score:.2f}]\n{chunk.text}"
        )

    return RetrievalResult(
        chunks=selected,
        context_text="\n\n---\n\n".join(context_parts) if context_parts else "",
    )


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
        logger.info(f"Translated '{query[:50]}...' to '{translation[:50]}...'")
        return translation
        
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        # Fallback to original query
        return query


async def _translate_to_english_async(query: str) -> str:
    """
    Async version of translation for better performance.
    """
    try:
        client = _get_async_openai()
        response = await client.chat.completions.create(
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
        logger.info(f"Translated '{query[:50]}...' to '{translation[:50]}...'")
        return translation
        
    except Exception as e:
        logger.error(f"Translation failed: {e}")
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
    # Translate non-English queries to English for better retrieval (optimized)
    search_query = query
    if _should_translate(query):
        search_query = _translate_to_english(query)
    
    # Embed the query (use translated version if non-English)
    try:
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

        chunks: list[RetrievedChunk] = []
        for match in matches:
            score = getattr(match, "score", 0.0)
            meta = getattr(match, "metadata", {}) or {}

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
    except Exception as exc:
        logger.warning(f"OpenAI/Pinecone retrieval failed, using local fallback: {exc}")
        return _fallback_local_retrieve(query, top_k, score_threshold)

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


async def retrieve_async(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.25,
) -> RetrievalResult:
    """
    Async version of retrieve for better performance.
    Runs translation (if needed) and embedding generation efficiently.
    """
    # Translate non-English queries (skip for simple queries)
    search_query = query
    if _should_translate(query):
        search_query = await _translate_to_english_async(query)
    
    # Embed the query
    try:
        client = _get_async_openai()
        response = await client.embeddings.create(
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

        matches = getattr(results, "matches", None) or []

        chunks: list[RetrievedChunk] = []
        for match in matches:
            score = getattr(match, "score", 0.0)
            meta = getattr(match, "metadata", {}) or {}

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
    except Exception as exc:
        logger.warning(f"OpenAI/Pinecone retrieval failed, using local fallback: {exc}")
        return _fallback_local_retrieve(query, top_k, score_threshold)

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
