"""
Tests for the Remediation Node.
All LLM calls mocked. Focus on strategy mapping and risk score logic.
"""
import pytest
from unittest.mock import patch, MagicMock
from agent.nodes.remediation import (
    remediation_node, _get_allowed_strategies, RISK_SCORES, RISK_THRESHOLD
)
from models.remediation import FixStrategy, RemediationPlan


def _make_state(event, anomaly_type, severity, combination, root_cause):
    return {
        "event": event,
        "anomaly_type": anomaly_type,
        "severity": severity,
        "combination": combination,
        "root_cause": root_cause,
        "messages": [],
        "iteration_count": 0,
    }


def _mock_plan(strategy: FixStrategy) -> RemediationPlan:
    return RemediationPlan(
        strategy=strategy,
        description="Test description",
        estimated_impact="Test impact",
        risk_score=RISK_SCORES[strategy],
        rollback_plan="Reverse the action",
        steps=["Step 1", "Step 2"],
    )


# ---------------------------------------------------------------------------
# Strategy mapping tests (no LLM needed)
# ---------------------------------------------------------------------------

def test_lag_spike_allows_restart_and_reroute():
    strategies = _get_allowed_strategies("lag_spike", "none")
    assert FixStrategy.RESTART in strategies
    assert FixStrategy.REROUTE in strategies


def test_lag_spike_high_cpu_only_allows_reroute():
    """RESTART ruled out when CPU is high — only REROUTE allowed."""
    strategies = _get_allowed_strategies("lag_spike", "lag_spike_high_cpu")
    assert FixStrategy.REROUTE in strategies
    assert FixStrategy.RESTART not in strategies


def test_restart_storm_allows_savepoint_redeploy():
    strategies = _get_allowed_strategies("restart_storm", "none")
    assert FixStrategy.SAVEPOINT_REDEPLOY in strategies


def test_schema_drift_allows_schema_patch():
    strategies = _get_allowed_strategies("schema_drift", "none")
    assert FixStrategy.SCHEMA_PATCH in strategies


def test_unknown_only_allows_alert_only():
    strategies = _get_allowed_strategies("unknown", "none")
    assert strategies == [FixStrategy.ALERT_ONLY]


# ---------------------------------------------------------------------------
# Risk score tests (no LLM needed)
# ---------------------------------------------------------------------------

def test_savepoint_redeploy_risk_above_threshold():
    """SAVEPOINT_REDEPLOY risk 0.8 > 0.7 → must trigger HITL."""
    assert RISK_SCORES[FixStrategy.SAVEPOINT_REDEPLOY] > RISK_THRESHOLD


def test_restart_risk_below_threshold():
    """RESTART risk 0.3 < 0.7 → no HITL needed."""
    assert RISK_SCORES[FixStrategy.RESTART] < RISK_THRESHOLD


def test_alert_only_lowest_risk():
    assert RISK_SCORES[FixStrategy.ALERT_ONLY] == 0.1


# ---------------------------------------------------------------------------
# Remediation Node output tests (LLM mocked)
# ---------------------------------------------------------------------------

def test_remediation_sets_requires_approval_true_for_high_risk(
    lag_spike_event, sample_root_cause
):
    """SAVEPOINT_REDEPLOY risk 0.8 → requires_approval=True."""
    with patch("agent.nodes.remediation.ChatOpenAI") as mock_cls:
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = _mock_plan(FixStrategy.SAVEPOINT_REDEPLOY)
        with patch("agent.nodes.remediation.REMEDIATION_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            state = _make_state(lag_spike_event, "restart_storm", "critical", "none", sample_root_cause)
            result = remediation_node(state)

    assert result["requires_approval"] is True
    assert result["risk_score"] == 0.8


def test_remediation_sets_requires_approval_false_for_low_risk(
    lag_spike_event, sample_root_cause
):
    """RESTART risk 0.3 → requires_approval=False."""
    with patch("agent.nodes.remediation.ChatOpenAI") as mock_cls:
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = _mock_plan(FixStrategy.RESTART)
        with patch("agent.nodes.remediation.REMEDIATION_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            state = _make_state(lag_spike_event, "lag_spike", "high", "none", sample_root_cause)
            result = remediation_node(state)

    assert result["requires_approval"] is False
    assert result["risk_score"] == 0.3


def test_remediation_returns_plan(lag_spike_event, sample_root_cause):
    """Remediation node returns a RemediationPlan."""
    with patch("agent.nodes.remediation.ChatOpenAI"):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = _mock_plan(FixStrategy.REROUTE)
        with patch("agent.nodes.remediation.REMEDIATION_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            state = _make_state(lag_spike_event, "lag_spike", "critical", "lag_spike_high_cpu", sample_root_cause)
            result = remediation_node(state)

    assert "remediation_plan" in result
    assert isinstance(result["remediation_plan"], RemediationPlan)
