"""
Tests for the Diagnosis Node.
All LLM calls are mocked — no real API calls.
"""
import pytest
from unittest.mock import patch, MagicMock
from agent.nodes.diagnosis import diagnosis_node, _query_similar_incidents
from models.diagnosis import RootCause


def _make_state(event, anomaly_type="lag_spike", severity="critical", combination="lag_spike_high_cpu"):
    return {
        "event": event,
        "anomaly_type": anomaly_type,
        "severity": severity,
        "combination": combination,
        "messages": [],
        "iteration_count": 0,
    }


def _mock_root_cause():
    return RootCause(
        primary_cause="Consumer lag caused by upstream throughput spike exceeding partition capacity",
        contributing_factors=["CPU at 94%", "Lag growing at 125k messages/min"],
        confidence=0.87,
        evidence=["current_lag 5.7x threshold", "cpu_pct > 80%"],
        recommended_action="Reroute traffic — restart ruled out due to high CPU",
    )


def _patch_diagnosis_chain(mock_root_cause):
    """Helper: patch ChatOpenAI and DIAGNOSIS_PROMPT to return mock_root_cause."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = mock_root_cause
    prompt_patch = patch("agent.nodes.diagnosis.DIAGNOSIS_PROMPT")
    llm_patch = patch("agent.nodes.diagnosis.ChatOpenAI")
    return prompt_patch, llm_patch, mock_chain


# ---------------------------------------------------------------------------
# Diagnosis Node output tests
# ---------------------------------------------------------------------------

def test_diagnosis_returns_root_cause(lag_spike_event):
    """Diagnosis node returns a RootCause object."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _mock_root_cause()

    with patch("agent.nodes.diagnosis.ChatOpenAI"):
        with patch("agent.nodes.diagnosis.DIAGNOSIS_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            with patch("agent.nodes.diagnosis._query_similar_incidents", return_value=[]):
                result = diagnosis_node(_make_state(lag_spike_event))

    assert "root_cause" in result
    assert isinstance(result["root_cause"], RootCause)


def test_diagnosis_root_cause_has_confidence(lag_spike_event):
    """RootCause confidence is between 0 and 1."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _mock_root_cause()

    with patch("agent.nodes.diagnosis.ChatOpenAI"):
        with patch("agent.nodes.diagnosis.DIAGNOSIS_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            with patch("agent.nodes.diagnosis._query_similar_incidents", return_value=[]):
                result = diagnosis_node(_make_state(lag_spike_event))

    assert 0.0 <= result["root_cause"].confidence <= 1.0


def test_similar_incidents_included_in_state(lag_spike_event):
    """similar_incidents key is always present in result."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _mock_root_cause()

    with patch("agent.nodes.diagnosis.ChatOpenAI"):
        with patch("agent.nodes.diagnosis.DIAGNOSIS_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            with patch("agent.nodes.diagnosis._query_similar_incidents", return_value=[]):
                result = diagnosis_node(_make_state(lag_spike_event))

    assert "similar_incidents" in result
    assert isinstance(result["similar_incidents"], list)


# ---------------------------------------------------------------------------
# Memory query tests
# ---------------------------------------------------------------------------

def test_query_similar_incidents_returns_empty_on_no_history():
    """Returns empty list when no incidents exist yet."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter.return_value \
        .order_by.return_value.limit.return_value.all.return_value = []

    with patch("agent.nodes.diagnosis.get_session", return_value=mock_session):
        result = _query_similar_incidents("pipeline-01", "lag_spike")

    assert result == []


def test_query_similar_incidents_handles_db_error():
    """Returns empty list gracefully if DB is unavailable."""
    with patch("agent.nodes.diagnosis.get_session", side_effect=Exception("DB error")):
        result = _query_similar_incidents("pipeline-01", "lag_spike")

    assert result == []
