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
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()
    yield
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()


def test_required_documents_prompts_for_program_selection():
    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "session_id": "docs-flow-selection"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response"].startswith("Please select your program:")
    assert data["options"] == [
        {"label": "B.Tech", "value": "btech"},
        {"label": "M.Tech", "value": "mtech"},
        {"label": "MBA / MCA", "value": "mba_mca"},
    ]


def test_required_documents_waits_for_program_then_category_and_answers_selection(monkeypatch):
    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        assert "M.Tech" in query
        assert "Management (Category B / NRI)" in query
        return (
            "For Management (Category B / NRI) admission, the required documents are:\n"
            "- 10th and 12th mark sheets\n"
            "- Transfer Certificate (TC)\n"
            "- Passport and visa documents (for NRI where applicable)"
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
    assert "Please select your admission category:" in second.json()["response"]
    assert second.json()["response"].startswith("Okay, for M.Tech:")
    assert second.json()["options"] == [
        {"label": "Convener (Category A)", "value": "convener"},
        {
            "label": "Management (Category B / NRI)",
            "value": "management",
        },
        {"label": "Supernumerary Quota", "value": "supernumerary"},
    ]

    third = client.post(
        "/api/chat",
        json={"message": "2", "session_id": session_id},
    )
    assert third.status_code == 200

    data = third.json()
    assert data["response"].startswith("For Management (Category B / NRI) admission")
    assert "For Convener (Category A) admission" not in data["response"]
    assert data["options"] == []


def test_documents_flow_accepts_localized_option_labels_and_keeps_language(monkeypatch):
    observed: dict[str, str] = {}

    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        observed["query"] = query
        observed["language"] = language
        return "- ట్రాన్స్‌ఫర్ సర్టిఫికేట్\n- మార్క్స్ మెమోలు"

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    session_id = "docs-flow-localized-selection"
    first = client.post(
        "/api/chat",
        json={"message": "అవసరమైన పత్రాలు ఏమిటి?", "session_id": session_id},
    )
    assert first.status_code == 200
    assert "మీ ప్రోగ్రామ్" in first.json()["response"]
    assert all(not re.search(r"[A-Za-z]", option["label"]) for option in first.json()["options"])

    second = client.post(
        "/api/chat",
        json={"message": "mtech", "session_id": session_id},
    )
    assert second.status_code == 200
    assert "మీ ప్రవేశ కోటాను ఎంచుకోండి" in second.json()["response"]
    assert all(not re.search(r"[A-Za-z]", option["label"]) for option in second.json()["options"])

    third = client.post(
        "/api/chat",
        json={"message": "management", "session_id": session_id},
    )
    assert third.status_code == 200

    assert observed["language"] == "te"
    assert "M.Tech" in observed["query"]
    assert "Management (Category B / NRI)" in observed["query"]
    assert third.json()["response"].startswith("మేనేజ్మెంట్ కోటాకు అవసరమైన పత్రాలు:")


def test_documents_query_with_program_and_category_skips_selection(monkeypatch):
    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        assert "B.Tech" in query
        assert "Convener (Category A)" in query
        return "For Convener (Category A) admission, the required documents are:\n- TS EAPCET Rank Card"

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    response = client.post(
        "/api/chat",
        json={"message": "B.Tech convener documents కావాలి", "session_id": "docs-flow-direct"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["options"] == []
    assert data["metadata"]["document_program"] == "btech"
    assert data["metadata"]["document_category"] == "convener"
    assert "Please select your program" not in data["response"]
    assert "Please select your admission category" not in data["response"]


def test_documents_flow_reuses_known_slots_without_repeating_questions(monkeypatch):
    calls = {"count": 0}

    async def fake_retrieve_and_respond(query: str, language: str = "en", additional_instructions: str = "") -> str:
        calls["count"] += 1
        return (
            "For Management (Category B / NRI) admission, the required documents are:\n"
            "- Transfer Certificate"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve_and_respond)

    session_id = "docs-flow-slot-memory"
    client.post("/api/chat", json={"message": "Required documents", "session_id": session_id})
    client.post("/api/chat", json={"message": "btech", "session_id": session_id})
    first_answer = client.post("/api/chat", json={"message": "management", "session_id": session_id})
    assert first_answer.status_code == 200
    assert first_answer.json()["options"] == []

    followup = client.post(
        "/api/chat",
        json={"message": "required documents please", "session_id": session_id},
    )
    assert followup.status_code == 200
    assert followup.json()["options"] == []
    assert "Please select your program" not in followup.json()["response"]
    assert "Please select your admission category" not in followup.json()["response"]
    assert calls["count"] == 2


def test_hindi_documents_flow_uses_pure_hindi_category_buttons():
    session_id = "docs-flow-hindi-buttons"
    first = client.post(
        "/api/chat",
        json={"message": "आवश्यक दस्तावेज", "session_id": session_id},
    )
    assert first.status_code == 200
    assert first.json()["options"] == [
        {"label": "बी.टेक", "value": "btech"},
        {"label": "एम.टेक", "value": "mtech"},
        {"label": "एमबीए/एमसीए", "value": "mba_mca"},
    ]

    second = client.post(
        "/api/chat",
        json={"message": "बी.टेक", "session_id": session_id},
    )
    assert second.status_code == 200
    assert second.json()["options"] == [
        {"label": "कन्वीनर कोटा", "value": "convener"},
        {"label": "मैनेजमेंट कोटा", "value": "management"},
        {"label": "सुपरन्यूमरेरी कोटा", "value": "supernumerary"},
    ]


def test_documents_flow_pivots_when_user_switches_script_mid_flow():
    session_id = "docs-flow-pivot-hi-te"
    first = client.post(
        "/api/chat",
        json={"message": "आवश्यक दस्तावेज", "session_id": session_id},
    )
    assert first.status_code == 200
    assert "प्रोग्राम" in first.json()["response"]
    assert all(not re.search(r"[A-Za-z]", option["label"]) for option in first.json()["options"])

    second = client.post(
        "/api/chat",
        json={"message": "ఎం.టెక్", "session_id": session_id},
    )
    assert second.status_code == 200
    assert "దయచేసి మీ ప్రవేశ కోటాను ఎంచుకోండి:" in second.json()["response"]
    assert second.json()["options"] == [
        {"label": "కన్వీనర్ కోటా", "value": "convener"},
        {"label": "మేనేజ్మెంట్ కోటా", "value": "management"},
        {"label": "సూపర్న్యూమరరీ కోటా", "value": "supernumerary"},
    ]


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
        {"label": "B.Tech", "value": "btech"},
        {"label": "M.Tech", "value": "mtech"},
        {"label": "MBA / MCA", "value": "mba_mca"},
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
    client.post("/api/chat", json={"message": "1", "session_id": session_id})
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
    client.post("/api/chat", json={"message": "1", "session_id": session_id})
    response = client.post("/api/chat/stream", json={"message": "1", "session_id": session_id})
    assert response.status_code == 200

    payload_lines = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    token_payloads = [json.loads(line) for line in payload_lines if '"token"' in line]
    streamed_text = "".join(payload["token"] for payload in token_payloads)

    assert "\n2. Intermediate (10+2) Marks Memo" in streamed_text
    assert "\n3. SSC (10th Class) Marks Memo" in streamed_text
