"""Agent sub-graph node: average pr_scores into final aggregates and emit EvalSubResult.

Runs once after all parallel score_pr_node calls have completed and the
pr_scores reducer list is fully populated.

Also writes eval_results so the result propagates back to the top-level
EvalState via key-name matching between sub-graph and parent state.
"""

from __future__ import annotations

import logging

from eval_models.schemas import AgentPRScore, EvalSubResult
from state.agent_state import AgentEvalState

logger = logging.getLogger(__name__)


def aggregate_agent_node(state: AgentEvalState) -> dict:
    """Average per-PR scores and emit EvalSubResult for the top-level graph."""
    pr_scores: list[AgentPRScore] = state["pr_scores"]

    def _avg(attr: str) -> float:
        values = [getattr(s, attr) for s in pr_scores]
        return round(sum(values) / len(values), 4) if values else 0.0

    aggregates = {
        "bug_recall":          _avg("bug_recall"),
        "false_positive_rate": _avg("false_positive_rate"),
        "comment_quality":     _avg("comment_quality"),
    }

    sub_result = EvalSubResult(target="agent", aggregates=aggregates, tokens_used=0)
    logger.info("Agent aggregates: %s", aggregates)

    return {
        "aggregates": aggregates,
        "eval_results": [sub_result],
    }
