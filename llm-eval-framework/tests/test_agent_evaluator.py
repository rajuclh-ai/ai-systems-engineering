"""Tests for agent evaluator metric logic — LLM judge calls are mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.datasets.loader import AgentSample
from src.evaluators.agent_evaluator import (
    _compute_bug_recall,
    _compute_false_positive_rate,
)


SAMPLE_DIFF = """\
def can_access(user):
-    if user.age > 18:
+    if user.age >= 18:
         return True
     return False
"""

KNOWN_BUGS = ["off-by-one error: 18-year-olds were incorrectly excluded"]
COMMENTS_CATCH = ["The condition now allows users aged exactly 18 to access the system."]
COMMENTS_MISS = ["Variable naming could be improved to follow PEP 8."]


# ---------------------------------------------------------------------------
# _compute_bug_recall
# ---------------------------------------------------------------------------

@patch("src.evaluators.agent_evaluator.check_bug_caught", return_value=True)
def test_bug_recall_all_caught(mock_judge):
    caught, missed = _compute_bug_recall(KNOWN_BUGS, COMMENTS_CATCH, SAMPLE_DIFF)
    assert caught == 1
    assert missed == 0


@patch("src.evaluators.agent_evaluator.check_bug_caught", return_value=False)
def test_bug_recall_none_caught(mock_judge):
    caught, missed = _compute_bug_recall(KNOWN_BUGS, COMMENTS_MISS, SAMPLE_DIFF)
    assert caught == 0
    assert missed == 1


@patch("src.evaluators.agent_evaluator.check_bug_caught", side_effect=[True, False, True])
def test_bug_recall_partial(mock_judge):
    bugs = ["bug1", "bug2", "bug3"]
    caught, missed = _compute_bug_recall(bugs, ["comment"], SAMPLE_DIFF)
    assert caught == 2
    assert missed == 1


@patch("src.evaluators.agent_evaluator.check_bug_caught")
def test_bug_recall_empty_bugs_returns_zero(mock_judge):
    caught, missed = _compute_bug_recall([], ["some comment"], SAMPLE_DIFF)
    assert caught == 0
    assert missed == 0
    mock_judge.assert_not_called()


# ---------------------------------------------------------------------------
# _compute_false_positive_rate
# ---------------------------------------------------------------------------

@patch("src.evaluators.agent_evaluator.check_is_valid_concern", return_value=True)
def test_fpr_all_valid_no_false_positives(mock_judge):
    fps, total = _compute_false_positive_rate(KNOWN_BUGS, COMMENTS_CATCH, SAMPLE_DIFF)
    assert fps == 0
    assert total == 1


@patch("src.evaluators.agent_evaluator.check_is_valid_concern", return_value=False)
def test_fpr_all_invalid_all_false_positives(mock_judge):
    comments = ["noise1", "noise2"]
    fps, total = _compute_false_positive_rate(KNOWN_BUGS, comments, SAMPLE_DIFF)
    assert fps == 2
    assert total == 2


@patch("src.evaluators.agent_evaluator.check_is_valid_concern", side_effect=[True, False, True])
def test_fpr_partial(mock_judge):
    comments = ["c1", "c2", "c3"]
    fps, total = _compute_false_positive_rate(KNOWN_BUGS, comments, SAMPLE_DIFF)
    assert fps == 1
    assert total == 3


@patch("src.evaluators.agent_evaluator.check_is_valid_concern")
def test_fpr_empty_comments_returns_zero(mock_judge):
    fps, total = _compute_false_positive_rate(KNOWN_BUGS, [], SAMPLE_DIFF)
    assert fps == 0
    assert total == 0
    mock_judge.assert_not_called()


# ---------------------------------------------------------------------------
# Aggregate calculation (end-to-end with pre-cached comments — no agent call)
# ---------------------------------------------------------------------------

@patch("src.evaluators.agent_evaluator.check_is_valid_concern", return_value=True)
@patch("src.evaluators.agent_evaluator.check_bug_caught", return_value=True)
@patch("src.evaluators.agent_evaluator.score_comment_quality", return_value=(0.8, "good"))
def test_score_pr_with_cached_comments(mock_quality, mock_caught, mock_valid, tmp_path):
    """When agent_comments are pre-cached, no pipeline call should happen."""
    import json
    from src.config import EvalConfig
    import textwrap

    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        model: gpt-4o-mini
        temperature: 0
        rag:
          thresholds: {}
        agent:
          dataset: datasets/pr_agent_testset.json
          thresholds:
            bug_recall: 0.70
            false_positive_rate: 0.40
            comment_quality: 0.60
    """))

    sample = AgentSample(
        pr_id="pr-001",
        description="test",
        diff=SAMPLE_DIFF,
        known_bugs=KNOWN_BUGS,
        agent_comments=["The boundary condition was fixed."],
    )

    from src.evaluators.agent_evaluator import _score_pr
    score, tokens = _score_pr(sample, agent_project_path="/unused")

    assert score.bug_recall == 1.0
    assert score.false_positive_rate == 0.0
    assert score.comment_quality == 0.8
    assert tokens == 0
