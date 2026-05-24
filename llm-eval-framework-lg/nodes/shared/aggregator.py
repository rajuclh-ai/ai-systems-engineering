"""Top-level graph node: merge EvalSubResults from both sub-graphs.

Runs once after both rag_eval and agent_eval sub-graphs have completed
and their results have been accumulated in the eval_results reducer list.
"""

from __future__ import annotations

import logging

from eval_models.schemas import EvalSubResult
from state.eval_state import EvalState

logger = logging.getLogger(__name__)

# GPT-4o-mini cost per token (rough estimate for cost_usd field)
_COST_PER_TOKEN = 0.00000015


def aggregator_node(state: EvalState) -> dict:
    """Merge sub-results, compute total tokens and estimated cost."""
    results: list[EvalSubResult] = state["eval_results"]

    total_tokens = sum(r.tokens_used for r in results)
    cost_usd = round(total_tokens * _COST_PER_TOKEN, 6)

    logger.info(
        "Merged %d sub-results | tokens=%d | cost=$%.4f",
        len(results), total_tokens, cost_usd,
    )
    return {
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    }
