"""
ReviewState — the single shared state object that flows through the graph.

Key design decision: agent_results uses Annotated[list, operator.add] reducer.
Each specialist node returns {"agent_results": [its_result]} and the reducer
appends automatically — no hardcoded security/logic/style fields.
Adding a 4th specialist later requires zero state schema changes.
"""
from __future__ import annotations
from typing import Annotated, Optional
from operator import add
from typing_extensions import TypedDict
from models.schemas import AgentResult, CriticReport


class ReviewState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    pr_url:         Optional[str]
    diff:           Optional[str]

    # ── Specialist outputs ─────────────────────────────────────────────────
    # Reducer appends each AgentResult as Send() branches complete in parallel.
    # AgentResult.agent ("security" | "logic" | "style") identifies the source.
    agent_results:  Annotated[list[AgentResult], add]

    # ── Critic output ──────────────────────────────────────────────────────
    critic_report:  Optional[CriticReport]
    verdict:        Optional[str]       # APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION

    # ── Learning ───────────────────────────────────────────────────────────
    review_id:      Optional[str]

    # ── Metadata ───────────────────────────────────────────────────────────
    iteration_count: int
