"""Tests for contextual follow-ups and mandatory clickable link formatting."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import app.api.chat as chat_api
from app.classifier.intent_classifier import ClassificationResult, IntentType
from app.main import app
from app.rag.retriever import RetrievalResult, RetrievedChunk


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_LANGUAGE_BY_ID.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()

    def force_info(_: str) -> ClassificationResult:
        return ClassificationResult(
            intent=IntentType.INFORMATIONAL,
            confidence=1.0,
            reason="forced informational behavior",
        )

    monkeypatch.setattr(chat_api, "classify", force_info)
    yield

    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_LANGUAGE_BY_ID.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()


def test_short_followup_without_prior_context_asks_clarification(monkeypatch):
    calls = {"count": 0}

    async def fake_retrieve(_: str, language: str = "en", additional_instructions: str = "") -> str:
        calls["count"] += 1
        return "This should not be called for ambiguous short follow-up."

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve)

    response = client.post(
        "/api/chat",
        json={"message": "fees?", "session_id": "ctx-clarify-1", "language": "en"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["needs_clarification"] is True
    assert "Could you clarify which program or topic you mean" in payload["response"]
    assert calls["count"] == 0


def test_short_followup_reuses_previous_context_for_retrieval(monkeypatch):
    observed_queries: list[str] = []

    async def fake_retrieve(query: str, language: str = "en", additional_instructions: str = "") -> str:
        observed_queries.append(query)
        return "Contextual answer"

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve)

    session_id = "ctx-followup-2"
    first = client.post(
        "/api/chat",
        json={"message": "B.Tech admissions", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "fees?", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200

    assert len(observed_queries) == 2
    assert observed_queries[1].startswith(("B.Tech admissions", "B. Tech admissions"))
    assert "Follow-up question: fees?" in observed_queries[1]


def test_raw_url_is_converted_to_clickable_markdown_link(monkeypatch):
    async def fake_retrieve(_: str, language: str = "en", additional_instructions: str = "") -> str:
        return "Visit https://vnrvjiet.ac.in/it/ for details."

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve)

    response = client.post(
        "/api/chat",
        json={"message": "Tell me about IT department", "session_id": "ctx-link-3", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "[👉 Click here to know more](https://vnrvjiet.ac.in/it/)" in text
    assert "Visit https://vnrvjiet.ac.in/it/" not in text


def test_transport_fee_query_returns_cta_links(monkeypatch):
    def fake_retrieve(_: str, top_k: int = 5) -> RetrievalResult:
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    text="transport fees",
                    score=0.95,
                    source="unit-test",
                    year=2026,
                    filename="transport_fee_links.txt",
                )
            ],
            context_text=(
                "BTech First Year Transport Fee: https://drive.google.com/file/d/first-year/view\n"
                "BTech 2nd, 3rd & 4th Year Transport Fee: https://drive.google.com/file/d/other-years/view"
            ),
        )

    monkeypatch.setattr(chat_api, "retrieve", fake_retrieve)

    response = client.post(
        "/api/chat",
        json={"message": "transport fee details", "session_id": "ctx-transport-1", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "For the transport fee structure, you can check the official documents below:" in text
    assert "👉 **BTech First Year Transport Fee**" in text
    assert "👉 **BTech 2nd, 3rd & 4th Year Transport Fee**" in text
    assert "Click here to view: [Open document](https://drive.google.com/file/d/first-year/view)" in text
    assert "Click here to view: [Open document](https://drive.google.com/file/d/other-years/view)" in text
    assert "Do you want hostel fee details as well?" in text


def test_transport_fee_query_without_links_returns_fallback(monkeypatch):
    def fake_retrieve(_: str, top_k: int = 5) -> RetrievalResult:
        return RetrievalResult(chunks=[], context_text="")

    monkeypatch.setattr(chat_api, "retrieve", fake_retrieve)

    response = client.post(
        "/api/chat",
        json={"message": "bus fee", "session_id": "ctx-transport-2", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "I'm not able to fetch the transport fee document right now" in text
    assert "👉 [Click here to know more](https://vnrvjiet.ac.in/)" in text
    assert "Would you like me to help with approximate fee details?" in text
