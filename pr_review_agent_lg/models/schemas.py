"""
Pydantic models for typed inter-agent communication.
Carried over from v1 — all agents communicate through these structs.
"""
from __future__ import annotations
from typing import Literal, Optional
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
    """Raw structured output returned by each specialist via LLM."""
    findings: list[Finding]


class AgentResult(BaseModel):
    """Wrapper that includes which agent produced the findings and any error."""
    agent: Literal["security", "logic", "style"]
    findings: list[Finding]
    error: Optional[str] = None
    tokens_used: int = 0
    duration_seconds: float = 0.0


class CriticReport(BaseModel):
    """Final output from the Critic — deduplicated, ranked, with verdict."""
    findings: list[Finding]
    summary: str
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "NEEDS_DISCUSSION"]
    verdict_reason: str
