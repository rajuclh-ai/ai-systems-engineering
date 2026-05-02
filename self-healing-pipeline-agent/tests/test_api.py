"""
API contract tests.
All graph calls mocked — tests verify request/response shapes and routing.

Background tasks run synchronously in FastAPI TestClient.
graph.stream() is mocked to return a list of node chunks.
graph.get_state() is mocked to return final state + whether graph is paused.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def _mock_stream_chunks(anomaly_type="lag_spike", severity="critical",
                        risk_score=0.6, requires_approval=False):
    """Minimal node chunks for a standard agent run."""
    chunks = [
        {"monitor": {"anomaly_type": anomaly_type, "severity": severity, "risk_score": risk_score}},
        {"diagnosis": {}},
        {"remediation": {"requires_approval": requires_approval, "risk_score": risk_score}},
        {"executor": {
            "execution_result": MagicMock(
                strategy_executed="reroute",
                status=MagicMock(value="success"),
            )
        }},
        {"verification": {"verification_status": "skipped"}},
        {"learning": {"incident_id": "test-incident-id"}},
    ]
    if requires_approval:
        # Graph pauses after remediation — only first 3 nodes yielded
        return chunks[:3]
    return chunks


def _mock_graph_state(anomaly_type="lag_spike", severity="critical",
                      risk_score=0.6, requires_approval=False):
    state = MagicMock()
    state.next = ["human_checkpoint"] if requires_approval else []
    state.values = {
        "anomaly_type": anomaly_type,
        "severity": severity,
        "risk_score": risk_score,
        "requires_approval": requires_approval,
        "incident_id": "test-incident-id",
    }
    return state


def _mock_approval_chunks():
    """Chunks yielded after APPROVE — executor through learning."""
    return [
        {"executor": {
            "execution_result": MagicMock(
                strategy_executed="savepoint_redeploy",
                status=MagicMock(value="success"),
            )
        }},
        {"verification": {"verification_status": "skipped"}},
        {"learning": {"incident_id": "test-incident-id"}},
    ]


LAG_SPIKE_PAYLOAD = {
    "pipeline_id": "clickstream-flink-job-03",
    "event_type": "consumer_lag_spike",
    "metrics": {
        "current_lag": 2850000,
        "threshold": 500000,
        "cpu_pct": 94,
    },
}


# ---------------------------------------------------------------------------
# POST /incidents tests
# ---------------------------------------------------------------------------

def test_trigger_incident_returns_200():
    """Valid incident payload returns 200."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks())
        mock_graph.get_state.return_value = _mock_graph_state()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.status_code == 200


def test_trigger_incident_returns_thread_id():
    """Response includes a non-empty thread_id."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks())
        mock_graph.get_state.return_value = _mock_graph_state()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert "thread_id" in response.json()
    assert len(response.json()["thread_id"]) > 0


def test_trigger_incident_returns_processing_status():
    """POST /incidents always returns status=processing immediately."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks())
        mock_graph.get_state.return_value = _mock_graph_state()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.json()["status"] == "processing"


def test_trigger_incident_missing_pipeline_id_returns_422():
    """Missing required field → 422 Unprocessable Entity."""
    response = client.post("/incidents", json={
        "event_type": "consumer_lag_spike",
        "metrics": {},
    })
    assert response.status_code == 422


def test_trigger_incident_graph_error_stores_failed_status():
    """Graph stream exception → status store records failed."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.side_effect = Exception("LLM error")
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)

    assert response.status_code == 200
    thread_id = response.json()["thread_id"]
    status_response = client.get(f"/incidents/{thread_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# GET /incidents/{thread_id}/status tests
# ---------------------------------------------------------------------------

def test_get_status_resolved_for_low_risk():
    """After agent runs, status=resolved for risk_score < 0.7."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks(risk_score=0.6))
        mock_graph.get_state.return_value = _mock_graph_state(risk_score=0.6, requires_approval=False)
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)

    thread_id = response.json()["thread_id"]
    status_response = client.get(f"/incidents/{thread_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "resolved"


def test_get_status_awaiting_approval_for_high_risk():
    """After agent pauses, status=awaiting_approval for high risk."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks(risk_score=0.8, requires_approval=True))
        mock_graph.get_state.return_value = _mock_graph_state(risk_score=0.8, requires_approval=True)
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)

    thread_id = response.json()["thread_id"]
    status_response = client.get(f"/incidents/{thread_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "awaiting_approval"


def test_get_status_returns_anomaly_type():
    """Status response includes anomaly_type from agent result."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks(anomaly_type="lag_spike"))
        mock_graph.get_state.return_value = _mock_graph_state(anomaly_type="lag_spike")
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)

    thread_id = response.json()["thread_id"]
    status_response = client.get(f"/incidents/{thread_id}/status")
    assert status_response.json()["anomaly_type"] == "lag_spike"


def test_get_status_returns_nodes_completed():
    """Status response includes the list of nodes that ran."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.stream.return_value = iter(_mock_stream_chunks())
        mock_graph.get_state.return_value = _mock_graph_state()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)

    thread_id = response.json()["thread_id"]
    status_response = client.get(f"/incidents/{thread_id}/status")
    nodes = status_response.json()["nodes_completed"]
    assert isinstance(nodes, list)
    assert "monitor" in nodes
    assert "learning" in nodes


def test_get_status_unknown_thread_returns_404():
    """Unknown thread_id → 404."""
    response = client.get("/incidents/nonexistent-thread/status")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /approval/{thread_id} tests
# ---------------------------------------------------------------------------

def test_approval_approve_returns_200():
    """APPROVE decision returns 200."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.stream.return_value = iter(_mock_approval_chunks())
        response = client.post("/approval/test-thread-123", json={"decision": "APPROVE"})
    assert response.status_code == 200


def test_approval_reject_returns_200():
    """REJECT decision returns 200."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.stream.return_value = iter([{"learning": {"incident_id": "test-id"}}])
        response = client.post("/approval/test-thread-123", json={"decision": "REJECT"})
    assert response.status_code == 200


def test_approval_invalid_decision_returns_400():
    """Invalid decision value → 400."""
    response = client.post("/approval/test-thread-123", json={"decision": "MAYBE"})
    assert response.status_code == 400


def test_approval_returns_thread_id():
    """Approval response echoes thread_id."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.stream.return_value = iter(_mock_approval_chunks())
        response = client.post("/approval/test-thread-123", json={"decision": "APPROVE"})
    assert response.json()["thread_id"] == "test-thread-123"


def test_approval_returns_decision():
    """Approval response echoes decision."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.stream.return_value = iter(_mock_approval_chunks())
        response = client.post("/approval/test-thread-123", json={"decision": "APPROVE"})
    assert response.json()["decision"] == "APPROVE"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_check():
    """Health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
