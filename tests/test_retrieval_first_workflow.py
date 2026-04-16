"""Tests for retrieval-first translation workflow."""

from __future__ import annotations

import asyncio

import app.rag.retriever as retriever


def _sample_chunk() -> retriever.RetrievedChunk:
    return retriever.RetrievedChunk(
        text="Sample admissions data",
        score=0.91,
        source="pinecone",
        year=2025,
        filename="sample.txt",
    )


def test_non_english_query_translates_before_vdb_search(monkeypatch):
    monkeypatch.setattr(retriever, "detect_language", lambda _: "te")

    translated = {"value": None}

    def fake_translate(query: str) -> str:
        translated["value"] = query
        return "CSE cutoff ranks"

    search_calls: list[str] = []

    def fake_collect(search_query: str, top_k: int, score_threshold: float):
        search_calls.append(search_query)
        return [_sample_chunk()]

    monkeypatch.setattr(retriever, "_translate_to_english", fake_translate)
    monkeypatch.setattr(retriever, "_collect_chunks_sync", fake_collect)

    result = retriever.retrieve("బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు")

    assert translated["value"] == "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు"
    assert search_calls[0] == "CSE cutoff ranks"
    assert len(result.chunks) == 1


def test_retrieve_uses_english_query_for_fallback_when_no_vdb_hits(monkeypatch):
    monkeypatch.setattr(retriever, "detect_language", lambda _: "te")
    monkeypatch.setattr(retriever, "_translate_to_english", lambda _: "admission documents list")
    monkeypatch.setattr(retriever, "_collect_chunks_sync", lambda *args, **kwargs: [])

    fallback_calls: list[str] = []

    def fake_fallback(query: str, top_k: int, score_threshold: float):
        fallback_calls.append(query)
        if query == "admission documents list":
            chunk = retriever.RetrievedChunk(
                text="Documents data from local fallback",
                score=0.5,
                source="local_docs",
                year=0,
                filename="docs.txt",
            )
            return retriever.RetrievalResult(
                chunks=[chunk],
                context_text="[Source 1: docs.txt]\nDocuments data from local fallback",
            )
        return retriever.RetrievalResult()

    monkeypatch.setattr(retriever, "_fallback_local_retrieve", fake_fallback)

    result = retriever.retrieve("అడ్మిషన్ పత్రాలు")

    assert fallback_calls
    assert fallback_calls[0] == "admission documents list"
    assert result.chunks


def test_async_prepare_query_translates_non_english(monkeypatch):
    monkeypatch.setattr(retriever, "detect_language", lambda _: "te")

    async def fake_translate_async(query: str) -> str:
        assert query == "కట్‌ఆఫ్"
        return "cutoff"

    monkeypatch.setattr(retriever, "_translate_to_english_async", fake_translate_async)

    search_query, detected_language = asyncio.run(
        retriever._prepare_english_search_query_async("కట్‌ఆఫ్")
    )

    assert detected_language == "te"
    assert search_query == "cutoff"
