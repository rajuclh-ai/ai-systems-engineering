"""
LLM Eval Framework v2 — LangGraph Edition CLI

Usage:
    python cli.py run                          # run all evals (RAG + Agent in parallel)
    python cli.py run --target rag             # RAG evals only
    python cli.py run --target agent           # agent evals only
    python cli.py history --last 10            # show last 10 runs

The CLI interface is identical to v1. The orchestration underneath is now a
LangGraph StateGraph with two levels of parallel Send() fan-out.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make top-level packages importable without installing the project
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import EvalConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")

# httpx fires async-cleanup tasks after asyncio.run() closes the event loop.
# Suppress that noise when the agent pipeline is called.
class _SuppressEventLoopClosed(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Event loop is closed" not in record.getMessage()

logging.getLogger("asyncio").addFilter(_SuppressEventLoopClosed())

HISTORY_PATH = Path(__file__).resolve().parent / "outputs" / "history" / "metrics_log.jsonl"


def cmd_run(args: argparse.Namespace) -> int:
    from graphs.eval_graph import build_eval_graph

    cfg    = EvalConfig(args.config)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    target = args.target  # "all", "rag", or "agent"

    graph = build_eval_graph().compile()

    initial_state = {
        "config":       cfg,
        "target":       target,
        "run_id":       run_id,
        "eval_results": [],
        "overall":      None,
        "total_tokens": 0,
        "cost_usd":     0.0,
    }

    logger.info("Starting eval run %s (target=%s)", run_id, target)
    final_state = graph.invoke(initial_state)

    overall = final_state.get("overall", "FAIL")
    return 0 if overall == "PASS" else 1


def cmd_history(args: argparse.Namespace) -> int:
    if not HISTORY_PATH.exists():
        print("No history found.")
        return 0

    with open(HISTORY_PATH) as f:
        runs = [json.loads(line) for line in f if line.strip()]

    if args.last:
        runs = runs[-args.last:]

    if not runs:
        print("No history found.")
        return 0

    _skip = {"run_id", "model", "timestamp", "overall", "cost_usd", "total_tokens"}
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
    parser = argparse.ArgumentParser(description="LLM Eval Framework v2 — LangGraph Edition")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run evaluations")
    run_p.add_argument("--config", default="eval_config.yaml", help="Path to eval_config.yaml")
    run_p.add_argument("--target", choices=["all", "rag", "agent"], default="all")

    hist_p = sub.add_parser("history", help="Show eval history")
    hist_p.add_argument("--last", type=int, default=None, help="Show last N runs")

    args = parser.parse_args()
    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "history":
        sys.exit(cmd_history(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
