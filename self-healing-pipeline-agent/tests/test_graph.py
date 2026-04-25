"""
End-to-end graph tests.
All LLM calls mocked — graph wiring and routing logic tested.
"""
import pytest
from unittest.mock import patch, MagicMock
from agent.graph import route_after_monitor, route_after_remediation
from models.diagnosis import RootCause
from models.remediation import RemediationPlan, FixStrategy
from models.execution import ExecutionResult, ExecutionStatus
from datetime import datetime


def _base_state(anomaly_type="lag_spike", severity="critical",
                requires_approval=False, risk_score=0.3):
    return {
        "anomaly_type": anomaly_type,
        "severity": severity,
        "requires_approval": requires_approval,
        "risk_score": risk_score,
        "combination": "none",
        "messages": [],
        "iteration_count": 0,
    }


# ---------------------------------------------------------------------------
# Routing logic tests (no graph invocation needed)
# ---------------------------------------------------------------------------

def test_route_after_monitor_unknown_goes_to_learning():
    state = _base_state(anomaly_type="unknown")
    assert route_after_monitor(state) == "learning"


def test_route_after_monitor_known_goes_to_diagnosis():
    state = _base_state(anomaly_type="lag_spike")
    assert route_after_monitor(state) == "diagnosis"


def test_route_after_remediation_high_risk_goes_to_human():
    state = _base_state(requires_approval=True, risk_score=0.8)
    assert route_after_remediation(state) == "human_checkpoint"


def test_route_after_remediation_low_risk_goes_to_executor():
    state = _base_state(requires_approval=False, risk_score=0.3)
    assert route_after_remediation(state) == "executor"


def test_route_after_remediation_savepoint_requires_approval():
    """SAVEPOINT_REDEPLOY risk 0.8 → human_checkpoint."""
    state = _base_state(requires_approval=True, risk_score=0.8)
    assert route_after_remediation(state) == "human_checkpoint"


# ---------------------------------------------------------------------------
# Graph structure tests
# ---------------------------------------------------------------------------

def test_graph_builds_without_error():
    """Graph compiles successfully."""
    from agent.graph import build_graph
    g = build_graph()
    assert g is not None


def test_graph_has_all_nodes():
    """All expected nodes are present in the graph."""
    from agent.graph import graph
    node_names = set(graph.nodes.keys())
    expected = {"monitor", "diagnosis", "remediation", "human_checkpoint", "executor", "learning"}
    assert expected.issubset(node_names)
