"""API request/response Pydantic models."""
from typing import Optional
from pydantic import BaseModel
from models.schemas import AgentResult, CriticReport


class ReviewRequest(BaseModel):
    pr_url: Optional[str] = None
    diff:   Optional[str] = None


class ReviewResponse(BaseModel):
    thread_id: str
    status:    str          # "processing"


class ReviewStatusResponse(BaseModel):
    thread_id:     str
    status:        str      # "processing" | "completed" | "failed"
    verdict:       Optional[str] = None
    critic_report: Optional[CriticReport] = None
    agent_results: Optional[list[AgentResult]] = None
    review_id:     Optional[str] = None
    error:         Optional[str] = None
