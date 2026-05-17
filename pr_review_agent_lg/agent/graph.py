"""
LangGraph StateGraph definition.
Wires all nodes with Send() parallel fan-out for specialist agents.

Graph flow:
  fetcher → [Send() fan-out] → security_node ─┐
                             → logic_node     ─┼─ (parallel) → critic → post_comment → learning → END
                             → style_node     ─┘
"""
import logging
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from agent.state import ReviewState
from agent.checkpointer import checkpointer
from agent.nodes.fetcher import fetcher_node
from agent.nodes.security import security_node
from agent.nodes.logic import logic_node
from agent.nodes.style import style_node
from agent.nodes.critic import critic_node
from agent.nodes.post_comment import post_comment_node
from agent.nodes.learning import learning_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_to_specialists(state: ReviewState) -> list[Send]:
    """
    Fan out to all three specialist nodes in parallel via Send().
    Each specialist receives the full state and appends to agent_results
    via the Annotated[list[AgentResult], add] reducer.
    """
    diff = state.get("diff", "")
    if not diff:
        logger.warning("[GRAPH] no diff in state — skipping specialists")
        return [Send("critic", state)]

    return [
        Send("security_node", state),
        Send("logic_node",    state),
        Send("style_node",    state),
    ]


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    workflow = StateGraph(ReviewState)

    # Add nodes
    workflow.add_node("fetcher",       fetcher_node)
    workflow.add_node("security_node", security_node)
    workflow.add_node("logic_node",    logic_node)
    workflow.add_node("style_node",    style_node)
    workflow.add_node("critic",        critic_node)
    workflow.add_node("post_comment",  post_comment_node)
    workflow.add_node("learning",      learning_node)

    # Entry point
    workflow.set_entry_point("fetcher")

    # fetcher → parallel fan-out via Send()
    workflow.add_conditional_edges(
        "fetcher",
        route_to_specialists,
        ["security_node", "logic_node", "style_node", "critic"],
    )

    # Each specialist feeds into critic (LangGraph waits for all Send() branches)
    workflow.add_edge("security_node", "critic")
    workflow.add_edge("logic_node",    "critic")
    workflow.add_edge("style_node",    "critic")

    # critic → post_comment → learning → END
    workflow.add_edge("critic",       "post_comment")
    workflow.add_edge("post_comment", "learning")
    workflow.add_edge("learning",     END)

    return workflow.compile(checkpointer=checkpointer)


# Module-level graph instance
graph = build_graph()
