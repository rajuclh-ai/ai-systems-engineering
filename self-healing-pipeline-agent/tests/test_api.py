"""
API contract tests.
All graph calls mocked — tests verify request/response shapes and routing.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def _mock_graph_result(anomaly_type="lag_spike", severity="critical",
                       risk_score=0.6, requires_approval=False):
    return {
        "anomaly_type": anomaly_type,
        "severity": severity,
        "risk_score": risk_score,
        "requires_approval": requires_approval,
        "incident_id": "test-incident-id",
        "execution_result": MagicMock(
            strategy_executed="reroute",
            status=MagicMock(value="success"),
        ),
    }


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
        mock_graph.invoke.return_value = _mock_graph_result()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.status_code == 200


def test_trigger_incident_returns_thread_id():
    """Response includes a thread_id."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.invoke.return_value = _mock_graph_result()
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert "thread_id" in response.json()
    assert len(response.json()["thread_id"]) > 0


def test_trigger_incident_status_resolved_for_low_risk():
    """risk_score 0.6 → status=resolved."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.invoke.return_value = _mock_graph_result(risk_score=0.6, requires_approval=False)
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.json()["status"] == "resolved"


def test_trigger_incident_status_awaiting_approval_for_high_risk():
    """risk_score 0.8 → status=awaiting_approval."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.invoke.return_value = _mock_graph_result(risk_score=0.8, requires_approval=True)
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.json()["status"] == "awaiting_approval"


def test_trigger_incident_returns_anomaly_type():
    """Response includes anomaly_type from graph result."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.invoke.return_value = _mock_graph_result(anomaly_type="lag_spike")
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.json()["anomaly_type"] == "lag_spike"


def test_trigger_incident_missing_pipeline_id_returns_422():
    """Missing required field → 422 Unprocessable Entity."""
    response = client.post("/incidents", json={
        "event_type": "consumer_lag_spike",
        "metrics": {},
    })
    assert response.status_code == 422


def test_trigger_incident_graph_error_returns_500():
    """Graph exception → 500."""
    with patch("api.routes.incidents.graph") as mock_graph:
        mock_graph.invoke.side_effect = Exception("LLM error")
        response = client.post("/incidents", json=LAG_SPIKE_PAYLOAD)
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /approval/{thread_id} tests
# ---------------------------------------------------------------------------

def test_approval_approve_returns_200():
    """APPROVE decision returns 200."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.invoke.return_value = _mock_graph_result()
        response = client.post("/approval/test-thread-123", json={"decision": "APPROVE"})
    assert response.status_code == 200


def test_approval_reject_returns_200():
    """REJECT decision returns 200."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.invoke.return_value = _mock_graph_result()
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
        mock_graph.invoke.return_value = _mock_graph_result()
        response = client.post("/approval/test-thread-123", json={"decision": "APPROVE"})
    assert response.json()["thread_id"] == "test-thread-123"


def test_approval_returns_decision():
    """Approval response echoes decision."""
    with patch("api.routes.approval.graph") as mock_graph:
        mock_graph.update_state.return_value = None
        mock_graph.invoke.return_value = _mock_graph_result()
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
