"""Tests for supervisor/pipeline.py — deduplication logic and error handling."""
import pytest
from models.schemas import Finding, AgentResult
from supervisor.pipeline import deduplicate_findings


def make_finding(**kwargs) -> Finding:
    defaults = dict(
        file_name="app.py",
        line_number=42,
        severity="HIGH",
        category="security",
        message="Issue found",
        suggestion="Fix it",
        agent="security",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


# ── deduplicate_findings ───────────────────────────────────────────────────────

def test_dedup_empty_list():
    assert deduplicate_findings([]) == []


def test_dedup_no_duplicates():
    findings = [
        make_finding(line_number=1, category="security", agent="security"),
        make_finding(line_number=2, category="logic", agent="logic"),
        make_finding(line_number=3, category="style", agent="style"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 3


def test_dedup_same_line_same_category_keeps_highest_severity():
    """Same file + line + category — only the HIGH should survive."""
    findings = [
        make_finding(line_number=42, category="security", severity="MEDIUM", agent="security"),
        make_finding(line_number=42, category="security", severity="HIGH", agent="logic"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 1
    assert result[0].severity == "HIGH"


def test_dedup_same_line_same_category_keeps_high_over_low():
    findings = [
        make_finding(line_number=10, category="logic", severity="LOW", agent="logic"),
        make_finding(line_number=10, category="logic", severity="HIGH", agent="logic"),
        make_finding(line_number=10, category="logic", severity="MEDIUM", agent="logic"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 1
    assert result[0].severity == "HIGH"


def test_dedup_same_line_different_category_keeps_both():
    """Same file + line but different categories — both should survive."""
    findings = [
        make_finding(line_number=42, category="security", agent="security", severity="HIGH"),
        make_finding(line_number=42, category="style", agent="style", severity="LOW"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 2


def test_dedup_different_files_same_line_same_category_keeps_both():
    """Same line + same category but different files — both should survive."""
    findings = [
        make_finding(file_name="auth.py", line_number=10, category="security", agent="security"),
        make_finding(file_name="utils.py", line_number=10, category="security", agent="security"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 2


def test_dedup_result_sorted_by_severity():
    """Output must be HIGH → MEDIUM → LOW."""
    findings = [
        make_finding(line_number=1, severity="LOW", category="style", agent="style"),
        make_finding(line_number=2, severity="HIGH", category="security", agent="security"),
        make_finding(line_number=3, severity="MEDIUM", category="logic", agent="logic"),
    ]
    result = deduplicate_findings(findings)
    severities = [f.severity for f in result]
    assert severities == ["HIGH", "MEDIUM", "LOW"]


def test_dedup_three_agents_same_line_same_category():
    """All 3 agents flag line 42 as security — only the highest severity survives."""
    findings = [
        make_finding(line_number=42, category="security", severity="LOW", agent="security"),
        make_finding(line_number=42, category="security", severity="HIGH", agent="logic"),
        make_finding(line_number=42, category="security", severity="MEDIUM", agent="style"),
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 1
    assert result[0].severity == "HIGH"


# ── AgentResult error handling ─────────────────────────────────────────────────

def test_agent_result_error_still_has_empty_findings():
    r = AgentResult(agent="security", findings=[], error="OpenAI timeout")
    assert r.findings == []
    assert r.error == "OpenAI timeout"
    assert r.tokens_used == 0


def test_agent_result_partial_success():
    """Pipeline should handle mix of successful and failed agents."""
    results = [
        AgentResult(agent="security", findings=[make_finding()], tokens_used=100),
        AgentResult(agent="logic", findings=[], error="timeout"),
        AgentResult(agent="style", findings=[make_finding(category="style", agent="style", severity="LOW")], tokens_used=80),
    ]
    total_tokens = sum(r.tokens_used for r in results)
    all_findings = [f for r in results for f in r.findings]

    assert total_tokens == 180
    assert len(all_findings) == 2
    assert any(r.error for r in results)
