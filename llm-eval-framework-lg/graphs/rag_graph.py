"""RAG evaluation sub-graph.

Flow:
  load_testset_node
      │
      └── fan_out_questions() ── Send() × N questions (parallel)
              │
          rag_question_node × N   [Annotated[list, add] accumulates enriched]
              │
          ragas_scorer_node  ← runs ragas.evaluate() once all questions are done
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
from nodes.rag.load_testset import load_testset_node
from nodes.rag.rag_question_node import rag_question_node
from nodes.rag.ragas_scorer import ragas_scorer_node
from state.rag_state import RagEvalState


class _RagOutput(TypedDict):
    """Only eval_results is written back to the parent EvalState.

    Without this, LangGraph would try to write every RagEvalState key
    (including config, samples, enriched …) back to the parent, causing
    InvalidUpdateError when the parallel agent sub-graph does the same.
    """
    eval_results: Annotated[list[EvalSubResult], add]


def _fan_out_questions(state: RagEvalState) -> list[Send]:
    """Conditional edge: emit one Send per question for parallel execution."""
    return [
        Send("rag_question_node", {"config": state["config"], "sample": s})
        for s in state["samples"]
    ]


def build_rag_graph() -> StateGraph:
    workflow = StateGraph(RagEvalState, output_schema=_RagOutput)

    workflow.add_node("load_testset_node",  load_testset_node)
    workflow.add_node("rag_question_node",  rag_question_node)
    workflow.add_node("ragas_scorer_node",  ragas_scorer_node)

    workflow.set_entry_point("load_testset_node")
    workflow.add_conditional_edges("load_testset_node", _fan_out_questions, ["rag_question_node"])
    workflow.add_edge("rag_question_node", "ragas_scorer_node")
    workflow.add_edge("ragas_scorer_node", END)

    return workflow
