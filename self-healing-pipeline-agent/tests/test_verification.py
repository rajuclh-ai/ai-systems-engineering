"""
Tests for the Verification Node.
Flink client mocked — no real polling.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from agent.nodes.verification import verification_node
from models.execution import ExecutionResult, ExecutionStatus
from models.remediation import RemediationPlan, FixStrategy


def _make_plan(strategy: FixStrategy) -> RemediationPlan:
    return RemediationPlan(
        strategy=strategy,
        description="test",
        estimated_impact="test",
        risk_score=0.3,
        rollback_plan="test",
        steps=["step"],
    )


def _make_execution_result(new_job_id: str | None = "new-job-123") -> ExecutionResult:
    return ExecutionResult(
        strategy_executed="restart",
        status=ExecutionStatus.SUCCESS,
        action_taken="Restarted job",
        timestamp=datetime(2026, 5, 1, 10, 0, 0),
        new_job_id=new_job_id,
    )


def _make_state(plan, execution_result, restart_attempts=0):
    return {
        "remediation_plan": plan,
        "execution_result": execution_result,
        "restart_attempts": restart_attempts,
        "messages": [],
        "iteration_count": 0,
    }


# ---------------------------------------------------------------------------
# Non-RESTART strategies — skipped
# ---------------------------------------------------------------------------

def test_non_restart_strategy_skipped(lag_spike_event):
    """REROUTE strategy → verification skipped."""
    state = _make_state(_make_plan(FixStrategy.REROUTE), _make_execution_result())
    result = verification_node(state)
    assert result["verification_status"] == "skipped"


def test_no_new_job_id_skipped():
    """No new_job_id in execution_result → skipped."""
    state = _make_state(_make_plan(FixStrategy.RESTART), _make_execution_result(new_job_id=None))
    result = verification_node(state)
    assert result["verification_status"] == "skipped"


# ---------------------------------------------------------------------------
# RESTART strategy — poll outcomes
# ---------------------------------------------------------------------------

def test_job_running_returns_verified():
    """Job reaches RUNNING → verified."""
    mock_client = MagicMock()
    mock_client.get_job_status.return_value = "RUNNING"
    state = _make_state(_make_plan(FixStrategy.RESTART), _make_execution_result())

    with patch("agent.nodes.verification.get_flink_client", return_value=mock_client):
        result = verification_node(state)

    assert result["verification_status"] == "verified"


def test_job_failed_returns_failed():
    """Job reaches FAILED terminal state → verification failed."""
    mock_client = MagicMock()
    mock_client.get_job_status.return_value = "FAILED"
    state = _make_state(_make_plan(FixStrategy.RESTART), _make_execution_result())

    with patch("agent.nodes.verification.get_flink_client", return_value=mock_client):
        result = verification_node(state)

    assert result["verification_status"] == "failed"


def test_job_canceled_returns_failed():
    """Job reaches CANCELED terminal state → verification failed."""
    mock_client = MagicMock()
    mock_client.get_job_status.return_value = "CANCELED"
    state = _make_state(_make_plan(FixStrategy.RESTART), _make_execution_result())

    with patch("agent.nodes.verification.get_flink_client", return_value=mock_client):
        result = verification_node(state)

    assert result["verification_status"] == "failed"


def test_poll_error_continues_until_timeout():
    """Polling errors are swallowed — keeps retrying until timeout."""
    mock_client = MagicMock()
    mock_client.get_job_status.side_effect = Exception("connection refused")
    state = _make_state(_make_plan(FixStrategy.RESTART), _make_execution_result())

    with patch("agent.nodes.verification.get_flink_client", return_value=mock_client), \
         patch("agent.nodes.verification.POLL_TIMEOUT_SECONDS", 0), \
         patch("agent.nodes.verification.POLL_INTERVAL_SECONDS", 1):
        result = verification_node(state)

    assert result["verification_status"] == "failed"


# ---------------------------------------------------------------------------
# Routing after verification
# ---------------------------------------------------------------------------

def test_route_verified_goes_to_learning():
    """verified → learning."""
    from agent.graph import route_after_verification
    state = {"verification_status": "verified", "restart_attempts": 1}
    assert route_after_verification(state) == "learning"


def test_route_skipped_goes_to_learning():
    """skipped → learning."""
    from agent.graph import route_after_verification
    state = {"verification_status": "skipped", "restart_attempts": 0}
    assert route_after_verification(state) == "learning"


def test_route_failed_with_attempts_remaining_goes_to_executor():
    """failed + attempts < MAX → retry executor."""
    from agent.graph import route_after_verification
    state = {"verification_status": "failed", "restart_attempts": 1}
    assert route_after_verification(state) == "executor"


def test_route_failed_attempts_exhausted_goes_to_learning():
    """failed + attempts >= MAX → learning (exhausted)."""
    from agent.graph import route_after_verification
    state = {"verification_status": "failed", "restart_attempts": 2}
    assert route_after_verification(state) == "learning"
