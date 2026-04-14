"""Tests for Pydantic models in models/schemas.py."""
import pytest
from pydantic import ValidationError
from models.schemas import Finding, AgentFindings, AgentResult, CriticReport


def make_finding(**kwargs) -> Finding:
    defaults = dict(
        file_name="app.py",
        line_number=42,
        severity="HIGH",
        category="security",
        message="Hardcoded password detected",
        suggestion="Use environment variables instead",
        agent="security",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


# ── Finding ────────────────────────────────────────────────────────────────────

def test_finding_valid():
    f = make_finding()
    assert f.file_name == "app.py"
    assert f.line_number == 42
    assert f.severity == "HIGH"
    assert f.category == "security"
    assert f.agent == "security"


def test_finding_all_severities():
    for sev in ["HIGH", "MEDIUM", "LOW"]:
        f = make_finding(severity=sev)
        assert f.severity == sev


def test_finding_all_categories():
    for cat, agent in [("security", "security"), ("logic", "logic"), ("style", "style")]:
        f = make_finding(category=cat, agent=agent)
        assert f.category == cat


def test_finding_invalid_severity():
    with pytest.raises(ValidationError):
        make_finding(severity="CRITICAL")


def test_finding_invalid_category():
    with pytest.raises(ValidationError):
        make_finding(category="performance")


def test_finding_invalid_agent():
    with pytest.raises(ValidationError):
        make_finding(agent="critic")


def test_finding_negative_line_number():
    # Pydantic allows negative ints — verify it doesn't raise (constraint not enforced)
    f = make_finding(line_number=-1)
    assert f.line_number == -1


# ── AgentFindings ──────────────────────────────────────────────────────────────

def test_agent_findings_empty():
    af = AgentFindings(findings=[])
    assert af.findings == []


def test_agent_findings_multiple():
    af = AgentFindings(findings=[make_finding(), make_finding(line_number=10, severity="LOW")])
    assert len(af.findings) == 2


# ── AgentResult ────────────────────────────────────────────────────────────────

def test_agent_result_success():
    r = AgentResult(agent="security", findings=[make_finding()])
    assert r.agent == "security"
    assert len(r.findings) == 1
    assert r.error is None
    assert r.tokens_used == 0
    assert r.duration_seconds == 0.0


def test_agent_result_with_error():
    r = AgentResult(agent="logic", findings=[], error="timeout")
    assert r.error == "timeout"
    assert r.findings == []


def test_agent_result_with_tokens():
    r = AgentResult(agent="style", findings=[], tokens_used=250, duration_seconds=3.5)
    assert r.tokens_used == 250
    assert r.duration_seconds == 3.5


def test_agent_result_invalid_agent():
    with pytest.raises(ValidationError):
        AgentResult(agent="critic", findings=[])


# ── CriticReport ───────────────────────────────────────────────────────────────

def test_critic_report_approve():
    report = CriticReport(
        findings=[],
        summary="No issues found.",
        verdict="APPROVE",
        verdict_reason="Clean diff with no findings.",
    )
    assert report.verdict == "APPROVE"
    assert report.findings == []


def test_critic_report_request_changes():
    report = CriticReport(
        findings=[make_finding()],
        summary="One HIGH severity issue found.",
        verdict="REQUEST_CHANGES",
        verdict_reason="Hardcoded credentials must be removed.",
    )
    assert report.verdict == "REQUEST_CHANGES"
    assert len(report.findings) == 1


def test_critic_report_needs_discussion():
    report = CriticReport(
        findings=[make_finding(severity="LOW")],
        summary="Minor style issues only.",
        verdict="NEEDS_DISCUSSION",
        verdict_reason="Borderline — discuss with the team.",
    )
    assert report.verdict == "NEEDS_DISCUSSION"


def test_critic_report_invalid_verdict():
    with pytest.raises(ValidationError):
        CriticReport(
            findings=[],
            summary="x",
            verdict="REJECT",
            verdict_reason="x",
        )
