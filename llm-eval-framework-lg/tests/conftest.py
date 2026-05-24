"""Shared pytest fixtures for llm-eval-framework-lg tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make top-level packages importable from tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import EvalConfig
from eval_models.schemas import AgentPRScore, AgentSample, EnrichedRagSample, EvalSubResult, RagSample


@pytest.fixture
def eval_config(tmp_path) -> EvalConfig:
    """Minimal EvalConfig backed by a temp YAML file."""
    yaml_content = """
model: gpt-4o-mini
temperature: 0
rag:
  dataset: datasets/arxiv_rag_testset.json
  generate_n: 2
  thresholds:
    faithfulness: 0.70
    answer_relevance: 0.70
    context_recall: 0.65
    context_precision: 0.65
agent:
  dataset: datasets/pr_agent_testset.json
  thresholds:
    bug_recall: 0.70
    false_positive_rate: 0.40
    comment_quality: 0.60
"""
    cfg_path = tmp_path / "eval_config.yaml"
    cfg_path.write_text(yaml_content)
    return EvalConfig(path=cfg_path)


@pytest.fixture
def rag_samples() -> list[RagSample]:
    return [
        RagSample(question="What is attention?", ground_truth="Attention is a mechanism."),
        RagSample(question="What is BERT?", ground_truth="BERT is a language model."),
    ]


@pytest.fixture
def enriched_samples() -> list[EnrichedRagSample]:
    return [
        EnrichedRagSample(
            question="What is attention?",
            ground_truth="Attention is a mechanism.",
            answer="Attention lets models focus on relevant tokens.",
            contexts=["Attention mechanisms are used in transformers."],
            tokens_used=50,
        ),
        EnrichedRagSample(
            question="What is BERT?",
            ground_truth="BERT is a language model.",
            answer="BERT is a bidirectional transformer.",
            contexts=["BERT was introduced by Google in 2018."],
            tokens_used=40,
        ),
    ]


@pytest.fixture
def agent_samples() -> list[AgentSample]:
    return [
        AgentSample(
            pr_id="pr-001",
            description="Fix user age validation",
            diff="- if user.age > 18:\n+ if user.age >= 18:",
            known_bugs=["Off-by-one in age validation — changed > to >="],
            agent_comments=["The condition should use > not >= to exclude 18-year-olds."],
        ),
        AgentSample(
            pr_id="pr-002",
            description="Fix API response check",
            diff="- if response.ok:\n+ if not response.ok:",
            known_bugs=["Inverted condition on API response check"],
            agent_comments=["The condition is inverted — not response.ok means it only runs on failure."],
        ),
    ]


@pytest.fixture
def pr_scores() -> list[AgentPRScore]:
    return [
        AgentPRScore(
            pr_id="pr-001", bug_recall=1.0, false_positive_rate=0.0,
            comment_quality=0.9, bugs_caught=1, bugs_missed=0, false_positives=0,
        ),
        AgentPRScore(
            pr_id="pr-002", bug_recall=1.0, false_positive_rate=0.0,
            comment_quality=0.8, bugs_caught=1, bugs_missed=0, false_positives=0,
        ),
    ]


@pytest.fixture
def rag_sub_result() -> EvalSubResult:
    return EvalSubResult(
        target="rag",
        aggregates={
            "faithfulness": 0.85,
            "answer_relevance": 0.80,
            "context_recall": 0.72,
            "context_precision": 0.70,
        },
        tokens_used=1000,
    )


@pytest.fixture
def agent_sub_result() -> EvalSubResult:
    return EvalSubResult(
        target="agent",
        aggregates={
            "bug_recall": 0.86,
            "false_positive_rate": 0.14,
            "comment_quality": 0.75,
        },
        tokens_used=500,
    )
