"""Tests for markdown report generation — pure Python, no LLM calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.reporting.markdown_reporter import generate_markdown, save_report


RAG_AGGREGATES = {
    "faithfulness": 0.36,
    "answer_relevance": 0.47,
    "context_recall": 0.64,
    "context_precision": 0.75,
}

RAG_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevance": 0.70,
    "context_recall": 0.65,
    "context_precision": 0.65,
}

AGENT_AGGREGATES = {
    "bug_recall": 1.0,
    "false_positive_rate": 0.10,
    "comment_quality": 0.61,
}

AGENT_THRESHOLDS = {
    "bug_recall": 0.70,
    "false_positive_rate": 0.40,
    "comment_quality": 0.60,
}


def _make_report(overall="FAIL", cost=0.0034, tokens=22970):
    return generate_markdown(
        run_id="2026-04-16T13-30-46Z",
        model="gpt-4o-mini",
        rag_aggregates=RAG_AGGREGATES,
        rag_thresholds=RAG_THRESHOLDS,
        agent_aggregates=AGENT_AGGREGATES,
        agent_thresholds=AGENT_THRESHOLDS,
        overall=overall,
        cost_usd=cost,
        total_tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Content checks
# ---------------------------------------------------------------------------

def test_report_contains_run_id():
    md = _make_report()
    assert "2026-04-16T13-30-46Z" in md


def test_report_contains_model():
    md = _make_report()
    assert "gpt-4o-mini" in md


def test_report_contains_overall_pass():
    md = _make_report(overall="PASS")
    assert "PASS" in md


def test_report_contains_overall_fail():
    md = _make_report(overall="FAIL")
    assert "FAIL" in md


def test_report_rag_metrics_present():
    md = _make_report()
    for metric in RAG_AGGREGATES:
        assert metric in md


def test_report_agent_metrics_present():
    md = _make_report()
    for metric in AGENT_AGGREGATES:
        assert metric in md


def test_report_failing_rag_metrics_show_x_icon():
    md = _make_report()
    # faithfulness 0.36 < threshold 0.70 → should show ❌
    assert "❌" in md


def test_report_passing_rag_metric_shows_check_icon():
    md = _make_report()
    # context_precision 0.75 >= threshold 0.65 → should show ✅
    assert "✅" in md


def test_report_false_positive_rate_uses_lower_is_better():
    md = _make_report()
    # false_positive_rate 0.10 <= threshold 0.40 → PASS (lower is better)
    # The row should show ✅ for false_positive_rate
    lines = [l for l in md.splitlines() if "false_positive_rate" in l]
    assert len(lines) == 1
    assert "✅" in lines[0]


def test_report_is_valid_markdown_table():
    md = _make_report()
    # Every metric row must have 4 pipe-separated columns
    for line in md.splitlines():
        if line.startswith("| ") and "Metric" not in line and "---" not in line:
            assert line.count("|") >= 4


def test_report_cost_and_tokens_present():
    md = _make_report(cost=0.0034, tokens=22970)
    assert "0.0034" in md
    assert "22,970" in md


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------

def test_save_report_writes_files(tmp_path):
    md = _make_report()
    with patch("src.reporting.markdown_reporter.REPORTS_PATH", tmp_path):
        path = save_report(md, "2026-04-16T13-30-46Z")

    assert (tmp_path / "latest_report.md").exists()
    assert (tmp_path / "2026-04-16T13-30-46Z.md").exists()


def test_save_report_returns_latest_path(tmp_path):
    md = _make_report()
    with patch("src.reporting.markdown_reporter.REPORTS_PATH", tmp_path):
        path = save_report(md, "some-run")

    assert path.name == "latest_report.md"


def test_save_report_content_matches(tmp_path):
    md = _make_report()
    with patch("src.reporting.markdown_reporter.REPORTS_PATH", tmp_path):
        save_report(md, "run-xyz")

    assert (tmp_path / "latest_report.md").read_text() == md
