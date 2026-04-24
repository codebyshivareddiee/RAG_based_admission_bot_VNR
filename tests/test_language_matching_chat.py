"""Tests for response-language matching and session language memory."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.classifier.intent_classifier import ClassificationResult, IntentType
from app.logic.cutoff_engine import CutoffResult
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_chat_language_state(monkeypatch):
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_LANGUAGE_BY_ID.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()

    def force_cutoff(_: str) -> ClassificationResult:
        return ClassificationResult(
            intent=IntentType.CUTOFF,
            confidence=1.0,
            reason="forced cutoff for language tests",
        )

    monkeypatch.setattr(chat_api, "classify", force_cutoff)
    yield
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_LANGUAGE_BY_ID.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()


def test_telugu_query_gets_telugu_missing_branch_response():
    response = client.post(
        "/api/chat",
        json={"message": "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు", "session_id": "lang-te-1", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "దయచేసి మీరు ఏ శాఖ గురించి అడుగుతున్నారో పేర్కొనండి." in text


def test_english_query_gets_english_missing_branch_response():
    response = client.post(
        "/api/chat",
        json={"message": "cutoff ranks", "session_id": "lang-en-1", "language": "te"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "Please specify which branch you're asking about." in text


def test_ambiguous_followup_keeps_session_language():
    session_id = "lang-memory-te"
    first = client.post(
        "/api/chat",
        json={"message": "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "CSE cutoff", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    text = second.json()["response"]
    assert "దయచేసి మీ వర్గాన్ని పేర్కొనండి." in text


def test_internal_option_value_does_not_switch_language():
    session_id = "lang-option-value-sticky"
    first = client.post(
        "/api/chat",
        json={"message": "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "management", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "దయచేసి మీరు ఏ శాఖ గురించి అడుగుతున్నారో పేర్కొనండి." in second.json()["response"]


def test_fresh_session_internal_value_uses_requested_language_not_english():
    response = client.post(
        "/api/chat",
        json={"message": "convener", "session_id": "fresh-hidden-code-te", "language": "te"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "దయచేసి మీరు ఏ శాఖ గురించి అడుగుతున్నారో పేర్కొనండి." in text


def test_forced_ui_language_overrides_stale_session_language_for_internal_values():
    session_id = "lang-force-ui-session"
    first = client.post(
        "/api/chat",
        json={"message": "అవసరమైన పత్రాలు", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200
    assert first.json()["options"][0]["label"] == "బి.టెక్"

    forced = client.post(
        "/api/chat",
        json={
            "message": "btech",
            "session_id": session_id,
            "language": "en",
            "force_language": True,
            "selected_option_label": "B.Tech",
            "selected_option_value": "btech",
        },
    )
    assert forced.status_code == 200
    payload = forced.json()
    assert "Please select your admission category:" in payload["response"]
    assert payload["options"][0]["label"] == "Convener (Category A)"


def test_latest_sentence_language_overrides_forced_previous_language():
    session_id = "lang-latest-message-priority"
    first = client.post(
        "/api/chat",
        json={"message": "कटऑफ रैंक बताएं", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200
    assert "कृपया बताएं आप किस शाखा के बारे में पूछ रहे हैं।" in first.json()["response"]

    second = client.post(
        "/api/chat",
        json={
            "message": "what is the fee structure for btech",
            "session_id": session_id,
            "language": "hi",
            "force_language": True,
        },
    )
    assert second.status_code == 200
    assert "Please specify which branch you're asking about." in second.json()["response"]


def test_selected_option_display_label_controls_language_over_internal_value():
    response = client.post(
        "/api/chat",
        json={
            "message": "btech",
            "selected_option_value": "btech",
            "selected_option_label": "बी.टेक",
            "session_id": "lang-visible-label-hi",
            "language": "en",
        },
    )
    assert response.status_code == 200
    assert "कृपया बताएं आप किस शाखा के बारे में पूछ रहे हैं।" in response.json()["response"]


def test_cutoff_followup_inherits_previous_filters(monkeypatch):
    observed_calls: list[dict] = []

    def fake_get_cutoff(
        branch: str,
        category: str,
        year: int | None = None,
        gender: str = "Any",
        quota: str = "Convenor",
        language: str = "en",
    ) -> CutoffResult:
        observed_calls.append(
            {
                "branch": branch,
                "category": category,
                "year": year,
                "gender": gender,
                "quota": quota,
                "language": language,
            }
        )
        return CutoffResult(
            found=True,
            branch=branch,
            category=category,
            year=year,
            gender=gender,
            quota=quota,
            message=f"{branch} ok",
        )

    monkeypatch.setattr(chat_api, "get_cutoff", fake_get_cutoff)

    session_id = "cutoff-memory-filters"
    first = client.post(
        "/api/chat",
        json={
            "message": "CSE BC-D girls cutoff 2023",
            "session_id": session_id,
            "language": "en",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "ECE cutoff", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200

    assert observed_calls[0]["branch"] == "CSE"
    assert observed_calls[0]["category"] == "BC-D"
    assert observed_calls[0]["year"] == 2023
    assert observed_calls[0]["gender"] == "Girls"

    assert observed_calls[1]["branch"] == "ECE"
    assert observed_calls[1]["category"] == "BC-D"
    assert observed_calls[1]["year"] == 2023
    assert observed_calls[1]["gender"] == "Girls"


def test_documents_query_short_script_input_pivots_language():
    session_id = "lang-docs-script-pivot"
    first = client.post(
        "/api/chat",
        json={"message": "आवश्यक दस्तावेज", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200
    assert first.json()["options"][0]["label"] == "बी.टेक"

    second = client.post(
        "/api/chat",
        json={"message": "అవసరమైన పత్రాలు", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "మీ ప్రోగ్రామ్" in second.json()["response"]
    assert second.json()["options"][0]["label"] == "బి.టెక్"


def test_documents_query_full_sentence_script_input_pivots_language():
    session_id = "lang-docs-script-pivot-full"
    first = client.post(
        "/api/chat",
        json={"message": "आवश्यक दस्तावेज", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200
    assert first.json()["options"][0]["label"] == "बी.टेक"

    second = client.post(
        "/api/chat",
        json={"message": "నాకు అవసరమైన ప్రవేశ పత్రాలు చెప్పండి", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "మీ ప్రోగ్రామ్" in second.json()["response"]
    assert second.json()["options"][0]["label"] == "బి.టెక్"


def test_different_language_followup_without_switch_request_switches_to_new_language():
    session_id = "lang-lock-en"
    first = client.post(
        "/api/chat",
        json={"message": "cutoff ranks", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "CSE cutoff क्या है?", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "कृपया अपनी श्रेणी बताएं।" in second.json()["response"]


def test_clear_english_followup_switches_to_english():
    session_id = "lang-memory-switch"
    first = client.post(
        "/api/chat",
        json={"message": "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "What is the CSE cutoff rank?", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    text = second.json()["response"]
    assert "Please specify your category." in text


def test_english_full_sentence_followup_switches_to_english():
    session_id = "lang-explicit-switch"
    first = client.post(
        "/api/chat",
        json={"message": "బ్రాంచ్‌లకు కట్‌ఆఫ్ ర్యాంకులు", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "Please respond in English", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "Please specify which branch you're asking about." in second.json()["response"]


def test_document_internal_code_uses_language_lock_and_deep_translation(monkeypatch):
    async def fake_retrieve(_: str, language: str = "en", additional_instructions: str = "") -> str:
        assert language == "hi"
        return (
            "1. original + 2 photocopies\n"
            "2. Rank Card\n"
            "3. transfer certificate"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve)

    session_id = "lang-docs-hidden-code-hi"

    start = client.post(
        "/api/chat",
        json={"message": "आवश्यक दस्तावेज", "session_id": session_id, "language": "en"},
    )
    assert start.status_code == 200
    assert start.json()["options"][0]["label"] == "बी.टेक"

    program = client.post(
        "/api/chat",
        json={"message": "btech", "session_id": session_id, "language": "en"},
    )
    assert program.status_code == 200
    assert "btech" not in program.json()["response"].lower()
    assert "प्रवेश श्रेणी" in program.json()["response"]

    category = client.post(
        "/api/chat",
        json={"message": "convener", "session_id": session_id, "language": "en"},
    )
    assert category.status_code == 200
    text = category.json()["response"]
    assert text.startswith("कन्वीनर कोटा के लिए आवश्यक दस्तावेज़:")
    assert "मूल + 2 छायाप्रतियां" in text
    assert "रैंक कार्ड" in text
    assert "स्थानांतरण प्रमाणपत्र" in text


@pytest.mark.parametrize(
    ("language", "expected_migration", "expected_combo"),
    [
        ("hi", "प्रवासन प्रमाणपत्र", "मूल + छायाप्रति"),
        ("te", "వలస ధృవీకరణ పత్రం", "అసలు + నకలు"),
    ],
)
def test_mandatory_translation_rules_for_migration_and_original_combo(
    language,
    expected_migration,
    expected_combo,
):
    raw = "Migration Certificate; Original + Photocopy; original + 2 photocopies"
    sanitized = chat_api._sanitize_non_english_response_leakage(raw, language)

    assert expected_migration in sanitized
    assert expected_combo in sanitized
    assert "migration certificate" not in sanitized.lower()
    assert "original + photocopy" not in sanitized.lower()


def test_document_internal_code_keeps_marathi_and_sanitizes_english_terms(monkeypatch):
    async def fake_retrieve(_: str, language: str = "en", additional_instructions: str = "") -> str:
        assert language == "mr"
        return (
            "Documents: original + 2 photocopies\n"
            "Rank Card\n"
            "Intermediate (10+2) Marks Memo\n"
            "Category A"
        )

    monkeypatch.setattr(chat_api, "retrieve_and_respond", fake_retrieve)

    session_id = "lang-docs-hidden-code-mr"

    start = client.post(
        "/api/chat",
        json={"message": "आवश्यक कागदपत्रे कोणती आहेत?", "session_id": session_id, "language": "en"},
    )
    assert start.status_code == 200
    assert start.json()["options"][0]["label"] == "बी.टेक"

    program = client.post(
        "/api/chat",
        json={"message": "btech", "session_id": session_id, "language": "en"},
    )
    assert program.status_code == 200
    assert "प्रवेश श्रेणी" in program.json()["response"]

    category = client.post(
        "/api/chat",
        json={"message": "convener", "session_id": session_id, "language": "en"},
    )
    assert category.status_code == 200
    text = category.json()["response"]
    assert text.startswith("कन्व्हीनर कोट्यासाठी आवश्यक कागदपत्रे:")
    assert "कागदपत्रे:" in text
    assert "मूळ + 2 छायाप्रती" in text
    assert "रँक कार्ड" in text
    assert "10+2 गुणपत्रक" in text
    assert "प्रवर्ग A" in text
    assert "original" not in text.lower()
    assert "photocopies" not in text.lower()
    assert "rank card" not in text.lower()
    assert "documents" not in text.lower()


def test_documents_prompt_localizes_to_telugu():
    response = client.post(
        "/api/chat",
        json={"message": "అవసరమైన పత్రాలు ఏమిటి?", "session_id": "lang-docs-te", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "మీ ప్రోగ్రామ్" in data["response"]
    assert data["options"][0]["label"].startswith("బి.టెక్")
    assert all(not re.search(r"[A-Za-z]", option["label"]) for option in data["options"])


def test_marathi_documents_prompt_does_not_fall_back_to_hindi():
    response = client.post(
        "/api/chat",
        json={"message": "आवश्यक कागदपत्रे", "session_id": "lang-docs-mr", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "कृपया तुमचा प्रोग्राम निवडा:" in data["response"]
    assert "कृपया अपना प्रोग्राम चुनें:" not in data["response"]


@pytest.mark.parametrize(
    ("language", "expected_phrase", "expected_rank_card"),
    [
        ("ta", "அசல் + 2 நகல்கள்", "தரவரிசை அட்டை"),
        ("kn", "ಮೂಲ + 2 ಛಾಯಾಪ್ರತಿಗಳು", "ಶ್ರೇಣಿ ಕಾರ್ಡ್"),
        ("bn", "মূল + 2 ফটোকপি", "র‍্যাঙ্ক কার্ড"),
        ("gu", "મૂળ + 2 ફોટોકોપીઓ", "રેન્ક કાર્ડ"),
    ],
)
def test_leakage_sanitizer_covers_additional_languages(language, expected_phrase, expected_rank_card):
    raw = "1. original + 2 photocopies\n2. Rank Card\n3. transfer certificate"
    sanitized = chat_api._sanitize_non_english_response_leakage(raw, language)

    assert expected_phrase in sanitized
    assert expected_rank_card in sanitized
    assert "original" not in sanitized.lower()
    assert "photocopies" not in sanitized.lower()
    assert "rank card" not in sanitized.lower()


@pytest.mark.parametrize(
    ("language", "expected_btech", "expected_mtech"),
    [
        ("hi", "बी टेक", "एम टेक"),
        ("te", "బి టెక్", "ఎం టెక్"),
        ("mr", "बी टेक", "एम टेक"),
    ],
)
def test_leakage_sanitizer_localizes_program_abbreviations(language, expected_btech, expected_mtech):
    raw = "B.Tech and M.Tech admissions are open."
    sanitized = chat_api._sanitize_non_english_response_leakage(raw, language)

    assert expected_btech in sanitized
    assert expected_mtech in sanitized
    assert "b.tech" not in sanitized.lower()
    assert "m.tech" not in sanitized.lower()
