"""Append each eval run result to a JSONL history log for trend tracking."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "outputs" / "history" / "metrics_log.jsonl"


def append_run(
    run_id: str,
    model: str,
    rag_aggregates: dict[str, float],
    agent_aggregates: dict[str, float],
    overall: str,
    cost_usd: float,
    total_tokens: int,
) -> None:
    """Append one run's aggregate metrics to the JSONL history log."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "run_id": run_id,
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "cost_usd": round(cost_usd, 6),
        "total_tokens": total_tokens,
        **{f"rag_{k}": v for k, v in rag_aggregates.items()},
        **{f"agent_{k}": v for k, v in agent_aggregates.items()},
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"Run appended to history: {HISTORY_PATH}")


def load_history(last_n: int | None = None) -> list[dict]:
    """Load all runs from the history log. Optionally return only the last N."""
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH) as f:
        runs = [json.loads(line) for line in f if line.strip()]
    if last_n:
        runs = runs[-last_n:]
    return runs
