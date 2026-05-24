"""Agent sub-graph node: score one PR — call the live agent then run 3 judge chains.

Invoked in parallel via Send() — one node call per PR in the testset.
The state dict received here is NOT the full AgentEvalState; it is the dict
passed by the Send() call: {"config": cfg, "sample": AgentSample}.

Returns {"pr_scores": [AgentPRScore]} which the Annotated[list, add]
reducer in AgentEvalState accumulates as each parallel call completes.

LLM calls made here:
  1. live pr_review_agent pipeline (its own LLM usage, external)
  2. bug_recall judge — one call per (known_bug, comment) pair
  3. false_positive judge — one call per comment
  4. comment_quality judge — one call per comment
All judge calls are traced in LangSmith automatically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading

from config import settings
from eval_models.schemas import AgentPRScore, AgentSample
from judges.llm_judge import check_bug_caught, check_is_valid_concern, score_comment_quality

logger = logging.getLogger(__name__)

# LangGraph runs parallel Send() nodes in a ThreadPoolExecutor.
# Guard the one-time sys.path mutation and first import with a lock so only
# one thread does the setup; all others wait and reuse the cached function.
_agent_import_lock = threading.Lock()
_run_pipeline = None


def _import_agent_pipeline(agent_project_path: str):
    """Import pr_review_agent's run_pipeline exactly once across all threads.

    Uses double-checked locking: fast path (no lock) when already imported,
    slow path (locked) for the one-time sys.path + import setup.
    """
    global _run_pipeline
    if _run_pipeline is not None:
        return _run_pipeline

    with _agent_import_lock:
        if _run_pipeline is not None:  # another thread may have finished while we waited
            return _run_pipeline

        # Propagate the API key to the environment before any agent import
        if settings.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

        if agent_project_path not in sys.path:
            sys.path.insert(0, agent_project_path)

        from supervisor.pipeline import run_pipeline as _rp  # type: ignore
        _run_pipeline = _rp
        logger.info("Agent pipeline imported from %s", agent_project_path)
        return _run_pipeline


def _get_agent_comments(diff: str) -> list[str]:
    """Run the live pr_review_agent pipeline and return all comment strings.

    asyncio.run() is safe in a ThreadPoolExecutor thread (Python 3.11+) —
    each thread gets its own event loop. We create and tear it down
    explicitly to avoid any edge case where a prior half-closed loop
    is found on the thread.
    """
    run_pipeline = _import_agent_pipeline(settings.agent_project_path)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _, critic_report, _ = loop.run_until_complete(run_pipeline(diff))
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    return [f.message for f in critic_report.findings]


def score_pr_node(state: dict) -> dict:
    """Call the agent on one diff and score it with the three judge chains.

    state keys expected: config, sample (AgentSample)
    """
    cfg = state["config"]
    sample: AgentSample = state["sample"]

    logger.info("Scoring PR: %s — %s", sample.pr_id, sample.description[:60])

    # Use pre-cached comments if present in the dataset (speeds up repeated runs)
    if sample.agent_comments:
        comments = sample.agent_comments
    else:
        comments = _get_agent_comments(sample.diff)

    # --- Bug recall ---
    bugs_caught = 0
    bugs_missed = 0
    for bug in sample.known_bugs:
        caught = False
        for comment in comments:
            result = check_bug_caught(bug, sample.diff, comment, cfg.model)
            if result.caught:
                caught = True
                break
        if caught:
            bugs_caught += 1
        else:
            bugs_missed += 1

    bug_recall = bugs_caught / len(sample.known_bugs) if sample.known_bugs else 0.0

    # --- False positive rate ---
    false_positives = 0
    for comment in comments:
        result = check_is_valid_concern(sample.diff, comment, cfg.model)
        if not result.valid:
            false_positives += 1

    fpr = false_positives / len(comments) if comments else 0.0

    # --- Comment quality ---
    quality_scores = []
    for comment in comments:
        result = score_comment_quality(sample.diff, comment, cfg.model)
        quality_scores.append(result.score)

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    pr_score = AgentPRScore(
        pr_id=sample.pr_id,
        bug_recall=round(bug_recall, 4),
        false_positive_rate=round(fpr, 4),
        comment_quality=round(avg_quality, 4),
        bugs_caught=bugs_caught,
        bugs_missed=bugs_missed,
        false_positives=false_positives,
    )
    logger.info(
        "%s — recall=%.2f fpr=%.2f quality=%.2f",
        sample.pr_id, bug_recall, fpr, avg_quality,
    )
    return {"pr_scores": [pr_score]}
