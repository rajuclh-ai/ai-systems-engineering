"""Agent sub-graph state.

pr_scores uses Annotated[list, add] so each parallel score_pr_node
invocation appends its AgentPRScore independently.
aggregate_agent_node reads the full pr_scores list once all PRs are scored.

eval_results mirrors the parent EvalState key — the sub-graph's final node
writes here, and LangGraph propagates it back to the parent via key-name matching.
"""

from __future__ import annotations

from operator import add
from typing import Annotated

from typing_extensions import TypedDict

from eval_models.schemas import AgentPRScore, AgentSample, EvalSubResult


class AgentEvalState(TypedDict):
    config: object                                        # EvalConfig
    samples: list[AgentSample]
    pr_scores: Annotated[list[AgentPRScore], add]        # reducer — one per PR
    aggregates: dict[str, float]
    eval_results: Annotated[list[EvalSubResult], add]    # written at end → propagates to parent
