"""
Automated test suite for the VNRVJIET Admissions Chatbot.

Run:  pytest tests/test_chatbot.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.classifier.intent_classifier import IntentType, classify
from app.logic.cutoff_engine import check_eligibility, get_cutoff, list_branches
from app.utils.validators import (
    extract_branch,
    extract_category,
    extract_rank,
    extract_year,
    sanitise_input,
)
from app.data.init_db import init_db


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_db(tmp_path_factory):
    """Ensure the test database is initialised."""
    db_path = str(tmp_path_factory.mktemp("data") / "test_cutoffs.db")
    init_db(db_path)
    # Patch settings for tests
    from app.config import get_settings
    settings = get_settings()
    settings.CUTOFF_DB_PATH = db_path


client = TestClient(app)


# ═══════════════════════════════════════════════════════════════
# 1. INTENT CLASSIFIER TESTS
# ═══════════════════════════════════════════════════════════════

class TestIntentClassifier:
    def test_greeting(self):
        assert classify("Hi").intent == IntentType.GREETING
        assert classify("Hello!").intent == IntentType.GREETING
        assert classify("Thank you").intent == IntentType.GREETING

    def test_informational(self):
        result = classify("What is the admission process?")
        assert result.intent == IntentType.INFORMATIONAL

    def test_cutoff(self):
        result = classify("CSE cutoff for OC?")
        assert result.intent == IntentType.CUTOFF

    def test_eligibility(self):
        result = classify("Can I get ECE with rank 21000?")
        assert result.intent == IntentType.CUTOFF

    def test_out_of_scope_other_college(self):
        result = classify("What is the cutoff for CBIT?")
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_out_of_scope_comparison(self):
        result = classify("Compare VNRVJIET with VIT")
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_out_of_scope_iit(self):
        result = classify("What is IIT Bombay cutoff?")
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_out_of_scope_prediction(self):
        result = classify("Predict the cutoff for next year")
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_mixed_query(self):
        result = classify(
            "What is the cutoff rank for CSE and also tell me about the admission process and documents required?"
        )
        assert result.intent == IntentType.MIXED


# ═══════════════════════════════════════════════════════════════
# 2. VALIDATOR / EXTRACTOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestValidators:
    def test_sanitise_input(self):
        assert sanitise_input("  hello  ") == "hello"
        assert "<script>" not in sanitise_input("<script>alert(1)</script>")

    def test_extract_rank_plain(self):
        assert extract_rank("I got 21000 rank") == 21000

    def test_extract_rank_comma(self):
        assert extract_rank("My rank is 21,000") == 21000

    def test_extract_rank_k(self):
        assert extract_rank("I got 21k rank") == 21000

    def test_extract_rank_none(self):
        assert extract_rank("What is the admission process?") is None

    def test_extract_branch_cse(self):
        assert extract_branch("CSE cutoff") == "CSE"

    def test_extract_branch_ece(self):
        assert extract_branch("can I get ECE?") == "ECE"

    def test_extract_branch_ai(self):
        assert extract_branch("AI & ML branch") == "CSE (AI & ML)"

    def test_extract_branch_none(self):
        assert extract_branch("What is admission?") is None

    def test_extract_category_obc(self):
        assert extract_category("OBC category") == "BC-D"

    def test_extract_category_sc(self):
        assert extract_category("SC reservation") == "SC"

    def test_extract_year(self):
        assert extract_year("cutoff 2025") == 2025
        assert extract_year("no year here") is None


# ═══════════════════════════════════════════════════════════════
# 3. CUTOFF ENGINE TESTS
# ═══════════════════════════════════════════════════════════════

class TestCutoffEngine:
    def test_list_branches(self):
        branches = list_branches()
        assert isinstance(branches, list)
        assert len(branches) > 0

    def test_get_cutoff_cse_oc(self):
        result = get_cutoff("CSE", "OC", 2025)
        assert result.cutoff_rank is not None
        assert result.branch == "CSE"

    def test_eligibility_pass(self):
        result = check_eligibility(2000, "CSE", "OC", 2025)
        assert result.eligible is True

    def test_eligibility_fail(self):
        result = check_eligibility(50000, "CSE", "OC", 2025)
        assert result.eligible is False

    def test_missing_data(self):
        result = get_cutoff("NONEXISTENT", "OC", 2025)
        assert result.cutoff_rank is None
        assert "not found" in result.message.lower() or "not available" in result.message.lower()


# ═══════════════════════════════════════════════════════════════
# 4. API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════

class TestAPI:
    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_branches(self):
        resp = client.get("/api/branches")
        assert resp.status_code == 200
        assert "branches" in resp.json()

    def test_empty_message(self):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422  # Pydantic validation

    def test_widget_page(self):
        resp = client.get("/widget")
        assert resp.status_code == 200
        assert "VNRVJIET" in resp.text


# ═══════════════════════════════════════════════════════════════
# 5. REQUIRED TEST CASES (from spec)
# ═══════════════════════════════════════════════════════════════

class TestRequiredScenarios:
    """
    These tests verify the REQUIRED test cases from the spec.
    Note: /api/chat requires OpenAI keys for LLM calls.
    We test the classification + cutoff logic layers directly.
    """

    def test_admission_process_query(self):
        """'What is the admission process?' → informational"""
        result = classify("What is the admission process?")
        assert result.intent == IntentType.INFORMATIONAL

    def test_eligibility_query(self):
        """'I got 21,000 rank OBC, can I get ECE?' → cutoff"""
        result = classify("I got 21,000 rank OBC, can I get ECE?")
        assert result.intent == IntentType.CUTOFF

        rank = extract_rank("I got 21,000 rank OBC, can I get ECE?")
        branch = extract_branch("I got 21,000 rank OBC, can I get ECE?")
        category = extract_category("I got 21,000 rank OBC, can I get ECE?")

        assert rank == 21000
        assert branch == "ECE"
        assert category == "BC-D"  # OBC maps to BC-D in Telangana

        elig = check_eligibility(rank, branch, category, 2025)
        assert elig.eligible is not None  # Should have data

    def test_documents_query(self):
        """'What documents are required?' → informational"""
        result = classify("What documents are required?")
        assert result.intent == IntentType.INFORMATIONAL

    def test_other_college_must_refuse(self):
        """'Cutoff for XYZ College?' → out_of_scope"""
        # The spec says "XYZ College" but we test with known other colleges
        result = classify("What is the cutoff for CBIT college?")
        assert result.intent == IntentType.OUT_OF_SCOPE

    def test_comparison_must_refuse(self):
        """'Compare with ABC College' → out_of_scope"""
        result = classify("Compare VNRVJIET with VIT college")
        assert result.intent == IntentType.OUT_OF_SCOPE
