from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_serves_pure_chatbot():
    """Test that / serves the chatbot as a full-viewport page."""
    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    # Chatbot DOM should remain intact so original functionality works.
    assert 'id="chat-toggle"' in body
    assert 'id="welcome-popup"' in body
    assert 'id="chat-container"' in body
    assert '.fullscreen-mode .chat-container' in body
    # Should have fullscreen mode enabled
    assert 'fullscreen=true' in body