"""Tests for LLM judge functions — OpenAI calls are mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.evaluators.llm_judge import (
    check_bug_caught,
    check_is_valid_concern,
    score_comment_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_openai_response(content: dict) -> MagicMock:
    """Build a mock openai.ChatCompletion response."""
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# score_comment_quality
# ---------------------------------------------------------------------------

@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_score_comment_quality_returns_score_and_reason(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"score": 0.85, "reason": "Clear and actionable."}
    )

    score, reason = score_comment_quality(diff="diff text", comment="The loop overflows.")

    assert score == 0.85
    assert reason == "Clear and actionable."


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_score_comment_quality_clamps_missing_fields(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response({})

    score, reason = score_comment_quality(diff="diff", comment="comment")

    assert score == 0.0
    assert reason == ""


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_score_comment_quality_calls_gpt4o_mini(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"score": 0.5, "reason": "ok"}
    )

    score_comment_quality(diff="d", comment="c")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# check_bug_caught
# ---------------------------------------------------------------------------

@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_bug_caught_returns_true_when_first_comment_catches_bug(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"caught": True, "reason": "Comment addresses the off-by-one."}
    )

    result = check_bug_caught(
        known_bug="off-by-one error in age check",
        diff="-if age > 18:\n+if age >= 18:",
        comments=["The condition now allows 18-year-olds."],
    )

    assert result is True


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_bug_caught_returns_false_when_no_comment_matches(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"caught": False, "reason": "Comment is about style only."}
    )

    result = check_bug_caught(
        known_bug="off-by-one error",
        diff="...",
        comments=["Variable name should be snake_case."],
    )

    assert result is False


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_bug_caught_stops_early_on_first_match(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"caught": True, "reason": "Caught."}
    )

    check_bug_caught(
        known_bug="bug",
        diff="diff",
        comments=["comment1", "comment2", "comment3"],
    )

    # Should stop after the first True — only 1 API call
    assert mock_client.chat.completions.create.call_count == 1


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_bug_caught_returns_false_for_empty_comments(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    result = check_bug_caught(known_bug="bug", diff="diff", comments=[])

    assert result is False
    mock_client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# check_is_valid_concern
# ---------------------------------------------------------------------------

@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_is_valid_concern_true(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"valid": True, "reason": "Null pointer dereference is a real bug."}
    )

    result = check_is_valid_concern(diff="...", comment="This can throw NPE.")
    assert result is True


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_is_valid_concern_false(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        {"valid": False, "reason": "Comment is not about the diff."}
    )

    result = check_is_valid_concern(diff="...", comment="Consider adding tests.")
    assert result is False


@patch("src.evaluators.llm_judge.openai.OpenAI")
def test_check_is_valid_concern_defaults_true_on_missing_field(mock_openai_cls):
    """If LLM returns unexpected JSON, default conservatively to True (not a FP)."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response({})

    result = check_is_valid_concern(diff="d", comment="c")
    assert result is True
