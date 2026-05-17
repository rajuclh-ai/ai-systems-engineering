"""
Learning Node — rule-based, no LLM.
Stores the completed review to SQLite for future context.
"""
import uuid
import logging
from agent.state import ReviewState
from models.db import get_session, ReviewRow
from utils.github import extract_repo

logger = logging.getLogger(__name__)


def learning_node(state: ReviewState) -> dict:
    report    = state.get("critic_report")
    pr_url    = state.get("pr_url", "")
    thread_id = state.get("review_id") or str(uuid.uuid4())

    if not report:
        logger.warning("[LEARNING] no critic_report — skipping store")
        return {}

    high   = sum(1 for f in report.findings if f.severity == "HIGH")
    medium = sum(1 for f in report.findings if f.severity == "MEDIUM")
    low    = sum(1 for f in report.findings if f.severity == "LOW")
    repo   = extract_repo(pr_url) if pr_url else ""

    try:
        with get_session() as session:
            row = ReviewRow(
                thread_id     = thread_id,
                pr_url        = pr_url,
                repo          = repo,
                verdict       = report.verdict,
                finding_count = len(report.findings),
                high_count    = high,
                medium_count  = medium,
                low_count     = low,
                summary       = report.summary,
            )
            session.add(row)
        logger.info("[LEARNING] stored review — thread=%s  verdict=%s  findings=%d",
                    thread_id, report.verdict, len(report.findings))
    except Exception as e:
        logger.error("[LEARNING] failed to store: %s", e)

    return {"review_id": thread_id}
