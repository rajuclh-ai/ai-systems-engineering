"""
LangGraph StateGraph definition.
Wires all nodes with conditional edges.
Compiles with MemorySaver for durable state + HITL support.
"""
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.checkpointer import checkpointer
from agent.nodes.monitor import monitor_node
from agent.nodes.diagnosis import diagnosis_node
from agent.nodes.remediation import remediation_node
from agent.nodes.executor import executor_node
from agent.nodes.learning import learning_node


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_monitor(state: AgentState) -> str:
    """
    UNKNOWN anomaly → skip to learning (log and move on).
    Known anomaly → proceed to diagnosis.
    """
    if state.get("anomaly_type") == "unknown":
        return "learning"
    return "diagnosis"


def route_after_remediation(state: AgentState) -> str:
    """
    risk_score > 0.7 → pause at human checkpoint.
    risk_score ≤ 0.7 → go straight to executor.
    """
    if state.get("requires_approval"):
        return "human_checkpoint"
    return "executor"


def human_checkpoint_node(state: AgentState) -> dict:
    """
    Placeholder node where LangGraph interrupts for human approval.
    The graph pauses here — resumed via POST /approval/{thread_id}.
    Human decision is injected into state via update_state() before resume.
    """
    return {}


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("monitor", monitor_node)
    workflow.add_node("diagnosis", diagnosis_node)
    workflow.add_node("remediation", remediation_node)
    workflow.add_node("human_checkpoint", human_checkpoint_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("learning", learning_node)

    # Entry point
    workflow.set_entry_point("monitor")

    # Routing after monitor
    workflow.add_conditional_edges(
        "monitor",
        route_after_monitor,
        {"diagnosis": "diagnosis", "learning": "learning"},
    )

    # Fixed edge: diagnosis → remediation
    workflow.add_edge("diagnosis", "remediation")

    # Routing after remediation
    workflow.add_conditional_edges(
        "remediation",
        route_after_remediation,
        {"human_checkpoint": "human_checkpoint", "executor": "executor"},
    )

    # After human checkpoint → executor
    workflow.add_edge("human_checkpoint", "executor")

    # Fixed edges to end
    workflow.add_edge("executor", "learning")
    workflow.add_edge("learning", END)

    # Compile with checkpointer — interrupt before executor when HITL needed
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_checkpoint"],
    )


# Module-level graph instance
graph = build_graph()
