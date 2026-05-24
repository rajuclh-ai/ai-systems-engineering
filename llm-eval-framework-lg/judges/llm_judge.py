"""Three LangChain judge chains — one per agent metric.

v1 used raw openai.OpenAI() + json.loads(). v2 uses:
  ChatPromptTemplate | ChatOpenAI | with_structured_output(PydanticSchema)

Benefits:
  - Typed results (no more raw.get("score", 0.0))
  - Automatic LangSmith tracing for every call
  - Pydantic validation — bad LLM output raises, not silently returns 0
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from judges.schemas import BugCaughtResult, CommentQualityResult, ValidConcernResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts — identical content to v1, wrapped in ChatPromptTemplate
# ---------------------------------------------------------------------------

_BUG_CAUGHT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are evaluating whether an AI code reviewer caught a known bug."),
    ("human", """\
Known bug:
{known_bug}

Diff:
{diff}

Reviewer comment:
{comment}

Does the reviewer comment address or identify the known bug (even with different wording)?
"""),
])

_VALID_CONCERN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a senior code reviewer. Given a code diff and a reviewer comment, "
        "determine whether the comment raises a legitimate concern about the code "
        "(a real bug, security issue, logic error, or significant quality problem) — "
        "regardless of whether it is the specific bug you were looking for."
    )),
    ("human", """\
Diff:
{diff}

Reviewer comment:
{comment}

Is this comment raising a real, actionable concern about the code?
"""),
])

_COMMENT_QUALITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an expert code reviewer evaluating the quality of an AI-generated "
        "code review comment. Score the comment on a scale of 0.0 to 1.0 based on:\n"
        "- Accuracy: Is the observation factually correct given the diff?\n"
        "- Actionability: Does it tell the developer what to fix and how?\n"
        "- Relevance: Does it focus on a real issue (not noise or style nitpicks)?"
    )),
    ("human", """\
Diff:
{diff}

Comment:
{comment}
"""),
])


# ---------------------------------------------------------------------------
# Chain builders — called once per score_pr_node invocation
# ---------------------------------------------------------------------------

def _make_llm(model: str, temperature: int = 0) -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=temperature)


def check_bug_caught(known_bug: str, diff: str, comment: str, model: str) -> BugCaughtResult:
    """Judge: did this single comment catch the known bug?

    Called once per (known_bug, comment) pair inside score_pr_node.
    score_pr_node iterates over comments itself so each call is minimal.
    """
    llm = _make_llm(model)
    chain = _BUG_CAUGHT_PROMPT | llm.with_structured_output(BugCaughtResult)
    result: BugCaughtResult = chain.invoke({
        "known_bug": known_bug,
        "diff": diff,
        "comment": comment,
    })
    logger.debug("bug_caught=%s — %s", result.caught, result.reason)
    return result


def check_is_valid_concern(diff: str, comment: str, model: str) -> ValidConcernResult:
    """Judge: is this comment a genuine concern or a false positive?"""
    llm = _make_llm(model)
    chain = _VALID_CONCERN_PROMPT | llm.with_structured_output(ValidConcernResult)
    result: ValidConcernResult = chain.invoke({"diff": diff, "comment": comment})
    logger.debug("valid_concern=%s — %s", result.valid, result.reason)
    return result


def score_comment_quality(diff: str, comment: str, model: str) -> CommentQualityResult:
    """Judge: score this comment's accuracy and actionability (0.0–1.0)."""
    llm = _make_llm(model)
    chain = _COMMENT_QUALITY_PROMPT | llm.with_structured_output(CommentQualityResult)
    result: CommentQualityResult = chain.invoke({"diff": diff, "comment": comment})
    logger.debug("comment_quality=%.2f — %s", result.score, result.reason)
    return result
