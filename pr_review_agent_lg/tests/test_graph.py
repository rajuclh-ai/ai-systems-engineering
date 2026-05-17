"""
Tests for the LangGraph StateGraph wiring.
Verifies Send() fan-out, reducer merging, and graph compilation.
"""
import pytest
from unittest.mock import patch, MagicMock
from langgraph.types import Send
from agent.graph import build_graph, route_to_specialists
from agent.state import ReviewState
from models.schemas import AgentResult, Finding


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

def test_graph_compiles():
    """Graph builds without errors and contains all expected nodes."""
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    expected = {"fetcher", "security_node", "logic_node", "style_node",
                "critic", "post_comment", "learning"}
    assert expected.issubset(node_names)


# ---------------------------------------------------------------------------
# route_to_specialists
# ---------------------------------------------------------------------------

def test_route_to_specialists_returns_three_sends(sample_diff):
    state: ReviewState = {
        "pr_url": None,
        "diff": sample_diff,
        "agent_results": [],
        "critic_report": None,
        "verdict": None,
        "review_id": None,
        "iteration_count": 0,
    }
    sends = route_to_specialists(state)
    assert len(sends) == 3
    nodes = {s.node for s in sends}
    assert nodes == {"security_node", "logic_node", "style_node"}


def test_route_to_specialists_no_diff_goes_to_critic():
    """If diff is missing, route directly to critic (skip specialists)."""
    state: ReviewState = {
        "pr_url": None,
        "diff": "",
        "agent_results": [],
        "critic_report": None,
        "verdict": None,
        "review_id": None,
        "iteration_count": 0,
    }
    sends = route_to_specialists(state)
    assert len(sends) == 1
    assert sends[0].node == "critic"


# ---------------------------------------------------------------------------
# Annotated[list, add] reducer behaviour
# ---------------------------------------------------------------------------

def test_agent_results_reducer_merges_all_three(three_agent_results):
    """
    Verify the reducer semantics: starting from [] and adding one result at a time
    produces the correct merged list — same behaviour LangGraph applies during Send() fan-out.
    """
    from operator import add
    accumulated = []
    for result in three_agent_results:
        accumulated = add(accumulated, [result])

    assert len(accumulated) == 3
    agents = {r.agent for r in accumulated}
    assert agents == {"security", "logic", "style"}


def test_agent_results_reducer_preserves_findings(three_agent_results):
    """Each specialist's findings are preserved after merging."""
    from operator import add
    accumulated = []
    for result in three_agent_results:
        accumulated = add(accumulated, [result])

    security = next(r for r in accumulated if r.agent == "security")
    assert len(security.findings) == 1
    assert security.findings[0].severity == "HIGH"
