"""
Pydantic models for typed inter-agent communication.

All agents communicate exclusively through these structs — no free text passing.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class Finding(BaseModel):
    """A single issue found by a specialist agent."""
    file_name: str
    line_number: int
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    category: Literal["security", "logic", "style"]
    message: str
    suggestion: str
    agent: Literal["security", "logic", "style"]


class AgentFindings(BaseModel):
    """Raw output returned by each specialist agent via OpenAI structured outputs."""
    findings: list[Finding]


class AgentResult(BaseModel):
    """Wrapper that includes which agent produced the findings and any error."""
    agent: Literal["security", "logic", "style"]
    findings: list[Finding]
    error: str | None = None
    tokens_used: int = 0
    duration_seconds: float = 0.0


class CriticReport(BaseModel):
    """Final output from the Critic agent — deduplicated, ranked, with verdict."""
    findings: list[Finding]
    summary: str
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "NEEDS_DISCUSSION"]
    verdict_reason: str
