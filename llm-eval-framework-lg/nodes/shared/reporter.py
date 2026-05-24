"""Top-level graph node: write JSON result, append to JSONL history, generate markdown report.

Output format is identical to v1 so existing CI integrations and history
files remain compatible.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from eval_models.schemas import EvalSubResult
from state.eval_state import EvalState

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RESULTS_PATH  = BASE_DIR / "outputs" / "results"
HISTORY_PATH  = BASE_DIR / "outputs" / "history" / "metrics_log.jsonl"
REPORTS_PATH  = BASE_DIR / "outputs" / "reports"

_LOWER_IS_BETTER = {"false_positive_rate"}


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def reporter_node(state: EvalState) -> dict:
    """Persist results and print the markdown report to stdout."""
    cfg         = state["config"]
    run_id      = state["run_id"]
    overall     = state["overall"]
    results     = state["eval_results"]
    total_tokens = state["total_tokens"]
    cost_usd    = state["cost_usd"]

    rag_result   = next((r for r in results if r.target == "rag"),   None)
    agent_result = next((r for r in results if r.target == "agent"), None)

    rag_agg   = rag_result.aggregates   if rag_result   else {}
    agent_agg = agent_result.aggregates if agent_result else {}

    # --- JSON result ---
    payload = _build_payload(
        run_id, cfg.model, rag_agg, cfg.rag_thresholds,
        agent_agg, cfg.agent_thresholds, overall, cost_usd, total_tokens,
    )
    _save_json(run_id, payload)

    # --- JSONL history ---
    _append_history(run_id, cfg.model, rag_agg, agent_agg, overall, cost_usd, total_tokens)

    # --- Markdown report ---
    report = _generate_markdown(
        run_id, cfg.model, rag_agg, cfg.rag_thresholds,
        agent_agg, cfg.agent_thresholds, overall, cost_usd, total_tokens,
    )
    _save_report(report, run_id)
    print(report)

    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(score: float, threshold: float, metric: str) -> dict:
    lower = metric in _LOWER_IS_BETTER
    passed = score <= threshold if lower else score >= threshold
    return {"score": score, "threshold": threshold, "pass": passed}


def _build_payload(
    run_id, model, rag_agg, rag_thresholds,
    agent_agg, agent_thresholds, overall, cost_usd, total_tokens,
) -> dict:
    rag_checks   = {m: _check(s, rag_thresholds.get(m, 0.0), m)   for m, s in rag_agg.items()}
    agent_checks = {m: _check(s, agent_thresholds.get(m, 0.0), m) for m, s in agent_agg.items()}
    return {
        "run_id":       run_id,
        "model":        model,
        "rag":          rag_checks,
        "agent":        agent_checks,
        "overall":      overall,
        "cost_usd":     round(cost_usd, 6),
        "total_tokens": total_tokens,
    }


def _save_json(run_id: str, payload: dict) -> None:
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    path = RESULTS_PATH / f"{run_id}.json"
    path.write_text(json.dumps(payload, indent=2))
    logger.info("Run result saved: %s", path)


def _append_history(
    run_id, model, rag_agg, agent_agg, overall, cost_usd, total_tokens,
) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id":       run_id,
        "model":        model,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "overall":      overall,
        "cost_usd":     round(cost_usd, 6),
        "total_tokens": total_tokens,
        **{f"rag_{k}":   v for k, v in rag_agg.items()},
        **{f"agent_{k}": v for k, v in agent_agg.items()},
    }
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info("Run appended to history: %s", HISTORY_PATH)


def _status(score: float, threshold: float, metric: str) -> str:
    lower = metric in _LOWER_IS_BETTER
    return "PASS" if (score <= threshold if lower else score >= threshold) else "FAIL"


def _generate_markdown(
    run_id, model, rag_agg, rag_thresholds,
    agent_agg, agent_thresholds, overall, cost_usd, total_tokens,
) -> str:
    lines = [
        f"# Eval Run: {run_id}",
        "",
        f"**Model:** {model}  ",
        f"**Overall:** `{overall}`  ",
        f"**Cost:** ${cost_usd:.4f}  ",
        f"**Tokens:** {total_tokens:,}",
        "",
        "---",
        "",
        "## RAG Metrics",
        "",
        "| Metric | Score | Threshold | Status |",
        "|---|---|---|---|",
    ]
    for metric, score in rag_agg.items():
        threshold = rag_thresholds.get(metric, 0.0)
        st = _status(score, threshold, metric)
        icon = "✅" if st == "PASS" else "❌"
        lines.append(f"| {metric} | {score:.4f} | {threshold} | {icon} {st} |")

    lines += ["", "## Agent Metrics", "", "| Metric | Score | Threshold | Status |", "|---|---|---|---|"]
    for metric, score in agent_agg.items():
        threshold = agent_thresholds.get(metric, 0.0)
        st = _status(score, threshold, metric)
        icon = "✅" if st == "PASS" else "❌"
        lines.append(f"| {metric} | {score:.4f} | {threshold} | {icon} {st} |")

    lines += ["", "---", ""]
    return "\n".join(lines)


def _save_report(content: str, run_id: str) -> None:
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    (REPORTS_PATH / f"{run_id}.md").write_text(content)
    (REPORTS_PATH / "latest_report.md").write_text(content)
    logger.info("Report saved: %s", REPORTS_PATH / "latest_report.md")
