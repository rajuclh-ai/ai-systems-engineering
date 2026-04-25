"""
Tests for the Executor Node.
No LLM calls — pure simulation logic.
"""
import pytest
from agent.nodes.executor import executor_node
from models.execution import ExecutionStatus
from models.remediation import FixStrategy


def _make_state(event, plan, human_decision=None):
    return {
        "event": event,
        "remediation_plan": plan,
        "human_decision": human_decision,
        "messages": [],
        "iteration_count": 0,
    }


def test_restart_strategy_executes(lag_spike_event, sample_remediation_plan):
    """RESTART strategy produces SUCCESS result."""
    from models.remediation import RemediationPlan
    plan = RemediationPlan(
        strategy=FixStrategy.RESTART,
        description="Restart the job",
        estimated_impact="Job recovers",
        risk_score=0.3,
        rollback_plan="Restore from checkpoint",
        steps=["Restart job"],
    )
    result = executor_node(_make_state(lag_spike_event, plan))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "Restarted" in result["execution_result"].action_taken


def test_reroute_strategy_executes(lag_spike_event):
    """REROUTE strategy produces SUCCESS result."""
    from models.remediation import RemediationPlan
    plan = RemediationPlan(
        strategy=FixStrategy.REROUTE,
        description="Reroute traffic",
        estimated_impact="Lag stabilises",
        risk_score=0.6,
        rollback_plan="Restore routing",
        steps=["Reroute"],
    )
    result = executor_node(_make_state(lag_spike_event, plan))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "Rerouted" in result["execution_result"].action_taken


def test_savepoint_redeploy_executes(restart_storm_event):
    """SAVEPOINT_REDEPLOY includes savepoint path in action."""
    from models.remediation import RemediationPlan
    plan = RemediationPlan(
        strategy=FixStrategy.SAVEPOINT_REDEPLOY,
        description="Redeploy from savepoint",
        estimated_impact="Job recovers cleanly",
        risk_score=0.8,
        rollback_plan="Rollback to previous savepoint",
        steps=["Redeploy"],
    )
    result = executor_node(_make_state(restart_storm_event, plan))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "savepoint" in result["execution_result"].action_taken.lower()


def test_human_reject_skips_execution(lag_spike_event, sample_remediation_plan):
    """Human REJECT → status SKIPPED, no fix applied."""
    result = executor_node(_make_state(lag_spike_event, sample_remediation_plan, human_decision="REJECT"))
    assert result["execution_result"].status == ExecutionStatus.SKIPPED
    assert "rejected" in result["execution_result"].action_taken.lower()


def test_alert_only_logs_no_action(lag_spike_event):
    """ALERT_ONLY → SUCCESS but no destructive action."""
    from models.remediation import RemediationPlan
    plan = RemediationPlan(
        strategy=FixStrategy.ALERT_ONLY,
        description="Alert only",
        estimated_impact="No change",
        risk_score=0.1,
        rollback_plan="N/A",
        steps=["Raise alert"],
    )
    result = executor_node(_make_state(lag_spike_event, plan))
    assert result["execution_result"].status == ExecutionStatus.SUCCESS
    assert "no automated action" in result["execution_result"].action_taken.lower()


def test_execution_result_has_timestamp(lag_spike_event, sample_remediation_plan):
    """ExecutionResult always has a timestamp."""
    result = executor_node(_make_state(lag_spike_event, sample_remediation_plan))
    assert result["execution_result"].timestamp is not None
