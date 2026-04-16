"""Agent evaluator — bug recall, false positive rate, comment quality via LLM judge."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config import EvalConfig, settings
from src.datasets.loader import AgentSample, load_agent_dataset
from src.evaluators.llm_judge import check_bug_caught, check_is_valid_concern, score_comment_quality

logger = logging.getLogger(__name__)


@dataclass
class AgentPRScore:
    pr_id: str
    bug_recall: float          # fraction of known_bugs that the agent flagged
    false_positive_rate: float # fraction of agent comments that are NOT real bugs
    comment_quality: float     # average LLM judge score across all comments
    bugs_caught: int
    bugs_missed: int
    false_positives: int


@dataclass
class AgentEvalResult:
    scores: list[AgentPRScore]
    aggregates: dict[str, float]
    tokens_used: int = 0


def _import_agent_pipeline(agent_project_path: str):
    """Dynamically import pr_review_agent pipeline."""
    # The pr_review_agent reads OPENAI_API_KEY directly from the environment.
    # Propagate it here so agents don't fail when the key was loaded via .env.
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if agent_project_path not in sys.path:
        sys.path.insert(0, agent_project_path)
    from supervisor.pipeline import run_pipeline
    return run_pipeline


def _get_agent_comments(diff: str, agent_project_path: str) -> list[str]:
    """Run the PR review agent on a diff and return all comment messages."""
    run_pipeline = _import_agent_pipeline(agent_project_path)
    agent_results, critic_report, _ = asyncio.run(run_pipeline(diff))
    comments = [f.message for f in critic_report.findings]
    return comments


def _compute_bug_recall(known_bugs: list[str], comments: list[str], diff: str) -> tuple[int, int]:
    """
    Use an LLM judge to determine whether each known bug was addressed by any comment.
    Returns (bugs_caught, bugs_missed).

    LLM-based evaluation is used here because keyword overlap fails when the agent
    uses different vocabulary than the bug description (which is nearly always).
    """
    bugs_caught = 0
    bugs_missed = 0
    for bug in known_bugs:
        if check_bug_caught(bug, diff, comments):
            bugs_caught += 1
        else:
            bugs_missed += 1
    return bugs_caught, bugs_missed


def _compute_false_positive_rate(known_bugs: list[str], comments: list[str], diff: str) -> tuple[int, int]:
    """
    A comment is a false positive if an LLM judge determines it does NOT raise
    a genuine concern about the code. Comments about real issues (even unplanted
    ones) are not counted as false positives.
    Returns (false_positives, total_comments).
    """
    if not comments:
        return 0, 0

    false_positives = 0
    for comment in comments:
        if not check_is_valid_concern(diff, comment):
            false_positives += 1

    return false_positives, len(comments)


def _score_pr(sample: AgentSample, agent_project_path: str) -> tuple[AgentPRScore, int]:
    """Run the agent on one PR diff and compute all metrics."""
    logger.info(f"Running agent on {sample.pr_id}")

    if sample.agent_comments:
        comments = sample.agent_comments
        tokens = 0
    else:
        comments = _get_agent_comments(sample.diff, agent_project_path)
        tokens = 0  # token tracking from agent pipeline not exposed at this level

    bugs_caught, bugs_missed = _compute_bug_recall(sample.known_bugs, comments, sample.diff)
    bug_recall = bugs_caught / len(sample.known_bugs) if sample.known_bugs else 0.0

    false_positives, total_comments = _compute_false_positive_rate(sample.known_bugs, comments, sample.diff)
    fpr = false_positives / total_comments if total_comments > 0 else 0.0

    quality_scores = []
    for comment in comments:
        score, _ = score_comment_quality(sample.diff, comment)
        quality_scores.append(score)
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    return AgentPRScore(
        pr_id=sample.pr_id,
        bug_recall=round(bug_recall, 4),
        false_positive_rate=round(fpr, 4),
        comment_quality=round(avg_quality, 4),
        bugs_caught=bugs_caught,
        bugs_missed=bugs_missed,
        false_positives=false_positives,
    ), tokens


def run_agent_eval(cfg: EvalConfig) -> AgentEvalResult:
    """
    Full agent evaluation run.

    1. Load testset.
    2. Run agent pipeline on each diff.
    3. Compute recall, FPR, and comment quality per PR.
    4. Return per-PR scores and aggregates.
    """
    samples = load_agent_dataset(cfg.agent_dataset)
    logger.info(f"Running agent eval on {len(samples)} PRs")

    pr_scores = []
    total_tokens = 0

    for sample in samples:
        score, tokens = _score_pr(sample, settings.agent_project_path)
        pr_scores.append(score)
        total_tokens += tokens

    aggregates = {
        "bug_recall": round(
            sum(s.bug_recall for s in pr_scores) / len(pr_scores), 4
        ) if pr_scores else 0.0,
        "false_positive_rate": round(
            sum(s.false_positive_rate for s in pr_scores) / len(pr_scores), 4
        ) if pr_scores else 0.0,
        "comment_quality": round(
            sum(s.comment_quality for s in pr_scores) / len(pr_scores), 4
        ) if pr_scores else 0.0,
    }

    return AgentEvalResult(scores=pr_scores, aggregates=aggregates, tokens_used=total_tokens)
