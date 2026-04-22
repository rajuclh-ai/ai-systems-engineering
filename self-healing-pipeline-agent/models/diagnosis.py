from typing import List
from pydantic import BaseModel, Field


class RootCause(BaseModel):
    primary_cause: str
    contributing_factors: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str]
    recommended_action: str
