"""
Retriever – queries Pinecone with mandatory college filter.

Every query is filtered to VNRVJIET to guarantee no cross-college leakage.
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
    score_threshold: float = 0.3,
) -> RetrievalResult:
    """
    Embed the query and search Pinecone with a strict college filter.

    Parameters
    ----------
    query : str – user's question
    top_k : int – maximum chunks to return
    score_threshold : float – minimum similarity to include

    Returns
    -------
    RetrievalResult with ranked chunks and combined context text.
    """
    # Embed the query
    client = _get_openai()
    response = client.embeddings.create(
        input=[query],
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
