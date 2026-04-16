"""
LLM Eval Framework CLI

Usage:
    python cli.py run                          # run all evals
    python cli.py run --target rag             # RAG evals only
    python cli.py run --target agent           # agent evals only
    python cli.py history --last 10            # show last 10 runs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing from src/ without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import EvalConfig, settings
from src.reporting.history_tracker import append_run, load_history
from src.reporting.markdown_reporter import generate_markdown, save_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")

# httpx fires async-cleanup tasks after asyncio.run() closes the event loop
# when the pr_review_agent pipeline is called in a loop. Suppress that noise.
class _SuppressEventLoopClosed(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Event loop is closed" not in (record.getMessage())

logging.getLogger("asyncio").addFilter(_SuppressEventLoopClosed())

RESULTS_PATH = Path(__file__).resolve().parent / "outputs" / "results"

# GPT-4o-mini cost per token (as of 2025)
COST_PER_INPUT_TOKEN = 0.00000015
COST_PER_OUTPUT_TOKEN = 0.0000006


def _check_thresholds(
    aggregates: dict[str, float],
    thresholds: dict[str, float],
    lower_is_better: set[str] | None = None,
) -> dict[str, dict]:
    lower_is_better = lower_is_better or set()
    results = {}
    for metric, threshold in thresholds.items():
        score = aggregates.get(metric, 0.0)
        if metric in lower_is_better:
            passed = score <= threshold
        else:
            passed = score >= threshold
        results[metric] = {"score": score, "threshold": threshold, "pass": passed}
    return results


def cmd_run(args: argparse.Namespace) -> int:
    cfg = EvalConfig(args.config)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    target = args.target  # "all", "rag", or "agent"

    rag_aggregates: dict[str, float] = {}
    agent_aggregates: dict[str, float] = {}
    rag_tokens = 0
    agent_tokens = 0
    rag_checks: dict = {}
    agent_checks: dict = {}

    # --- RAG eval ---
    if target in ("all", "rag"):
        from src.evaluators.rag_evaluator import run_rag_eval
        logger.info("=== RAG Eval ===")
        rag_result = run_rag_eval(cfg)
        rag_aggregates = rag_result.aggregates
        rag_tokens = rag_result.tokens_used
        rag_checks = _check_thresholds(rag_aggregates, cfg.rag_thresholds)

        logger.info("RAG results:")
        for metric, info in rag_checks.items():
            status = "PASS" if info["pass"] else "FAIL"
            logger.info(f"  {metric}: {info['score']:.4f} (threshold {info['threshold']}) — {status}")

    # --- Agent eval ---
    if target in ("all", "agent"):
        from src.evaluators.agent_evaluator import run_agent_eval
        logger.info("=== Agent Eval ===")
        agent_result = run_agent_eval(cfg)
        agent_aggregates = agent_result.aggregates
        agent_tokens = agent_result.tokens_used
        agent_checks = _check_thresholds(
            agent_aggregates,
            cfg.agent_thresholds,
            lower_is_better={"false_positive_rate"},
        )

        logger.info("Agent results:")
        for metric, info in agent_checks.items():
            status = "PASS" if info["pass"] else "FAIL"
            logger.info(f"  {metric}: {info['score']:.4f} (threshold {info['threshold']}) — {status}")

    # --- Overall pass/fail ---
    all_checks = list(rag_checks.values()) + list(agent_checks.values())
    overall = "PASS" if all(c["pass"] for c in all_checks) else "FAIL"
    total_tokens = rag_tokens + agent_tokens
    cost_usd = total_tokens * COST_PER_INPUT_TOKEN  # rough estimate

    logger.info(f"=== Overall: {overall} ===")

    # --- Save raw result ---
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    result_payload = {
        "run_id": run_id,
        "model": cfg.model,
        "rag": rag_checks,
        "agent": agent_checks,
        "overall": overall,
        "cost_usd": round(cost_usd, 6),
        "total_tokens": total_tokens,
    }
    result_file = RESULTS_PATH / f"{run_id}.json"
    result_file.write_text(json.dumps(result_payload, indent=2))
    logger.info(f"Run result saved: {result_file}")

    # --- Append to history ---
    append_run(
        run_id=run_id,
        model=cfg.model,
        rag_aggregates=rag_aggregates,
        agent_aggregates=agent_aggregates,
        overall=overall,
        cost_usd=cost_usd,
        total_tokens=total_tokens,
    )

    # --- Generate report ---
    report = generate_markdown(
        run_id=run_id,
        model=cfg.model,
        rag_aggregates=rag_aggregates,
        rag_thresholds=cfg.rag_thresholds,
        agent_aggregates=agent_aggregates,
        agent_thresholds=cfg.agent_thresholds,
        overall=overall,
        cost_usd=cost_usd,
        total_tokens=total_tokens,
    )
    report_path = save_report(report, run_id.replace(":", "-"))
    logger.info(f"Report saved: {report_path}")
    print(report)

    # Exit 1 if any metric failed (CI gate)
    return 0 if overall == "PASS" else 1


def cmd_history(args: argparse.Namespace) -> int:
    runs = load_history(last_n=args.last)
    if not runs:
        print("No history found.")
        return 0

    _skip = {"run_id", "model", "timestamp", "overall", "cost_usd", "total_tokens"}
    # Collect all metric keys across every run so RAG + agent columns both appear
    seen: dict[str, None] = {}
    for run in runs:
        for k in run:
            if k not in _skip:
                seen[k] = None
    metrics = list(seen)
    header = ["run_id", "overall"] + metrics
    print("\t".join(header))
    for run in runs:
        row = [run.get("run_id", ""), run.get("overall", "")]
        row += [str(round(run.get(m, 0.0), 4)) for m in metrics]
        print("\t".join(row))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Eval Framework")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run evaluations")
    run_parser.add_argument("--config", default="eval_config.yaml", help="Path to eval_config.yaml")
    run_parser.add_argument("--target", choices=["all", "rag", "agent"], default="all")

    history_parser = sub.add_parser("history", help="Show eval history")
    history_parser.add_argument("--last", type=int, default=None, help="Show last N runs")

    args = parser.parse_args()
    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "history":
        sys.exit(cmd_history(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
