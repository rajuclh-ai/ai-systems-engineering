"""
Fetcher Node — rule-based, no LLM.
Accepts either a GitHub PR URL or a raw diff pasted directly.
If a URL is provided, fetches the diff via GitHub REST API.
"""
import logging
from agent.state import ReviewState
from utils.github import fetch_pr_diff

logger = logging.getLogger(__name__)


def fetcher_node(state: ReviewState) -> dict:
    """
    Fetch the diff from GitHub or pass through a raw diff.
    Returns: {"diff": str}
    """
    pr_url = state.get("pr_url", "")
    existing_diff = state.get("diff", "")

    if existing_diff:
        logger.info("[FETCHER] raw diff provided (%d chars) — skipping GitHub fetch", len(existing_diff))
        return {}

    if not pr_url:
        raise ValueError("Either pr_url or diff must be provided")

    logger.info("[FETCHER] fetching diff for PR: %s", pr_url)
    diff = fetch_pr_diff(pr_url)
    logger.info("[FETCHER] fetched %d chars", len(diff))
    return {"diff": diff}
