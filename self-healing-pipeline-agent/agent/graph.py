"""
LangGraph StateGraph definition.
Wires all nodes with conditional edges.
Compiles with MemorySaver for durable state + HITL support.

Graph flow:
  monitor → diagnosis → remediation → [human_checkpoint?] → executor
         → verification → [retry executor if failed?] → learning → END
"""
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.checkpointer import checkpointer
from agent.nodes.monitor import monitor_node
from agent.nodes.diagnosis import diagnosis_node
from agent.nodes.remediation import remediation_node
from agent.nodes.executor import executor_node, MAX_RESTART_ATTEMPTS
from agent.nodes.verification import verification_node
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


def route_after_verification(state: AgentState) -> str:
    """
    verified  → learning (success path)
    skipped   → learning (non-RESTART strategies pass through)
    failed    → executor again if attempts < MAX, else learning (exhausted)
    """
    verification_status = state.get("verification_status", "skipped")
    restart_attempts = state.get("restart_attempts", 0)

    if verification_status == "verified":
        return "learning"

    if verification_status == "skipped":
        return "learning"

    # verification failed — retry if attempts remaining
    if restart_attempts < MAX_RESTART_ATTEMPTS:
        return "executor"

    # attempts exhausted — go to learning with FAILED outcome
    return "learning"


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
    workflow.add_node("verification", verification_node)
    workflow.add_node("learning", learning_node)

    # Entry point
    workflow.set_entry_point("monitor")

    # monitor → diagnosis | learning
    workflow.add_conditional_edges(
        "monitor",
        route_after_monitor,
        {"diagnosis": "diagnosis", "learning": "learning"},
    )

    # diagnosis → remediation (fixed)
    workflow.add_edge("diagnosis", "remediation")

    # remediation → human_checkpoint | executor
    workflow.add_conditional_edges(
        "remediation",
        route_after_remediation,
        {"human_checkpoint": "human_checkpoint", "executor": "executor"},
    )

    # human_checkpoint → executor (fixed — resumes after APPROVE/REJECT)
    workflow.add_edge("human_checkpoint", "executor")

    # executor → verification (fixed)
    workflow.add_edge("executor", "verification")

    # verification → executor (retry) | learning (success/exhausted)
    workflow.add_conditional_edges(
        "verification",
        route_after_verification,
        {"executor": "executor", "learning": "learning"},
    )

    # learning → END (fixed)
    workflow.add_edge("learning", END)

    # Compile with checkpointer — interrupt before human_checkpoint when HITL needed
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_checkpoint"],
    )


# Module-level graph instance
graph = build_graph()
