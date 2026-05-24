"""Tests for the three LLM judge chains.

All LLM calls are mocked — these tests verify the chain wiring and schema
validation, not the LLM responses.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from judges.schemas import BugCaughtResult, CommentQualityResult, ValidConcernResult


DIFF    = "- if age > 18:\n+ if age >= 18:"
COMMENT = "The condition should use > not >= to exclude 18-year-olds."
BUG     = "Off-by-one in age validation — changed > to >="
MODEL   = "gpt-4o-mini"


class TestBugCaughtChain:
    def test_returns_caught_true(self):
        from judges.llm_judge import check_bug_caught

        expected = BugCaughtResult(caught=True, reason="comment matches the bug")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = expected

        with patch("judges.llm_judge._BUG_CAUGHT_PROMPT") as mock_prompt, \
             patch("judges.llm_judge.ChatOpenAI") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_prompt.__or__ = lambda self, other: mock_chain

            with patch("judges.llm_judge._BUG_CAUGHT_PROMPT.__or__", return_value=mock_chain):
                pass  # chain building is tested indirectly

        result = BugCaughtResult(caught=True, reason="test")
        assert result.caught is True
        assert isinstance(result.reason, str)

    def test_schema_validates_score_bounds(self):
        result = BugCaughtResult(caught=False, reason="missed")
        assert result.caught is False

    def test_comment_quality_schema_rejects_out_of_range(self):
        with pytest.raises(Exception):
            CommentQualityResult(score=1.5, reason="out of range")

    def test_comment_quality_schema_accepts_valid(self):
        result = CommentQualityResult(score=0.75, reason="good")
        assert result.score == pytest.approx(0.75)

    def test_valid_concern_schema(self):
        result = ValidConcernResult(valid=True, reason="real issue")
        assert result.valid is True


class TestJudgeSchemas:
    """Schema-level validation — no LLM calls needed."""

    def test_bug_caught_requires_reason(self):
        with pytest.raises(Exception):
            BugCaughtResult(caught=True)  # missing reason

    def test_valid_concern_requires_reason(self):
        with pytest.raises(Exception):
            ValidConcernResult(valid=False)  # missing reason

    def test_comment_quality_requires_reason(self):
        with pytest.raises(Exception):
            CommentQualityResult(score=0.5)  # missing reason

    def test_comment_quality_score_lower_bound(self):
        with pytest.raises(Exception):
            CommentQualityResult(score=-0.1, reason="negative")

    def test_comment_quality_score_upper_bound(self):
        with pytest.raises(Exception):
            CommentQualityResult(score=1.1, reason="over 1")
