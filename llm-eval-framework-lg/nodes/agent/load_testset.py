"""Agent sub-graph node: load the PR agent testset from disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eval_models.schemas import AgentSample
from state.agent_state import AgentEvalState

logger = logging.getLogger(__name__)


def load_testset_node(state: AgentEvalState) -> dict:
    """Load pr_agent_testset.json — raises if missing (no generation path for agent data)."""
    cfg = state["config"]
    path = Path(cfg.agent_dataset)

    if not path.exists():
        raise FileNotFoundError(
            f"Agent testset not found: {path}. "
            "The agent testset contains hand-crafted synthetic PRs with known bugs "
            "and must exist before running agent evaluation."
        )

    with open(path) as f:
        records = json.load(f)

    samples = [
        AgentSample(
            pr_id=r["pr_id"],
            description=r.get("description", ""),
            diff=r["diff"],
            known_bugs=r["known_bugs"],
            agent_comments=r.get("agent_comments", []),
        )
        for r in records
    ]
    logger.info("Loaded %d agent samples from %s", len(samples), path)
    return {"samples": samples}
