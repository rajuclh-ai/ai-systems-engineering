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
    status: str              # "processing" — agent runs in background


class IncidentStatusResponse(BaseModel):
    thread_id: str
    pipeline_id: Optional[str] = None
    status: str              # "processing" | "resolved" | "awaiting_approval" | "failed" | "rejected"
    anomaly_type: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    current_node: Optional[str] = None       # node currently executing (None when idle)
    nodes_completed: Optional[list] = None   # ordered list of node names that have finished
    error: Optional[str] = None


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
