"""
Tests for the Learning Node.
Uses in-memory SQLite to avoid touching the real DB.
"""
import pytest
from unittest.mock import patch, MagicMock
from agent.nodes.learning import learning_node


def _make_state(event, root_cause=None, remediation_plan=None,
                execution_result=None, human_decision=None, anomaly_type="lag_spike"):
    return {
        "event": event,
        "anomaly_type": anomaly_type,
        "root_cause": root_cause,
        "remediation_plan": remediation_plan,
        "execution_result": execution_result,
        "human_decision": human_decision,
        "messages": [],
        "iteration_count": 0,
    }


def _mock_db_session():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


def test_learning_stores_incident(lag_spike_event, sample_root_cause, sample_remediation_plan, sample_execution_result):
    """Learning node stores incident and returns incident_id."""
    state = _make_state(lag_spike_event, sample_root_cause, sample_remediation_plan, sample_execution_result)
    with patch("agent.nodes.learning.init_db"):
        with patch("agent.nodes.learning.get_session") as mock_get:
            mock_get.return_value = _mock_db_session()
            result = learning_node(state)

    assert "incident_id" in result
    assert result["stored"] is True
    assert len(result["incident_id"]) > 0


def test_learning_stores_unknown_anomaly(lag_spike_event):
    """UNKNOWN anomaly is stored with fallback values."""
    state = _make_state(lag_spike_event, anomaly_type="unknown")
    with patch("agent.nodes.learning.init_db"):
        with patch("agent.nodes.learning.get_session") as mock_get:
            mock_get.return_value = _mock_db_session()
            result = learning_node(state)

    assert result["stored"] is True


def test_learning_handles_db_error(lag_spike_event, sample_root_cause):
    """DB failure → stored=False, no exception raised."""
    state = _make_state(lag_spike_event, sample_root_cause)
    with patch("agent.nodes.learning.init_db"):
        with patch("agent.nodes.learning.get_session", side_effect=Exception("DB down")):
            result = learning_node(state)

    assert result["stored"] is False
    assert "incident_id" in result


def test_learning_marks_human_approved(
    lag_spike_event, sample_root_cause, sample_remediation_plan, sample_execution_result
):
    """human_decision=APPROVE → human_approved=True in stored row."""
    state = _make_state(
        lag_spike_event, sample_root_cause, sample_remediation_plan,
        sample_execution_result, human_decision="APPROVE"
    )
    with patch("agent.nodes.learning.init_db"):
        with patch("agent.nodes.learning.get_session") as mock_get:
            mock_session = _mock_db_session()
            mock_get.return_value = mock_session
            learning_node(state)

    added_row = mock_session.add.call_args[0][0]
    assert added_row.human_approved is True


def test_learning_unique_incident_ids(lag_spike_event):
    """Each call generates a unique incident_id."""
    state = _make_state(lag_spike_event)
    with patch("agent.nodes.learning.init_db"):
        with patch("agent.nodes.learning.get_session") as mock_get:
            mock_get.return_value = _mock_db_session()
            result1 = learning_node(state)
            result2 = learning_node(state)

    assert result1["incident_id"] != result2["incident_id"]
