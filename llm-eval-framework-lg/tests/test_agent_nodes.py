"""Tests for Agent sub-graph nodes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from eval_models.schemas import AgentPRScore, AgentSample
from nodes.agent.aggregate_agent import aggregate_agent_node
from nodes.agent.load_testset import load_testset_node
from nodes.agent.score_pr_node import score_pr_node


class TestLoadTestsetNode:
    def test_loads_existing_dataset(self, tmp_path, eval_config):
        records = [
            {
                "pr_id": "pr-001",
                "description": "Fix age check",
                "diff": "- if age > 18:\n+ if age >= 18:",
                "known_bugs": ["Off-by-one in age validation"],
            }
        ]
        path = tmp_path / "pr_agent_testset.json"
        path.write_text(json.dumps(records))

        eval_config.agent_dataset = path
        result = load_testset_node({"config": eval_config})

        assert len(result["samples"]) == 1
        assert isinstance(result["samples"][0], AgentSample)
        assert result["samples"][0].pr_id == "pr-001"

    def test_raises_if_missing(self, tmp_path, eval_config):
        eval_config.agent_dataset = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            load_testset_node({"config": eval_config})


class TestScorePrNode:
    def test_uses_cached_comments(self, eval_config, agent_samples):
        sample = agent_samples[0]  # has agent_comments pre-populated

        mock_bug = MagicMock(caught=True, reason="caught it")
        mock_concern = MagicMock(valid=True, reason="valid")
        mock_quality = MagicMock(score=0.9, reason="good")

        with patch("nodes.agent.score_pr_node.check_bug_caught",      return_value=mock_bug), \
             patch("nodes.agent.score_pr_node.check_is_valid_concern", return_value=mock_concern), \
             patch("nodes.agent.score_pr_node.score_comment_quality",  return_value=mock_quality):

            result = score_pr_node({"config": eval_config, "sample": sample})

        assert "pr_scores" in result
        assert len(result["pr_scores"]) == 1
        score = result["pr_scores"][0]
        assert isinstance(score, AgentPRScore)
        assert score.pr_id == "pr-001"
        assert score.bug_recall == 1.0
        assert score.false_positive_rate == 0.0
        assert score.comment_quality == pytest.approx(0.9, abs=0.01)

    def test_zero_recall_when_bug_not_caught(self, eval_config, agent_samples):
        sample = agent_samples[0]

        mock_bug     = MagicMock(caught=False, reason="missed")
        mock_concern = MagicMock(valid=True, reason="valid")
        mock_quality = MagicMock(score=0.5, reason="ok")

        with patch("nodes.agent.score_pr_node.check_bug_caught",      return_value=mock_bug), \
             patch("nodes.agent.score_pr_node.check_is_valid_concern", return_value=mock_concern), \
             patch("nodes.agent.score_pr_node.score_comment_quality",  return_value=mock_quality):

            result = score_pr_node({"config": eval_config, "sample": sample})

        assert result["pr_scores"][0].bug_recall == 0.0
        assert result["pr_scores"][0].bugs_missed == 1

    def test_fpr_counted_when_invalid_concern(self, eval_config, agent_samples):
        sample = agent_samples[0]

        mock_bug     = MagicMock(caught=True, reason="caught")
        mock_concern = MagicMock(valid=False, reason="not a real issue")
        mock_quality = MagicMock(score=0.3, reason="poor")

        with patch("nodes.agent.score_pr_node.check_bug_caught",      return_value=mock_bug), \
             patch("nodes.agent.score_pr_node.check_is_valid_concern", return_value=mock_concern), \
             patch("nodes.agent.score_pr_node.score_comment_quality",  return_value=mock_quality):

            result = score_pr_node({"config": eval_config, "sample": sample})

        assert result["pr_scores"][0].false_positive_rate == 1.0
        assert result["pr_scores"][0].false_positives == 1


class TestAggregateAgentNode:
    def test_averages_pr_scores(self, eval_config, pr_scores):
        state = {"config": eval_config, "pr_scores": pr_scores}
        result = aggregate_agent_node(state)

        assert result["aggregates"]["bug_recall"]          == pytest.approx(1.0,  abs=0.01)
        assert result["aggregates"]["false_positive_rate"] == pytest.approx(0.0,  abs=0.01)
        assert result["aggregates"]["comment_quality"]     == pytest.approx(0.85, abs=0.01)

    def test_emits_eval_sub_result(self, eval_config, pr_scores):
        result = aggregate_agent_node({"config": eval_config, "pr_scores": pr_scores})

        assert "eval_results" in result
        assert len(result["eval_results"]) == 1
        assert result["eval_results"][0].target == "agent"
