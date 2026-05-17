"""
Shared pytest fixtures.
All LLM calls are mocked — tests pass with OPENAI_API_KEY=test-key.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Set test env vars before any imports that trigger dotenv loading
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

from langchain_core.runnables import RunnableLambda
from models.schemas import Finding, AgentResult, CriticReport, AgentFindings


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_finding():
    return Finding(
        file_name="app.py",
        line_number=42,
        severity="HIGH",
        category="security",
        message="Hardcoded API key detected",
        suggestion="Use environment variable instead",
        agent="security",
    )


@pytest.fixture
def sample_agent_result(sample_finding):
    return AgentResult(
        agent="security",
        findings=[sample_finding],
        tokens_used=100,
        duration_seconds=1.5,
    )


@pytest.fixture
def sample_critic_report(sample_finding):
    return CriticReport(
        findings=[sample_finding],
        summary="One critical security finding detected.",
        verdict="REQUEST_CHANGES",
        verdict_reason="HIGH severity finding requires immediate attention.",
    )


@pytest.fixture
def sample_diff():
    return """\
diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,8 @@
 import os
+
+API_KEY = "sk-hardcoded-secret-key"
+
 def main():
     pass
"""


@pytest.fixture
def three_agent_results():
    """One AgentResult per specialist — simulates merged state after Send() fan-out."""
    return [
        AgentResult(agent="security", findings=[
            Finding(file_name="app.py", line_number=3, severity="HIGH",
                    category="security", message="Hardcoded secret",
                    suggestion="Use env var", agent="security"),
        ], tokens_used=100, duration_seconds=1.2),
        AgentResult(agent="logic", findings=[
            Finding(file_name="app.py", line_number=10, severity="MEDIUM",
                    category="logic", message="Missing null check",
                    suggestion="Check for None before access", agent="logic"),
        ], tokens_used=90, duration_seconds=1.1),
        AgentResult(agent="style", findings=[
            Finding(file_name="app.py", line_number=15, severity="LOW",
                    category="style", message="Poor variable name",
                    suggestion="Use descriptive name", agent="style"),
        ], tokens_used=60, duration_seconds=0.8),
    ]


# ---------------------------------------------------------------------------
# LLM mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_security(sample_finding):
    """Mock ChatOpenAI structured output for security node."""
    with patch("agent.nodes.security.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        return_value = AgentFindings(findings=[sample_finding])
        mock_llm.with_structured_output.return_value = RunnableLambda(lambda x: return_value)
        mock_cls.return_value = mock_llm
        yield mock_cls


@pytest.fixture
def mock_llm_logic():
    """Mock ChatOpenAI structured output for logic node — no findings."""
    with patch("agent.nodes.logic.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        return_value = AgentFindings(findings=[])
        mock_llm.with_structured_output.return_value = RunnableLambda(lambda x: return_value)
        mock_cls.return_value = mock_llm
        yield mock_cls


@pytest.fixture
def mock_llm_style():
    """Mock ChatOpenAI structured output for style node — no findings."""
    with patch("agent.nodes.style.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        return_value = AgentFindings(findings=[])
        mock_llm.with_structured_output.return_value = RunnableLambda(lambda x: return_value)
        mock_cls.return_value = mock_llm
        yield mock_cls


@pytest.fixture
def mock_llm_critic(sample_critic_report):
    """Mock ChatOpenAI structured output for critic node."""
    with patch("agent.nodes.critic.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        report = sample_critic_report
        mock_llm.with_structured_output.return_value = RunnableLambda(lambda x: report)
        mock_cls.return_value = mock_llm
        yield mock_cls
