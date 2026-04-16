"""Tests for required-documents category selection flow."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_document_flow_state():
    chat_api._PENDING_DOCUMENT_CATEGORY_SESSIONS.clear()
    yield
    chat_api._PENDING_DOCUMENT_CATEGORY_SESSIONS.clear()


def test_required_documents_prompts_for_category_selection():
    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "session_id": "docs-flow-selection"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response"].startswith("Please select your admission category to view required documents:")
    assert data["options"] == [
        {"label": "Convener (Category A)", "value": "convener"},
        {
            "label": "Management (Category B / NRI / NRI Sponsored)",
            "value": "management",
        },
        {"label": "Supernumerary Quota", "value": "supernumerary"},
    ]


def test_required_documents_waits_for_selection_and_answers_selected_category(monkeypatch):
    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        assert "Management (Category B / NRI / NRI Sponsored)" in query
        return (
            "For Management (Category B / NRI / NRI Sponsored) admission, the required documents are:\n"
            "- 10th and 12th mark sheets\n"
            "- Transfer Certificate (TC)\n"
            "- Passport and visa documents (for NRI/NRI Sponsored where applicable)"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    session_id = "docs-flow-followup"
    first = client.post(
        "/api/chat",
        json={"message": "Documents needed for admission", "session_id": session_id},
    )
    assert first.status_code == 200
    assert first.json()["options"]

    second = client.post(
        "/api/chat",
        json={"message": "2", "session_id": session_id},
    )
    assert second.status_code == 200

    data = second.json()
    assert data["response"].startswith(
        "For Management (Category B / NRI / NRI Sponsored) admission, the required documents are:"
    )
    assert "For Convener (Category A) admission" not in data["response"]
    assert data["options"] == []


def test_required_documents_stream_returns_clickable_options():
    response = client.post(
        "/api/chat/stream",
        json={"message": "Required Documents", "session_id": "docs-flow-stream"},
    )
    assert response.status_code == 200

    payload_lines = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    final_payload = json.loads(payload_lines[-1])

    assert final_payload["done"] is True
    assert final_payload["options"] == [
        {"label": "Convener (Category A)", "value": "convener"},
        {
            "label": "Management (Category B / NRI / NRI Sponsored)",
            "value": "management",
        },
        {"label": "Supernumerary Quota", "value": "supernumerary"},
    ]


def test_inline_numbered_documents_are_reformatted_to_multiline_list(monkeypatch):
    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        return (
            "For Convener (Category A) admission, the required documents are: "
            "1. TS EAPCET / JEE Main Rank Card 2. Intermediate (10+2) Marks Memo "
            "3. SSC (10th Class) Marks Memo 4. Transfer Certificate (TC)"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    session_id = "docs-flow-inline-format"
    client.post("/api/chat", json={"message": "What documents are required?", "session_id": session_id})
    response = client.post("/api/chat", json={"message": "1", "session_id": session_id})
    assert response.status_code == 200

    text = response.json()["response"]
    assert re.search(r"\n1\.\s+", text)
    assert re.search(r"\n2\.\s+", text)
    assert re.search(r"\n3\.\s+", text)
    assert "1. TS EAPCET / JEE Main Rank Card 2. Intermediate" not in text


def test_streaming_preserves_newlines_in_list_tokens(monkeypatch):
    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        return (
            "For Convener (Category A) admission, the required documents are:\n\n"
            "1. TS EAPCET / JEE Main Rank Card\n"
            "2. Intermediate (10+2) Marks Memo\n"
            "3. SSC (10th Class) Marks Memo"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    session_id = "docs-flow-stream-format"
    client.post("/api/chat", json={"message": "What documents are required?", "session_id": session_id})
    response = client.post("/api/chat/stream", json={"message": "1", "session_id": session_id})
    assert response.status_code == 200

    payload_lines = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    token_payloads = [json.loads(line) for line in payload_lines if '"token"' in line]
    streamed_text = "".join(payload["token"] for payload in token_payloads)

    assert "\n2. Intermediate (10+2) Marks Memo" in streamed_text
    assert "\n3. SSC (10th Class) Marks Memo" in streamed_text
