"""Tests for contextual follow-ups and mandatory clickable link formatting."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import app.api.chat as chat_api
from app.classifier.intent_classifier import ClassificationResult, IntentType
from app.main import app
from app.rag.retriever import RetrievalResult, RetrievedChunk


client = TestClient(app)

_MANDATORY_DISCLAIMER = (
    "Fees are subject to change based on the academic year and university/government guidelines."
)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    chat_api._DOCUMENT_FLOW_STATE_BY_SESSION.clear()
    chat_api._DOCUMENT_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._SESSION_LANGUAGE_BY_ID.clear()
    chat_api._SESSION_CONTEXT_BY_ID.clear()
    chat_api._SESSION_CUTOFF_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._MANAGEMENT_FEE_FLOW_STATE_BY_SESSION.clear()
    chat_api._MANAGEMENT_FEE_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._BTECH_FEE_FLOW_STATE_BY_SESSION.clear()

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
    chat_api._MANAGEMENT_FEE_FLOW_STATE_BY_SESSION.clear()
    chat_api._MANAGEMENT_FEE_SLOT_MEMORY_BY_SESSION.clear()
    chat_api._BTECH_FEE_FLOW_STATE_BY_SESSION.clear()


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
    monkeypatch.setattr(
        chat_api,
        "classify",
        lambda _: ClassificationResult(
            intent=IntentType.INFORMATIONAL,
            confidence=1.0,
            reason="forced informational behavior",
        ),
    )

    response = client.post(
        "/api/chat",
        json={"message": "Give details about facilities", "session_id": "ctx-link-3", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert 'Visit 👉 <a href="https://vnrvjiet.ac.in/it/" target="_blank">Click here to know more</a> for details.' in text
    assert text.rstrip().endswith('👉 <a href="https://www.vnrvjiet.ac.in/facilities" target="_blank">Click here to know more</a>')
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
    assert text.rstrip().endswith('👉 <a href="https://vnrvjiet.ac.in/transport/" target="_blank">Click here to know more</a>')
    assert "Would you like me to help with approximate fee details?" in text


def test_hostel_ac_questions_return_fixed_answer_with_footer():
    response = client.post(
        "/api/chat",
        json={"message": "Are AC rooms available for boys hostel?", "session_id": "ctx-hostel-1", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "AC rooms are not available for boys hostel. They are only available in the girls hostel." in text
    assert text.rstrip().endswith('👉 <a href="https://www.vnrvjiet.ac.in/hostel" target="_blank">Click here to know more</a>')


def test_management_fee_query_triggers_clarification():
    """Management fee asks should stay in fee flow (not cutoff) and ask quota selection first."""
    response = client.post(
        "/api/chat",
        json={"message": "What is the fee for management category in CSE?", "session_id": "mgmt-fee-1", "language": "en"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Please select your admission quota to view the B.Tech fee details:" in payload["response"]
    assert payload["intent"] == "informational"
    assert payload["options"][1]["value"] == "management"


def test_management_fee_extraction_function():
    """Test the extraction function directly."""
    # Test Category-B extraction
    assert chat_api._extract_management_fee_selection("Category-B") == "category_b"
    assert chat_api._extract_management_fee_selection("category-b") == "category_b"
    assert chat_api._extract_management_fee_selection("Category B") == "category_b"
    assert chat_api._extract_management_fee_selection("1") == "category_b"
    assert chat_api._extract_management_fee_selection("first") == "category_b"
    
    # Test NRI extraction
    assert chat_api._extract_management_fee_selection("NRI") == "nri"
    assert chat_api._extract_management_fee_selection("nri") == "nri"
    assert chat_api._extract_management_fee_selection("2") == "nri"
    assert chat_api._extract_management_fee_selection("second") == "nri"
    
    # Test no match
    assert chat_api._extract_management_fee_selection("some random message") is None


def test_management_fee_category_b_direct_call():
    """Test management fee handler directly with mocked dependencies."""
    import asyncio
    
    async def test_direct():
        # First call to initiate the flow
        response1 = await chat_api._handle_management_fee_clarification_flow(
            user_message="What is the management fee?",
            session_id="direct-test-1",
            language="en"
        )
        assert response1 is not None
        assert "Management quota includes multiple categories" in response1.response
        
        # Second call with selection
        response2 = await chat_api._handle_management_fee_clarification_flow(
            user_message="Category-B",
            session_id="direct-test-1",
            language="en"
        )
        assert response2 is not None
        assert "Category-B (Management Quota) Fee Structure:" in response2.response
        assert "The tuition fee for all B.Tech programmes under Category-B (Management Quota) is approximately ₹2,50,000 – ₹4,00,000 per annum." in response2.response
        assert "Note: Category-B fees may vary slightly depending on demand and academic year." in response2.response
        assert "Please contact the admissions office" not in response2.response
    
    asyncio.run(test_direct())


def test_management_fee_nri_selection_returns_fee():
    """Test that selecting NRI returns the appropriate fee guidance."""
    session_id = "mgmt-fee-3"
    
    # First request: trigger fee quota-selection flow
    response1 = client.post(
        "/api/chat",
        json={"message": "What is the fee for management category in IT?", "session_id": session_id, "language": "en"},
    )
    assert response1.status_code == 200
    assert "Please select your admission quota to view the B.Tech fee details:" in response1.json()["response"]

    # Second request: choose management
    response2 = client.post(
        "/api/chat",
        json={"message": "Management Quota", "session_id": session_id, "language": "en"},
    )
    assert response2.status_code == 200
    assert "Please select the type of Management Quota:" in response2.json()["response"]
    
    # Third request: select NRI using "2"
    response3 = client.post(
        "/api/chat",
        json={"message": "2", "session_id": session_id, "language": "en"},
    )
    assert response3.status_code == 200
    text = response3.json()["response"]
    assert "NRI Quota Fee Structure (per annum):" in text
    assert "$5000 per annum" in text
    assert text.rstrip().endswith('👉 <a href="https://vnrvjiet.ac.in/admission/" target="_blank">Click here to know more</a>')


def test_management_fee_nri_full_word_selection():
    """Test that selecting NRI by full word 'NRI' also works."""
    session_id = "mgmt-fee-4"
    
    # First request: trigger clarification
    response1 = client.post(
        "/api/chat",
        json={"message": "management fee CSE", "session_id": session_id, "language": "en"},
    )
    assert response1.status_code == 200
    
    # Second request: select NRI by full word
    response2 = client.post(
        "/api/chat",
        json={"message": "NRI", "session_id": session_id, "language": "en"},
    )
    assert response2.status_code == 200
    text = response2.json()["response"]
    assert "The NRI Quota fee for Computer Science and Engineering is $5000 per annum." in text
    assert "The following branches have a fee of" not in text


def test_btech_fee_query_prompts_quota_selection_with_clickable_options():
    response = client.post(
        "/api/chat",
        json={"message": "What is the B.Tech fee structure?", "session_id": "btech-fee-1", "language": "en"},
    )
    assert response.status_code == 200
    payload = response.json()
    text = payload["response"]
    assert "Please select your admission quota to view the B.Tech fee details:" in text
    assert "1) Category-A (Convener Quota)" in text
    assert "2) Management Quota" in text
    assert "a) Category-B" in text
    assert "b) NRI Quota" in text
    assert "3) Supernumerary Quota" in text

    options = payload["options"]
    assert len(options) == 3
    assert options[0]["value"] == "category_a"
    assert options[1]["value"] == "management"
    assert options[2]["value"] == "supernumerary"


def test_btech_fee_category_a_selection_returns_fee_and_all_branches():
    session_id = "btech-fee-2"
    first = client.post(
        "/api/chat",
        json={"message": "B.Tech fees", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "Category-A (Convener Quota)", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    text = second.json()["response"]
    assert "Category-A (Convener Quota) Fee Structure:" in text
    assert "The tuition fee for all B.Tech programmes under Category-A (Convener Quota) is ₹1,59,600 per annum." in text
    assert "Please note that fees may vary based on the academic year and specific branch regulations." in text
    assert _MANDATORY_DISCLAIMER in text
    assert "1." not in text
    assert "etc." not in text.lower()


def test_btech_fee_management_flow_and_nri_details():
    session_id = "btech-fee-3"
    first = client.post(
        "/api/chat",
        json={"message": "Tell me B.Tech fee details", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "Management Quota", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert "Please select the type of Management Quota:" in second_payload["response"]
    assert len(second_payload["options"]) == 2
    assert second_payload["options"][0]["value"] == "category_b"
    assert second_payload["options"][1]["value"] == "nri"

    third = client.post(
        "/api/chat",
        json={"message": "NRI Quota", "session_id": session_id, "language": "en"},
    )
    assert third.status_code == 200
    text = third.json()["response"]
    assert "NRI Quota Fee Structure (per annum):" in text
    assert "The following branches have a fee of $5000 per annum:" in text
    assert "The following branches have a fee of $3500 per annum:" in text
    assert "The following branches have a fee of $3000 per annum:" in text
    assert "All other branches have a fee of" not in text
    assert "Information for NRI fee regarding the following branches is currently unavailable:" in text
    assert "Note: Fees may vary depending on the academic year and fluctuations in USD to INR exchange rates." in text
    assert _MANDATORY_DISCLAIMER in text


def test_btech_fee_management_flow_category_b_returns_complete_structure():
    session_id = "btech-fee-5"
    first = client.post(
        "/api/chat",
        json={"message": "B.Tech fee details", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "Management Quota", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    assert "Please select the type of Management Quota:" in second.json()["response"]

    third = client.post(
        "/api/chat",
        json={"message": "Category-B", "session_id": session_id, "language": "en"},
    )
    assert third.status_code == 200
    text = third.json()["response"]
    assert "Category-B (Management Quota) Fee Structure:" in text
    assert "The tuition fee for all B.Tech programmes under Category-B (Management Quota) is approximately ₹2,50,000 – ₹4,00,000 per annum." in text
    assert "Please note that fees may vary based on the academic year and specific branch regulations." in text
    assert "Note: Category-B fees may vary slightly depending on demand and academic year." in text
    assert _MANDATORY_DISCLAIMER in text


def test_btech_fee_supernumerary_selection_returns_contact_message():
    session_id = "btech-fee-4"
    first = client.post(
        "/api/chat",
        json={"message": "B.Tech tuition fee", "session_id": session_id, "language": "en"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/chat",
        json={"message": "Supernumerary Quota", "session_id": session_id, "language": "en"},
    )
    assert second.status_code == 200
    text = second.json()["response"]
    assert "Information for Fees regarding Supernumerary Quota is currently unavailable." in text
    assert _MANDATORY_DISCLAIMER in text


def test_fee_query_with_category_b_typos_does_not_drift_to_cutoff():
    response = client.post(
        "/api/chat",
        json={"message": "fee structurte for category - b brznches", "session_id": "btech-fee-6", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "Category-B (Management Quota) Fee Structure:" in text
    assert "Cutoff rank information is available only for Convener quota" not in text
    assert "No cutoff information is available for the requested quota" not in text


def test_btech_fee_quota_prompt_buttons_follow_selected_language_hindi():
    response = client.post(
        "/api/chat",
        json={"message": "B.Tech fees", "session_id": "btech-fee-hi-1", "language": "hi"},
    )
    assert response.status_code == 200
    payload = response.json()
    options = payload["options"]
    assert len(options) == 3
    assert options[0]["label"] == "कैटेगरी-A (कन्वीनर कोटा)"
    assert options[1]["label"] == "मैनेजमेंट कोटा"
    assert options[2]["label"] == "सुपरन्यूमरेरी कोटा"


def test_specific_entity_nri_fee_for_cse_returns_only_cse_data_point():
    response = client.post(
        "/api/chat",
        json={"message": "NRI fee for CSE", "session_id": "btech-fee-specific-1", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "The NRI Quota fee for Computer Science and Engineering is $5000 per annum." in text
    assert "The following branches have a fee of" not in text
    assert "Civil Engineering" not in text
    assert _MANDATORY_DISCLAIMER in text


def test_specific_entity_nri_fee_ai_ml_shorthand_maps_correctly():
    response = client.post(
        "/api/chat",
        json={"message": "NRI fee for AI ML", "session_id": "btech-fee-specific-2", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "The NRI Quota fee for CSE – Artificial Intelligence & Machine Learning is $5000 per annum." in text
    assert "The following branches have a fee of" not in text
    assert _MANDATORY_DISCLAIMER in text


def test_specific_entity_category_b_fee_for_mechanical_returns_single_point():
    response = client.post(
        "/api/chat",
        json={"message": "Category-B fee for Mechanical", "session_id": "btech-fee-specific-3", "language": "en"},
    )
    assert response.status_code == 200
    text = response.json()["response"]
    assert "The Category-B (Management Quota) tuition fee for Mechanical Engineering is approximately ₹2,50,000 – ₹4,00,000 per annum." in text
    assert "The tuition fee for all B.Tech programmes" not in text
    assert "Automobile Engineering" not in text
    assert _MANDATORY_DISCLAIMER in text
