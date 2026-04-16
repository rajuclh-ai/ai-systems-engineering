"""Tests for EvalConfig YAML loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.config import EvalConfig


MINIMAL_YAML = textwrap.dedent("""\
    model: gpt-4o-mini
    temperature: 0

    rag:
      dataset: datasets/arxiv_rag_testset.json
      generate_n: 10
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
""")


def test_eval_config_reads_model_and_temperature(tmp_path):
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(MINIMAL_YAML)

    cfg = EvalConfig(cfg_file)

    assert cfg.model == "gpt-4o-mini"
    assert cfg.temperature == 0


def test_eval_config_rag_thresholds(tmp_path):
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(MINIMAL_YAML)

    cfg = EvalConfig(cfg_file)

    assert cfg.rag_thresholds["faithfulness"] == 0.70
    assert cfg.rag_thresholds["answer_relevance"] == 0.70
    assert cfg.rag_thresholds["context_recall"] == 0.65
    assert cfg.rag_thresholds["context_precision"] == 0.65


def test_eval_config_agent_thresholds(tmp_path):
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(MINIMAL_YAML)

    cfg = EvalConfig(cfg_file)

    assert cfg.agent_thresholds["bug_recall"] == 0.70
    assert cfg.agent_thresholds["false_positive_rate"] == 0.40
    assert cfg.agent_thresholds["comment_quality"] == 0.60


def test_eval_config_rag_generate_n(tmp_path):
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(MINIMAL_YAML)

    cfg = EvalConfig(cfg_file)

    assert cfg.rag_generate_n == 10


def test_eval_config_dataset_paths_are_pathlib(tmp_path):
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(MINIMAL_YAML)

    cfg = EvalConfig(cfg_file)

    assert isinstance(cfg.rag_dataset, Path)
    assert isinstance(cfg.agent_dataset, Path)
    assert cfg.rag_dataset.name == "arxiv_rag_testset.json"
    assert cfg.agent_dataset.name == "pr_agent_testset.json"


def test_eval_config_temperature_defaults_to_zero(tmp_path):
    yaml_no_temp = textwrap.dedent("""\
        model: gpt-4o-mini
        rag:
          thresholds: {}
        agent:
          thresholds: {}
    """)
    cfg_file = tmp_path / "eval_config.yaml"
    cfg_file.write_text(yaml_no_temp)

    cfg = EvalConfig(cfg_file)
    assert cfg.temperature == 0
