"""Tests for dataset loaders — no LLM calls needed."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.datasets.loader import (
    AgentSample,
    RagSample,
    load_agent_dataset,
    load_rag_dataset,
)


# ---------------------------------------------------------------------------
# RagSample / load_rag_dataset
# ---------------------------------------------------------------------------

def test_load_rag_dataset_returns_empty_for_missing_file(tmp_path):
    result = load_rag_dataset(tmp_path / "nonexistent.json")
    assert result == []


def test_load_rag_dataset_minimal_fields(tmp_path):
    data = [{"question": "What is LoRA?", "ground_truth": "A low-rank adaptation method."}]
    path = tmp_path / "rag.json"
    path.write_text(json.dumps(data))

    samples = load_rag_dataset(path)

    assert len(samples) == 1
    s = samples[0]
    assert isinstance(s, RagSample)
    assert s.question == "What is LoRA?"
    assert s.ground_truth == "A low-rank adaptation method."
    assert s.answer == ""
    assert s.contexts == []


def test_load_rag_dataset_with_optional_fields(tmp_path):
    data = [{
        "question": "Q",
        "ground_truth": "GT",
        "answer": "A",
        "contexts": ["ctx1", "ctx2"],
    }]
    path = tmp_path / "rag.json"
    path.write_text(json.dumps(data))

    samples = load_rag_dataset(path)

    s = samples[0]
    assert s.answer == "A"
    assert s.contexts == ["ctx1", "ctx2"]


def test_load_rag_dataset_multiple_records(tmp_path):
    data = [
        {"question": f"Q{i}", "ground_truth": f"GT{i}"}
        for i in range(5)
    ]
    path = tmp_path / "rag.json"
    path.write_text(json.dumps(data))

    samples = load_rag_dataset(path)
    assert len(samples) == 5


# ---------------------------------------------------------------------------
# AgentSample / load_agent_dataset
# ---------------------------------------------------------------------------

def test_load_agent_dataset_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_agent_dataset(tmp_path / "nonexistent.json")


def test_load_agent_dataset_minimal_fields(tmp_path):
    data = [{
        "pr_id": "pr-001",
        "diff": "-x = 1\n+x = 2",
        "known_bugs": ["off-by-one error"],
    }]
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(data))

    samples = load_agent_dataset(path)

    assert len(samples) == 1
    s = samples[0]
    assert isinstance(s, AgentSample)
    assert s.pr_id == "pr-001"
    assert s.diff == "-x = 1\n+x = 2"
    assert s.known_bugs == ["off-by-one error"]
    assert s.agent_comments == []


def test_load_agent_dataset_with_cached_comments(tmp_path):
    data = [{
        "pr_id": "pr-002",
        "diff": "...",
        "known_bugs": ["inverted condition"],
        "agent_comments": ["The condition is inverted."],
    }]
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(data))

    samples = load_agent_dataset(path)
    assert samples[0].agent_comments == ["The condition is inverted."]


def test_load_agent_dataset_multiple_records(tmp_path):
    data = [
        {"pr_id": f"pr-{i:03d}", "diff": "...", "known_bugs": ["bug"]}
        for i in range(7)
    ]
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(data))

    samples = load_agent_dataset(path)
    assert len(samples) == 7
    assert [s.pr_id for s in samples] == [f"pr-{i:03d}" for i in range(7)]
