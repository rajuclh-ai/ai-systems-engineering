"""
Tests for FastAPI routes.
POST /reviews  — accepts pr_url or diff, returns thread_id.
GET  /reviews/{id} — polls status.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from api.main import app
from api import status_store

client = TestClient(app)


def _clear_store():
    status_store._store.clear()


# ---------------------------------------------------------------------------
# POST /reviews
# ---------------------------------------------------------------------------

def test_post_reviews_accepts_pr_url():
    _clear_store()
    with patch("api.routes.reviews._run_review"):
        resp = client.post("/reviews", json={"pr_url": "https://github.com/owner/repo/pull/1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert data["status"] == "processing"


def test_post_reviews_accepts_raw_diff(sample_diff):
    _clear_store()
    with patch("api.routes.reviews._run_review"):
        resp = client.post("/reviews", json={"diff": sample_diff})
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"


def test_post_reviews_rejects_empty_body():
    resp = client.post("/reviews", json={})
    assert resp.status_code == 400
    assert "pr_url or diff" in resp.json()["detail"]


def test_post_reviews_returns_immediately():
    """POST returns before the agent finishes — thread_id is immediately valid."""
    _clear_store()
    with patch("api.routes.reviews._run_review"):
        resp = client.post("/reviews", json={"pr_url": "https://github.com/owner/repo/pull/1"})
    thread_id = resp.json()["thread_id"]
    # Immediately poll — should be "processing"
    status_resp = client.get(f"/reviews/{thread_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "processing"


# ---------------------------------------------------------------------------
# GET /reviews/{thread_id}
# ---------------------------------------------------------------------------

def test_get_review_status_not_found():
    resp = client.get("/reviews/nonexistent-thread-id")
    assert resp.status_code == 404


def test_get_review_status_completed(sample_critic_report, three_agent_results):
    _clear_store()
    thread_id = "test-thread-123"
    status_store.set_status(thread_id, {
        "thread_id":     thread_id,
        "status":        "completed",
        "verdict":       "REQUEST_CHANGES",
        "critic_report": sample_critic_report.model_dump(),
        "agent_results": [r.model_dump() for r in three_agent_results],
        "review_id":     "rev-abc",
    })
    resp = client.get(f"/reviews/{thread_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["verdict"] == "REQUEST_CHANGES"
    assert data["critic_report"]["summary"] == sample_critic_report.summary
    assert len(data["agent_results"]) == 3


def test_get_review_status_failed():
    _clear_store()
    thread_id = "test-failed-thread"
    status_store.set_status(thread_id, {
        "thread_id": thread_id,
        "status":    "failed",
        "error":     "LLM unreachable",
    })
    resp = client.get(f"/reviews/{thread_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"] == "LLM unreachable"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def test_index_returns_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PR Review Agent" in resp.text
