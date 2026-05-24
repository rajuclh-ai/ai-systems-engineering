"""Agent evaluation sub-graph.

Flow:
  load_testset_node
      │
      └── fan_out_prs() ── Send() × 7 PRs (parallel)
              │
          score_pr_node × 7   [Annotated[list, add] accumulates pr_scores]
              │
          aggregate_agent_node  ← averages pr_scores, emits EvalSubResult
              │
             END

The sub-graph is compiled and registered as a node in the top-level EvalGraph.
Its final node writes eval_results, which propagates back to the parent state
via key-name matching.
"""

from __future__ import annotations

from operator import add
from typing import Annotated

from langgraph.types import Send
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from eval_models.schemas import EvalSubResult
from nodes.agent.aggregate_agent import aggregate_agent_node
from nodes.agent.load_testset import load_testset_node
from nodes.agent.score_pr_node import score_pr_node
from state.agent_state import AgentEvalState


class _AgentOutput(TypedDict):
    """Only eval_results is written back to the parent EvalState.

    Without this, LangGraph would try to write every AgentEvalState key
    (including config, samples, pr_scores …) back to the parent, causing
    InvalidUpdateError when the parallel RAG sub-graph does the same.
    """
    eval_results: Annotated[list[EvalSubResult], add]


def _fan_out_prs(state: AgentEvalState) -> list[Send]:
    """Conditional edge: emit one Send per PR for parallel execution."""
    return [
        Send("score_pr_node", {"config": state["config"], "sample": s})
        for s in state["samples"]
    ]


def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentEvalState, output_schema=_AgentOutput)

    workflow.add_node("load_testset_node",    load_testset_node)
    workflow.add_node("score_pr_node",        score_pr_node)
    workflow.add_node("aggregate_agent_node", aggregate_agent_node)

    workflow.set_entry_point("load_testset_node")
    workflow.add_conditional_edges("load_testset_node", _fan_out_prs, ["score_pr_node"])
    workflow.add_edge("score_pr_node",        "aggregate_agent_node")
    workflow.add_edge("aggregate_agent_node", END)

    return workflow
