"""
POST /approval/{thread_id} — human submits APPROVE or REJECT.
Resumes a paused graph after human reviews high-risk remediation.
"""
import logging
from fastapi import APIRouter, HTTPException
from api.schemas import ApprovalRequest, ApprovalResponse
from agent.graph import graph

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_DECISIONS = {"APPROVE", "REJECT"}


@router.post("/approval/{thread_id}", response_model=ApprovalResponse)
async def submit_approval(thread_id: str, request: ApprovalRequest):
    """
    Resume a paused agent after human reviews high-risk remediation.
    Injects human_decision into state, then resumes graph execution.
    """
    if request.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision '{request.decision}'. Must be APPROVE or REJECT."
        )

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Inject human decision into the paused state
        graph.update_state(
            config,
            {"human_decision": request.decision},
        )

        # Resume graph from where it paused
        result = graph.invoke(None, config)

        execution_result = result.get("execution_result")
        strategy = execution_result.strategy_executed if execution_result else None
        outcome = execution_result.status.value if execution_result else None

        logger.info(
            "Approval processed — thread=%s decision=%s outcome=%s",
            thread_id, request.decision, outcome
        )

        return ApprovalResponse(
            thread_id=thread_id,
            decision=request.decision,
            strategy_executed=strategy,
            outcome=outcome,
            incident_id=result.get("incident_id"),
        )

    except Exception as e:
        logger.error("Approval failed — thread=%s error=%s", thread_id, str(e))
        raise HTTPException(status_code=500, detail=f"Approval error: {str(e)}")
