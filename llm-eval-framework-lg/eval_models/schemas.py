"""Data contracts shared across the eval framework."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# RAG pipeline data
# ---------------------------------------------------------------------------

@dataclass
class RagSample:
    """One RAG eval record — question + ground truth loaded from dataset."""
    question: str
    ground_truth: str


@dataclass
class EnrichedRagSample:
    """RagSample after calling the live RAG pipeline — has answer + retrieved chunks."""
    question: str
    ground_truth: str
    answer: str
    contexts: list[str]
    tokens_used: int = 0


@dataclass
class RagQuestionScore:
    """Per-question RAGAS metric scores."""
    question: str
    faithfulness: float
    answer_relevance: float
    context_recall: float
    context_precision: float


# ---------------------------------------------------------------------------
# Agent pipeline data
# ---------------------------------------------------------------------------

@dataclass
class AgentSample:
    """One agent eval record — diff + known bugs + optional pre-cached comments."""
    pr_id: str
    description: str
    diff: str
    known_bugs: list[str]
    agent_comments: list[str] = field(default_factory=list)


@dataclass
class AgentPRScore:
    """Per-PR scores from the three LLM judge chains."""
    pr_id: str
    bug_recall: float           # fraction of known bugs caught
    false_positive_rate: float  # fraction of comments that are non-issues
    comment_quality: float      # average quality score (0.0–1.0)
    bugs_caught: int
    bugs_missed: int
    false_positives: int


# ---------------------------------------------------------------------------
# Top-level result — one per sub-graph, merged by the Annotated[list, add] reducer
# ---------------------------------------------------------------------------

@dataclass
class EvalSubResult:
    """Result returned by a completed sub-graph (RAG or Agent)."""
    target: str                 # "rag" | "agent"
    aggregates: dict[str, float]
    tokens_used: int = 0
