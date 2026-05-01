from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionResult(BaseModel):
    strategy_executed: str
    status: ExecutionStatus
    action_taken: str
    timestamp: datetime
    new_job_id: Optional[str] = None   # set by FlinkRestClient after RESTART resubmit


class IncidentRecord(BaseModel):
    incident_id: str
    pipeline_id: str
    timestamp: datetime
    anomaly_type: str
    root_cause: str
    strategy_executed: str
    outcome: str               # success | failed | skipped
    human_approved: bool
