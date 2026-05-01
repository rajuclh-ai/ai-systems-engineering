"""
POST /incidents — trigger the agent with a pipeline failure event.
"""
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from api.schemas import TriggerIncidentRequest, TriggerIncidentResponse
from models.events import PipelineEvent
from agent.graph import graph

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/incidents", response_model=TriggerIncidentResponse)
async def trigger_incident(request: TriggerIncidentRequest):
    """
    Trigger the self-healing agent with a pipeline failure event.
    Returns immediately with thread_id and initial classification.
    Status is "awaiting_approval" if risk > 0.7, "resolved" otherwise.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Build PipelineEvent from request
    event = PipelineEvent(
        pipeline_id=request.pipeline_id,
        timestamp=datetime.utcnow(),
        event_type=request.event_type,
        metrics=request.metrics,
        raw_log=request.raw_log,
    )

    initial_state = {
        "event": event,
        "messages": [],
        "iteration_count": 0,
        "restart_attempts": 0,
    }

    try:
        result = graph.invoke(initial_state, config)

        # Graph paused at human_checkpoint (high risk)
        requires_approval = result.get("requires_approval", False)
        status = "awaiting_approval" if requires_approval else "resolved"

        return TriggerIncidentResponse(
            thread_id=thread_id,
            pipeline_id=request.pipeline_id,
            anomaly_type=result.get("anomaly_type"),
            severity=result.get("severity"),
            status=status,
            risk_score=result.get("risk_score"),
        )

    except Exception as e:
        logger.error("Agent failed for pipeline=%s error=%s", request.pipeline_id, str(e))
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
