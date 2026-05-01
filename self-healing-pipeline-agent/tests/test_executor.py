"""
Tests for the Executor Node.
RESTART strategy mocks the Flink client — no real API calls.
"""
import pytest
from unittest.mock import patch, MagicMock
from agent.nodes.executor import executor_node
from agent.tools.flink_client import RestartResult
from models.execution import ExecutionStatus
from models.remediation import FixStrategy, RemediationPlan


def _make_plan(strategy: FixStrategy, risk_score: float = 0.3) -> RemediationPlan:
    return RemediationPlan(
        strategy=strategy,
        description="test plan",
        estimated_impact="test impact",
        risk_score=risk_score,
        rollback_plan="test rollback",
        steps=["step1"],
    )


def _make_state(event, plan, human_decision=None, restart_attempts=0):
    return {
        "event": event,
        "remediation_plan": plan,
        "human_decision": human_decision,
        "restart_attempts": restart_attempts,
        "messages": [],
        "iteration_count": 0,
    }


# ---------------------------------------------------------------------------
# RESTART strategy — Flink client mocked
# ---------------------------------------------------------------------------

def test_restart_strategy_executes(lag_spike_event):
    """RESTART strategy calls Flink client and returns SUCCESS with new_job_id."""
    plan = _make_plan(FixStrategy.RESTART)
    mock_client = MagicMock()
    mock_client.restart_job.return_value = RestartResult(
        action_taken="Restarted job abc on pipeline test",
        new_job_id="new-abc-456",
    )
    with patch("agent.nodes.executor.get_flink_client", return_value=mock_client):
        result = executor_node(_make_state(lag_spike_event, plan))

    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert result["execution_result"].new_job_id == "new-abc-456"
    assert "Restarted" in result["execution_result"].action_taken
    assert result["restart_attempts"] == 1


def test_restart_increments_attempt_counter(lag_spike_event):
    """Each RESTART execution increments restart_attempts."""
    plan = _make_plan(FixStrategy.RESTART)
    mock_client = MagicMock()
    mock_client.restart_job.return_value = RestartResult(
        action_taken="Restarted", new_job_id="new-job-id"
    )
    with patch("agent.nodes.executor.get_flink_client", return_value=mock_client):
        result = executor_node(_make_state(lag_spike_event, plan, restart_attempts=1))
    assert result["restart_attempts"] == 2


def test_restart_exhausted_returns_failed(lag_spike_event):
    """restart_attempts >= MAX → FAILED outcome, no Flink call."""
    plan = _make_plan(FixStrategy.RESTART)
    with patch("agent.nodes.executor.get_flink_client") as mock_get:
        result = executor_node(_make_state(lag_spike_event, plan, restart_attempts=2))
    mock_get.assert_not_called()
    assert result["execution_result"].status == ExecutionStatus.FAILED
    assert "exhausted" in result["execution_result"].action_taken.lower()


# ---------------------------------------------------------------------------
# Other strategies — simulated
# ---------------------------------------------------------------------------

def test_reroute_strategy_executes(lag_spike_event):
    """REROUTE strategy produces SUCCESS result (simulated)."""
    result = executor_node(_make_state(lag_spike_event, _make_plan(FixStrategy.REROUTE, 0.6)))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "Rerouted" in result["execution_result"].action_taken
    assert result["execution_result"].new_job_id is None


def test_savepoint_redeploy_executes(restart_storm_event):
    """SAVEPOINT_REDEPLOY includes savepoint path in action (simulated)."""
    result = executor_node(_make_state(restart_storm_event, _make_plan(FixStrategy.SAVEPOINT_REDEPLOY, 0.8)))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "savepoint" in result["execution_result"].action_taken.lower()


def test_alert_only_logs_no_action(lag_spike_event):
    """ALERT_ONLY → SUCCESS but no destructive action."""
    result = executor_node(_make_state(lag_spike_event, _make_plan(FixStrategy.ALERT_ONLY, 0.1)))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "no automated action" in result["execution_result"].action_taken.lower()


def test_execution_result_has_timestamp(lag_spike_event):
    """ExecutionResult always has a timestamp."""
    result = executor_node(_make_state(lag_spike_event, _make_plan(FixStrategy.REROUTE)))
    assert result["execution_result"].timestamp is not None


# ---------------------------------------------------------------------------
# Human decision
# ---------------------------------------------------------------------------

def test_human_reject_skips_execution(lag_spike_event):
    """Human REJECT → status SKIPPED, no fix applied."""
    result = executor_node(_make_state(lag_spike_event, _make_plan(FixStrategy.REROUTE), human_decision="REJECT"))
    assert result["execution_result"].status == ExecutionStatus.SKIPPED
    assert "rejected" in result["execution_result"].action_taken.lower()
