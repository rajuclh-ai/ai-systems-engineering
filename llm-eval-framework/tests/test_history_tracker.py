"""Tests for history tracker — file I/O only, no LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.reporting.history_tracker import append_run, load_history


def _write_run(tmp_history: Path, **overrides):
    defaults = dict(
        run_id="2026-04-16T10-00-00Z",
        model="gpt-4o-mini",
        rag_aggregates={"faithfulness": 0.85, "answer_relevance": 0.90},
        agent_aggregates={"bug_recall": 1.0, "false_positive_rate": 0.10},
        overall="PASS",
        cost_usd=0.004,
        total_tokens=8000,
    )
    defaults.update(overrides)
    with patch("src.reporting.history_tracker.HISTORY_PATH", tmp_history):
        append_run(**defaults)


# ---------------------------------------------------------------------------
# append_run
# ---------------------------------------------------------------------------

def test_append_run_creates_file(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    _write_run(history_file)
    assert history_file.exists()


def test_append_run_writes_valid_jsonl(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    _write_run(history_file)

    lines = history_file.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["run_id"] == "2026-04-16T10-00-00Z"
    assert record["overall"] == "PASS"


def test_append_run_prefixes_rag_and_agent_keys(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    _write_run(history_file)

    record = json.loads(history_file.read_text().strip())
    assert "rag_faithfulness" in record
    assert "rag_answer_relevance" in record
    assert "agent_bug_recall" in record
    assert "agent_false_positive_rate" in record


def test_append_run_appends_multiple_runs(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    _write_run(history_file, run_id="run-001")
    _write_run(history_file, run_id="run-002")
    _write_run(history_file, run_id="run-003")

    lines = history_file.read_text().strip().splitlines()
    assert len(lines) == 3


def test_append_run_stores_cost_and_tokens(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    _write_run(history_file, cost_usd=0.0123, total_tokens=5000)

    record = json.loads(history_file.read_text().strip())
    assert record["cost_usd"] == pytest.approx(0.0123, abs=1e-6)
    assert record["total_tokens"] == 5000


# ---------------------------------------------------------------------------
# load_history
# ---------------------------------------------------------------------------

def test_load_history_returns_empty_for_missing_file(tmp_path):
    history_file = tmp_path / "nonexistent.jsonl"
    with patch("src.reporting.history_tracker.HISTORY_PATH", history_file):
        result = load_history()
    assert result == []


def test_load_history_returns_all_runs(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    for i in range(4):
        _write_run(history_file, run_id=f"run-{i:03d}")

    with patch("src.reporting.history_tracker.HISTORY_PATH", history_file):
        runs = load_history()

    assert len(runs) == 4


def test_load_history_last_n(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    for i in range(5):
        _write_run(history_file, run_id=f"run-{i:03d}")

    with patch("src.reporting.history_tracker.HISTORY_PATH", history_file):
        runs = load_history(last_n=3)

    assert len(runs) == 3
    assert runs[0]["run_id"] == "run-002"
    assert runs[-1]["run_id"] == "run-004"


def test_load_history_preserves_order(tmp_path):
    history_file = tmp_path / "metrics_log.jsonl"
    ids = ["run-A", "run-B", "run-C"]
    for rid in ids:
        _write_run(history_file, run_id=rid)

    with patch("src.reporting.history_tracker.HISTORY_PATH", history_file):
        runs = load_history()

    assert [r["run_id"] for r in runs] == ids
