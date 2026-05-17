"""
Tests for individual agent nodes.
All LLM calls are mocked via conftest fixtures.
"""
import pytest
from agent.nodes.fetcher import fetcher_node
from agent.nodes.security import security_node
from agent.nodes.logic import logic_node
from agent.nodes.style import style_node
from agent.nodes.critic import critic_node, _deduplicate
from agent.nodes.post_comment import post_comment_node, _format_comment
from agent.nodes.learning import learning_node
from models.schemas import Finding, AgentResult, CriticReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs):
    base = {
        "pr_url": None,
        "diff": None,
        "agent_results": [],
        "critic_report": None,
        "verdict": None,
        "review_id": None,
        "iteration_count": 0,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Fetcher node
# ---------------------------------------------------------------------------

def test_fetcher_passthrough_if_diff_exists(sample_diff):
    """If diff is already in state, fetcher returns empty dict (no-op)."""
    state = _make_state(diff=sample_diff)
    result = fetcher_node(state)
    assert result == {}


def test_fetcher_raises_without_url_or_diff():
    state = _make_state()
    with pytest.raises(ValueError, match="Either pr_url or diff"):
        fetcher_node(state)


def test_fetcher_fetches_diff_from_github(sample_diff):
    from unittest.mock import patch
    state = _make_state(pr_url="https://github.com/owner/repo/pull/1")
    with patch("agent.nodes.fetcher.fetch_pr_diff", return_value=sample_diff) as mock_fetch:
        result = fetcher_node(state)
    assert result["diff"] == sample_diff
    mock_fetch.assert_called_once_with("https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# Security node
# ---------------------------------------------------------------------------

def test_security_node_returns_agent_result(sample_diff, mock_llm_security, sample_finding):
    state = _make_state(diff=sample_diff)
    result = security_node(state)

    assert "agent_results" in result
    assert len(result["agent_results"]) == 1
    ar = result["agent_results"][0]
    assert ar.agent == "security"
    assert len(ar.findings) == 1
    assert ar.findings[0].category == "security"


def test_security_node_sets_agent_field(sample_diff, mock_llm_security):
    state = _make_state(diff=sample_diff)
    result = security_node(state)
    for f in result["agent_results"][0].findings:
        assert f.agent == "security"
        assert f.category == "security"


def test_security_node_error_returns_empty_result(sample_diff):
    from unittest.mock import patch, MagicMock
    from langchain_core.runnables import RunnableLambda
    state = _make_state(diff=sample_diff)
    with patch("agent.nodes.security.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        def _raise(x): raise Exception("API error")
        mock_llm.with_structured_output.return_value = RunnableLambda(_raise)
        mock_cls.return_value = mock_llm
        result = security_node(state)

    ar = result["agent_results"][0]
    assert ar.agent == "security"
    assert ar.findings == []
    assert ar.error == "API error"


# ---------------------------------------------------------------------------
# Logic node
# ---------------------------------------------------------------------------

def test_logic_node_returns_agent_result(sample_diff, mock_llm_logic):
    state = _make_state(diff=sample_diff)
    result = logic_node(state)
    assert "agent_results" in result
    ar = result["agent_results"][0]
    assert ar.agent == "logic"
    assert ar.tokens_used == 0


# ---------------------------------------------------------------------------
# Style node
# ---------------------------------------------------------------------------

def test_style_node_returns_agent_result(sample_diff, mock_llm_style):
    state = _make_state(diff=sample_diff)
    result = style_node(state)
    assert "agent_results" in result
    ar = result["agent_results"][0]
    assert ar.agent == "style"
    assert ar.tokens_used == 0


# ---------------------------------------------------------------------------
# Critic node — deduplication
# ---------------------------------------------------------------------------

def test_deduplicate_keeps_highest_severity():
    """Same file+line+category → keep the highest severity."""
    findings = [
        Finding(file_name="f.py", line_number=1, severity="LOW",
                category="security", message="low", suggestion="fix", agent="security"),
        Finding(file_name="f.py", line_number=1, severity="HIGH",
                category="security", message="high", suggestion="fix", agent="security"),
        Finding(file_name="f.py", line_number=1, severity="MEDIUM",
                category="security", message="med", suggestion="fix", agent="security"),
    ]
    result = _deduplicate(findings)
    assert len(result) == 1
    assert result[0].severity == "HIGH"


def test_deduplicate_keeps_different_categories():
    """Same file+line but different categories → keep both."""
    findings = [
        Finding(file_name="f.py", line_number=1, severity="HIGH",
                category="security", message="sec", suggestion="fix", agent="security"),
        Finding(file_name="f.py", line_number=1, severity="HIGH",
                category="logic", message="log", suggestion="fix", agent="logic"),
    ]
    result = _deduplicate(findings)
    assert len(result) == 2


def test_deduplicate_sorts_by_severity():
    """Output is sorted HIGH → MEDIUM → LOW."""
    findings = [
        Finding(file_name="f.py", line_number=3, severity="LOW",
                category="style", message="s3", suggestion="fix", agent="style"),
        Finding(file_name="f.py", line_number=1, severity="HIGH",
                category="security", message="s1", suggestion="fix", agent="security"),
        Finding(file_name="f.py", line_number=2, severity="MEDIUM",
                category="logic", message="s2", suggestion="fix", agent="logic"),
    ]
    result = _deduplicate(findings)
    assert [f.severity for f in result] == ["HIGH", "MEDIUM", "LOW"]


def test_critic_node_returns_report(three_agent_results, mock_llm_critic, sample_critic_report):
    state = _make_state(agent_results=three_agent_results)
    result = critic_node(state)
    assert "critic_report" in result
    assert "verdict" in result
    assert result["verdict"] in ("APPROVE", "REQUEST_CHANGES", "NEEDS_DISCUSSION")


def test_critic_node_fallback_on_error(three_agent_results):
    """If LLM fails, critic falls back to raw deduplicated findings."""
    from unittest.mock import patch, MagicMock
    from langchain_core.runnables import RunnableLambda
    state = _make_state(agent_results=three_agent_results)
    with patch("agent.nodes.critic.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        def _raise(x): raise Exception("LLM down")
        mock_llm.with_structured_output.return_value = RunnableLambda(_raise)
        mock_cls.return_value = mock_llm
        result = critic_node(state)

    assert result["verdict"] == "NEEDS_DISCUSSION"
    assert "Critic failed" in result["critic_report"].verdict_reason


# ---------------------------------------------------------------------------
# Post comment node
# ---------------------------------------------------------------------------

def test_post_comment_skips_without_report():
    state = _make_state()
    result = post_comment_node(state)
    assert result == {}


def test_post_comment_skips_without_pr_url(sample_critic_report):
    state = _make_state(critic_report=sample_critic_report)
    result = post_comment_node(state)
    assert result == {}


def test_format_comment_contains_verdict(sample_critic_report):
    comment = _format_comment(sample_critic_report)
    assert "REQUEST_CHANGES" in comment
    assert sample_critic_report.summary in comment
    assert sample_critic_report.verdict_reason in comment


def test_format_comment_contains_findings(sample_critic_report):
    comment = _format_comment(sample_critic_report)
    f = sample_critic_report.findings[0]
    assert f.file_name in comment
    assert str(f.line_number) in comment
    assert f.message in comment


# ---------------------------------------------------------------------------
# Learning node
# ---------------------------------------------------------------------------

def test_learning_node_skips_without_report():
    state = _make_state()
    result = learning_node(state)
    assert result == {}


def test_learning_node_stores_review(sample_critic_report, tmp_path):
    """Learning node writes a ReviewRow to SQLite."""
    import contextlib
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.db import Base

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextlib.contextmanager
    def _test_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    from unittest.mock import patch
    with patch("agent.nodes.learning.get_session", _test_get_session):
        state = _make_state(
            critic_report=sample_critic_report,
            pr_url="https://github.com/owner/repo/pull/1",
        )
        result = learning_node(state)

    assert "review_id" in result
    assert result["review_id"] is not None
