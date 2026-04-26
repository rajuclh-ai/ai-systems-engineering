"""
API request and response Pydantic models.
Typed contracts for every endpoint — no raw dicts at the API boundary.
"""
from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# POST /incidents
# ---------------------------------------------------------------------------

class TriggerIncidentRequest(BaseModel):
    pipeline_id: str
    event_type: str
    metrics: dict
    raw_log: Optional[str] = None


class TriggerIncidentResponse(BaseModel):
    thread_id: str
    pipeline_id: str
    anomaly_type: Optional[str]
    severity: Optional[str]
    status: str              # "resolved" | "awaiting_approval" | "failed"
    risk_score: Optional[float]


# ---------------------------------------------------------------------------
# POST /approval/{thread_id}
# ---------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    decision: str            # APPROVE | REJECT


class ApprovalResponse(BaseModel):
    thread_id: str
    decision: str
    strategy_executed: Optional[str]
    outcome: Optional[str]
    incident_id: Optional[str]
