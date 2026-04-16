"""Load and validate eval test datasets from JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RagSample:
    """One RAG eval record — question + ground truth + (optionally) pre-cached answer/contexts."""
    question: str
    ground_truth: str
    answer: str = ""
    contexts: list[str] = field(default_factory=list)


@dataclass
class AgentSample:
    """One agent eval record — diff + known real bugs + (optionally) pre-cached agent comments."""
    pr_id: str
    description: str
    diff: str
    known_bugs: list[str]
    agent_comments: list[str] = field(default_factory=list)


def load_rag_dataset(path: str | Path) -> list[RagSample]:
    """
    Load RAG testset from JSON.
    Expected format: list of objects with keys: question, ground_truth.
    Optional keys: answer, contexts (pre-cached).
    """
    path = Path(path)
    if not path.exists():
        return []

    with open(path) as f:
        records = json.load(f)

    samples = []
    for r in records:
        samples.append(RagSample(
            question=r["question"],
            ground_truth=r["ground_truth"],
            answer=r.get("answer", ""),
            contexts=r.get("contexts", []),
        ))
    return samples


def load_agent_dataset(path: str | Path) -> list[AgentSample]:
    """
    Load agent testset from JSON.
    Expected format: list of objects with keys: pr_id, description, diff, known_bugs.
    Optional key: agent_comments (pre-cached).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Agent testset not found: {path}")

    with open(path) as f:
        records = json.load(f)

    samples = []
    for r in records:
        samples.append(AgentSample(
            pr_id=r["pr_id"],
            description=r.get("description", ""),
            diff=r["diff"],
            known_bugs=r["known_bugs"],
            agent_comments=r.get("agent_comments", []),
        ))
    return samples
