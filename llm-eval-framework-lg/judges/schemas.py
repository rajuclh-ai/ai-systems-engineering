"""Pydantic schemas for LLM judge structured outputs.

These replace the fragile json.loads() pattern from v1.
LangChain's with_structured_output() validates the LLM response against
these schemas and raises if the output doesn't conform — no silent failures.
Every call is also automatically traced in LangSmith.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BugCaughtResult(BaseModel):
    """Output of the bug_recall judge chain.

    Answers: did any reviewer comment address this specific known bug,
    even if phrased differently?
    """
    caught: bool
    reason: str = Field(description="One sentence explaining the decision")


class ValidConcernResult(BaseModel):
    """Output of the false_positive judge chain.

    Answers: is this comment raising a genuine code concern (real bug,
    logic error, security issue) — not noise or a hallucinated problem?
    A comment is a false positive only when valid=False.
    """
    valid: bool
    reason: str = Field(description="One sentence explaining the decision")


class CommentQualityResult(BaseModel):
    """Output of the comment_quality judge chain.

    Scores accuracy + actionability of a single reviewer comment on a 0.0–1.0 scale.
    """
    score: float = Field(ge=0.0, le=1.0, description="Quality score between 0.0 and 1.0")
    reason: str = Field(description="One sentence explaining the score")
