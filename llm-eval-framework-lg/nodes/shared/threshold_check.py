"""Top-level graph node: check every metric against its configured threshold.

Metrics where lower is better (false_positive_rate) use ≤ comparison.
All others use ≥. Produces overall PASS/FAIL written to state.
"""

from __future__ import annotations

import logging

from eval_models.schemas import EvalSubResult
from state.eval_state import EvalState

logger = logging.getLogger(__name__)

_LOWER_IS_BETTER = {"false_positive_rate"}


def threshold_check_node(state: EvalState) -> dict:
    """Compare each metric against thresholds from eval_config.yaml."""
    cfg = state["config"]
    results: list[EvalSubResult] = state["eval_results"]

    all_passed = True
    for sub in results:
        thresholds = cfg.rag_thresholds if sub.target == "rag" else cfg.agent_thresholds
        for metric, score in sub.aggregates.items():
            threshold = thresholds.get(metric)
            if threshold is None:
                continue
            if metric in _LOWER_IS_BETTER:
                passed = score <= threshold
            else:
                passed = score >= threshold
            status = "PASS" if passed else "FAIL"
            logger.info("[%s] %s: %.4f (threshold %s) — %s", sub.target, metric, score, threshold, status)
            if not passed:
                all_passed = False

    overall = "PASS" if all_passed else "FAIL"
    logger.info("=== Overall: %s ===", overall)
    return {"overall": overall}
