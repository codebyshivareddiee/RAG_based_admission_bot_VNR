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
from app.utils.languages import DEFAULT_LANGUAGE, detect_language

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


def _detect_query_language(query: str) -> str:
    """Detect query language with safe fallback to English."""
    try:
        detected = detect_language(query)
        if detected:
            return detected
    except Exception as exc:
        logger.warning(f"Language detection failed, defaulting to English: {exc}")
    return DEFAULT_LANGUAGE


def _prepare_english_search_query(query: str) -> tuple[str, str]:
    """
    Retrieval-first workflow:
    1) detect query language,
    2) translate to English when non-English,
    3) return (search_query, detected_language).
    """
    detected_language = _detect_query_language(query)
    if detected_language != DEFAULT_LANGUAGE:
        translated = _translate_to_english(query)
        return translated or query, detected_language
    return query, detected_language


async def _prepare_english_search_query_async(query: str) -> tuple[str, str]:
    """Async version of retrieval-first query preparation."""
    detected_language = _detect_query_language(query)
    if detected_language != DEFAULT_LANGUAGE:
        translated = await _translate_to_english_async(query)
        return translated or query, detected_language
    return query, detected_language


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


def _build_context_text(chunks: list[RetrievedChunk]) -> str:
    """Build combined context text payload from retrieved chunks."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk.filename} ({chunk.source}, {chunk.year}), "
            f"relevance: {chunk.score:.2f}]\n{chunk.text}"
        )
    return "\n\n---\n\n".join(context_parts) if context_parts else ""


def _collect_chunks_sync(
    search_query: str,
    top_k: int,
    score_threshold: float,
) -> list[RetrievedChunk]:
    """Run one Pinecone retrieval attempt for a query and threshold."""
    client = _get_openai()
    response = client.embeddings.create(
        input=[search_query],
        model=settings.OPENAI_EMBEDDING_MODEL,
    )
    query_embedding = response.data[0].embedding

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
        if score < score_threshold:
            continue
        meta = getattr(match, "metadata", {}) or {}
        chunks.append(
            RetrievedChunk(
                text=meta.get("text", ""),
                score=score,
                source=meta.get("source", "unknown"),
                year=meta.get("year", 0),
                filename=meta.get("filename", ""),
            )
        )
    return chunks


async def _collect_chunks_async(
    search_query: str,
    top_k: int,
    score_threshold: float,
) -> list[RetrievedChunk]:
    """Async Pinecone retrieval attempt for a query and threshold."""
    client = _get_async_openai()
    response = await client.embeddings.create(
        input=[search_query],
        model=settings.OPENAI_EMBEDDING_MODEL,
    )
    query_embedding = response.data[0].embedding

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
        if score < score_threshold:
            continue
        meta = getattr(match, "metadata", {}) or {}
        chunks.append(
            RetrievedChunk(
                text=meta.get("text", ""),
                score=score,
                source=meta.get("source", "unknown"),
                year=meta.get("year", 0),
                filename=meta.get("filename", ""),
            )
        )
    return chunks


def _score_threshold_retry_plan(score_threshold: float) -> list[float]:
    """Generate retrieval retry thresholds (strict → relaxed)."""
    base = max(0.0, float(score_threshold))
    relaxed = max(0.12, round(base - 0.1, 2))
    if relaxed >= base:
        return [base]
    return [base, relaxed]


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
    search_query, detected_language = _prepare_english_search_query(query)
    thresholds = _score_threshold_retry_plan(score_threshold)
    attempted_queries = [search_query]
    if search_query.strip().lower() != query.strip().lower():
        attempted_queries.append(query)

    try:
        chunks: list[RetrievedChunk] = []
        selected_threshold = thresholds[0]
        selected_query = search_query

        for candidate_query in attempted_queries:
            for threshold in thresholds:
                candidate_chunks = _collect_chunks_sync(
                    search_query=candidate_query,
                    top_k=top_k,
                    score_threshold=threshold,
                )
                if candidate_chunks:
                    chunks = candidate_chunks
                    selected_threshold = threshold
                    selected_query = candidate_query
                    break
            if chunks:
                break

        if not chunks:
            fallback_threshold = thresholds[-1]
            local_result = _fallback_local_retrieve(search_query, top_k, fallback_threshold)
            if local_result.chunks:
                return local_result
            if search_query.strip().lower() != query.strip().lower():
                return _fallback_local_retrieve(query, top_k, fallback_threshold)
            return local_result

        logger.info(
            "Retrieved %d chunks using query='%s' (language=%s, threshold=%.2f)",
            len(chunks),
            selected_query[:80],
            detected_language,
            selected_threshold,
        )
        return RetrievalResult(
            chunks=chunks,
            context_text=_build_context_text(chunks),
        )

    except Exception as exc:
        logger.warning(f"OpenAI/Pinecone retrieval failed, using local fallback: {exc}")
        fallback_threshold = thresholds[-1]
        local_result = _fallback_local_retrieve(search_query, top_k, fallback_threshold)
        if local_result.chunks:
            return local_result
        if search_query.strip().lower() != query.strip().lower():
            return _fallback_local_retrieve(query, top_k, fallback_threshold)
        return local_result


async def retrieve_async(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.25,
) -> RetrievalResult:
    """
    Async version of retrieve for better performance.
    Runs translation (if needed) and embedding generation efficiently.
    """
    search_query, detected_language = await _prepare_english_search_query_async(query)
    thresholds = _score_threshold_retry_plan(score_threshold)
    attempted_queries = [search_query]
    if search_query.strip().lower() != query.strip().lower():
        attempted_queries.append(query)

    try:
        chunks: list[RetrievedChunk] = []
        selected_threshold = thresholds[0]
        selected_query = search_query

        for candidate_query in attempted_queries:
            for threshold in thresholds:
                candidate_chunks = await _collect_chunks_async(
                    search_query=candidate_query,
                    top_k=top_k,
                    score_threshold=threshold,
                )
                if candidate_chunks:
                    chunks = candidate_chunks
                    selected_threshold = threshold
                    selected_query = candidate_query
                    break
            if chunks:
                break

        if not chunks:
            fallback_threshold = thresholds[-1]
            local_result = _fallback_local_retrieve(search_query, top_k, fallback_threshold)
            if local_result.chunks:
                return local_result
            if search_query.strip().lower() != query.strip().lower():
                return _fallback_local_retrieve(query, top_k, fallback_threshold)
            return local_result

        logger.info(
            "Async retrieved %d chunks using query='%s' (language=%s, threshold=%.2f)",
            len(chunks),
            selected_query[:80],
            detected_language,
            selected_threshold,
        )
        return RetrievalResult(
            chunks=chunks,
            context_text=_build_context_text(chunks),
        )

    except Exception as exc:
        logger.warning(f"OpenAI/Pinecone retrieval failed, using local fallback: {exc}")
        fallback_threshold = thresholds[-1]
        local_result = _fallback_local_retrieve(search_query, top_k, fallback_threshold)
        if local_result.chunks:
            return local_result
        if search_query.strip().lower() != query.strip().lower():
            return _fallback_local_retrieve(query, top_k, fallback_threshold)
        return local_result
