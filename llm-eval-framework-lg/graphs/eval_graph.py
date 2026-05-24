"""Top-level EvalGraph — orchestrates the RAG and Agent sub-graphs in parallel.

Flow:
  route_to_evaluators()
      │
      ├── Send("rag_eval",   state)  ──┐  parallel
      └── Send("agent_eval", state)  ──┤
                                       │
                    [Annotated[list, add] accumulates EvalSubResults]
                                       │
                              aggregator_node
                                       │
                            threshold_check_node
                                       │
                               reporter_node
                                       │
                                      END

route_to_evaluators respects --target so only the requested sub-graph(s) run.
"""

from __future__ import annotations

from langgraph.types import Send
from langgraph.graph import END, StateGraph

from graphs.agent_graph import build_agent_graph
from graphs.rag_graph import build_rag_graph
from nodes.shared.aggregator import aggregator_node
from nodes.shared.reporter import reporter_node
from nodes.shared.threshold_check import threshold_check_node
from state.eval_state import EvalState


def _route_to_evaluators(state: EvalState) -> list[Send]:
    """Fan-out: send to RAG and/or Agent sub-graphs based on --target."""
    target = state["target"]
    sends = []
    if target in ("all", "rag"):
        sends.append(Send("rag_eval", state))
    if target in ("all", "agent"):
        sends.append(Send("agent_eval", state))
    return sends


def build_eval_graph() -> StateGraph:
    rag_subgraph   = build_rag_graph().compile()
    agent_subgraph = build_agent_graph().compile()

    workflow = StateGraph(EvalState)

    # Sub-graphs registered as nodes
    workflow.add_node("rag_eval",   rag_subgraph)
    workflow.add_node("agent_eval", agent_subgraph)

    # Shared post-processing nodes
    workflow.add_node("aggregator_node",      aggregator_node)
    workflow.add_node("threshold_check_node", threshold_check_node)
    workflow.add_node("reporter_node",        reporter_node)

    # Entry: fan-out to sub-graphs
    workflow.set_conditional_entry_point(_route_to_evaluators, ["rag_eval", "agent_eval"])

    # Both sub-graphs converge at aggregator
    workflow.add_edge("rag_eval",   "aggregator_node")
    workflow.add_edge("agent_eval", "aggregator_node")

    workflow.add_edge("aggregator_node",      "threshold_check_node")
    workflow.add_edge("threshold_check_node", "reporter_node")
    workflow.add_edge("reporter_node",        END)

    return workflow
