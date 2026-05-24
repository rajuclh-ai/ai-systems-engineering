"""Tests for RAG sub-graph nodes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from eval_models.schemas import EnrichedRagSample, RagSample
from nodes.rag.load_testset import load_testset_node
from nodes.rag.ragas_scorer import ragas_scorer_node


class TestLoadTestsetNode:
    def test_loads_existing_dataset(self, tmp_path, eval_config):
        records = [
            {"question": "What is GPT?", "ground_truth": "A language model."},
            {"question": "What is BERT?", "ground_truth": "A bidirectional model."},
        ]
        dataset_path = tmp_path / "datasets" / "arxiv_rag_testset.json"
        dataset_path.parent.mkdir(parents=True)
        dataset_path.write_text(json.dumps(records))

        eval_config.rag_dataset = dataset_path
        result = load_testset_node({"config": eval_config})

        assert "samples" in result
        assert len(result["samples"]) == 2
        assert result["samples"][0].question == "What is GPT?"
        assert result["samples"][1].ground_truth == "A bidirectional model."

    def test_returns_rag_sample_objects(self, tmp_path, eval_config):
        records = [{"question": "Q?", "ground_truth": "A."}]
        dataset_path = tmp_path / "test.json"
        dataset_path.write_text(json.dumps(records))

        eval_config.rag_dataset = dataset_path
        result = load_testset_node({"config": eval_config})

        assert isinstance(result["samples"][0], RagSample)


class TestRagasScorerNode:
    def test_produces_scores_and_aggregates_and_eval_result(
        self, eval_config, enriched_samples
    ):
        from eval_models.schemas import RagQuestionScore

        mock_scores = [
            RagQuestionScore(
                question=s.question,
                faithfulness=0.9, answer_relevance=0.85,
                context_recall=0.75, context_precision=0.70,
            )
            for s in enriched_samples
        ]

        with patch("nodes.rag.ragas_scorer._score_with_ragas", return_value=mock_scores):
            state = {"config": eval_config, "enriched": enriched_samples}
            result = ragas_scorer_node(state)

        assert "scores" in result
        assert "aggregates" in result
        assert "eval_results" in result
        assert len(result["scores"]) == 2
        assert result["eval_results"][0].target == "rag"
        assert "faithfulness" in result["aggregates"]

    def test_aggregates_are_averaged(self, eval_config, enriched_samples):
        from eval_models.schemas import RagQuestionScore

        mock_scores = [
            RagQuestionScore(question="Q1", faithfulness=0.8, answer_relevance=0.7,
                             context_recall=0.6, context_precision=0.5),
            RagQuestionScore(question="Q2", faithfulness=0.6, answer_relevance=0.5,
                             context_recall=0.4, context_precision=0.3),
        ]

        with patch("nodes.rag.ragas_scorer._score_with_ragas", return_value=mock_scores):
            result = ragas_scorer_node({"config": eval_config, "enriched": enriched_samples})

        assert result["aggregates"]["faithfulness"]    == pytest.approx(0.7, abs=0.01)
        assert result["aggregates"]["answer_relevance"] == pytest.approx(0.6, abs=0.01)
