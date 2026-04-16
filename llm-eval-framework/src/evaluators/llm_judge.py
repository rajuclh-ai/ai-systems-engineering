"""Generic LLM-as-judge — scores free-text outputs on a 0.0–1.0 scale."""

from __future__ import annotations

import json
import logging

import openai

from src.config import settings

logger = logging.getLogger(__name__)

BUG_CAUGHT_PROMPT = """\
You are evaluating whether an AI code reviewer caught a known bug.

Known bug:
{known_bug}

Diff:
{diff}

Reviewer comment:
{comment}

Does the reviewer comment address or identify the known bug (even with different wording)?
Respond with ONLY a JSON object: {{"caught": true|false, "reason": "<one sentence>"}}
"""

COMMENT_QUALITY_PROMPT = """\
You are an expert code reviewer evaluating the quality of an AI-generated code review comment.

Score the comment below on a scale of 0.0 to 1.0 based on:
- Accuracy: Is the observation factually correct given the diff?
- Actionability: Does it tell the developer what to fix and how?
- Relevance: Does it focus on a real issue (not noise or style nitpicks for a logic bug)?

Diff:
{diff}

Comment:
{comment}

Respond with ONLY a JSON object in this exact format:
{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}
"""


VALID_CONCERN_PROMPT = """\
You are a senior code reviewer. Given a code diff and a reviewer comment, determine whether
the comment raises a legitimate concern about the code (a real bug, security issue, logic error,
or significant quality problem) — regardless of whether it is the specific bug you were looking for.

Diff:
{diff}

Reviewer comment:
{comment}

Is this comment raising a real, actionable concern about the code?
Respond with ONLY a JSON object: {{"valid": true|false, "reason": "<one sentence>"}}
"""


def check_is_valid_concern(diff: str, comment: str) -> bool:
    """
    Use an LLM judge to determine whether a comment raises a genuine concern,
    as opposed to being noise or a hallucinated issue.

    Used to compute false positive rate: a comment is a false positive only
    if the LLM judge says it does NOT identify a real concern.
    """
    client = openai.OpenAI(api_key=settings.openai_api_key)
    prompt = VALID_CONCERN_PROMPT.format(diff=diff, comment=comment)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = json.loads(response.choices[0].message.content or "{}")
    is_valid = bool(raw.get("valid", True))
    logger.debug(f"Valid concern: {is_valid} — {raw.get('reason', '')}")
    return is_valid


def check_bug_caught(known_bug: str, diff: str, comments: list[str]) -> bool:
    """
    Use an LLM judge to determine whether any of the agent's comments
    address the given known bug, regardless of vocabulary differences.

    Returns True if the bug was caught by at least one comment.
    """
    client = openai.OpenAI(api_key=settings.openai_api_key)
    for comment in comments:
        prompt = BUG_CAUGHT_PROMPT.format(known_bug=known_bug, diff=diff, comment=comment)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        if raw.get("caught", False):
            logger.debug(f"Bug caught by comment — {raw.get('reason', '')}")
            return True
    logger.debug(f"Bug NOT caught: {known_bug[:60]}")
    return False


def score_comment_quality(diff: str, comment: str) -> tuple[float, str]:
    """
    Score a single agent comment for quality.

    Returns:
        (score, reason) — score is 0.0–1.0, reason is one sentence.
    """
    client = openai.OpenAI(api_key=settings.openai_api_key)
    prompt = COMMENT_QUALITY_PROMPT.format(diff=diff, comment=comment)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = json.loads(response.choices[0].message.content or "{}")
    score = float(raw.get("score", 0.0))
    reason = raw.get("reason", "")
    logger.debug(f"Comment quality score: {score:.2f} — {reason}")
    return score, reason
