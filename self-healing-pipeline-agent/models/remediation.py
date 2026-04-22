from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class FixStrategy(str, Enum):
    RESTART = "restart"
    REROUTE = "reroute"
    SCHEMA_PATCH = "schema_patch"
    QUARANTINE = "quarantine"
    SAVEPOINT_REDEPLOY = "savepoint_redeploy"
    LAG_CATCHUP = "lag_catchup"
    ALERT_ONLY = "alert_only"


class RemediationPlan(BaseModel):
    strategy: FixStrategy
    description: str
    estimated_impact: str
    risk_score: float = Field(ge=0.0, le=1.0)
    rollback_plan: str
    steps: List[str]
