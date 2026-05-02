"""
POST /approval/{thread_id} — human submits APPROVE or REJECT.
Resumes a paused graph after human reviews high-risk remediation.
Uses graph.stream() so remaining nodes are tracked in the status store
and visible in the demo script.
"""
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from api.schemas import ApprovalRequest, ApprovalResponse
from api import status_store
from agent.graph import graph

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_DECISIONS = {"APPROVE", "REJECT"}


@router.post("/approval/{thread_id}", response_model=ApprovalResponse)
async def submit_approval(thread_id: str, request: ApprovalRequest):
    """
    Resume a paused agent after human reviews high-risk remediation.
    Streams remaining nodes so the demo can show them completing in real time.
    """
    if request.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision '{request.decision}'. Must be APPROVE or REJECT."
        )

    config = {"configurable": {"thread_id": thread_id}}

    try:
        graph.update_state(config, {"human_decision": request.decision})

        # Capture base nodes before resumption so we can append without duplication
        base_nodes: list[str] = (status_store.get_status(thread_id) or {}).get("nodes_completed") or []

        def _stream_approval() -> dict:
            approval_nodes: list[str] = []
            final_values: dict = {}
            for chunk in graph.stream(None, config, stream_mode="updates"):
                node_name = list(chunk.keys())[0]
                node_output = chunk[node_name] or {}
                final_values.update(node_output)
                approval_nodes.append(node_name)

                current = status_store.get_status(thread_id) or {}
                status_store.set_status(thread_id, {
                    **current,
                    "current_node": node_name,
                    "nodes_completed": base_nodes + list(approval_nodes),
                })
            return final_values

        loop = asyncio.get_event_loop()
        final_values = await loop.run_in_executor(None, _stream_approval)

        execution_result = final_values.get("execution_result")
        strategy = execution_result.strategy_executed if execution_result else None
        outcome = execution_result.status.value if execution_result else None

        # Write final status
        current = status_store.get_status(thread_id) or {}
        status_store.set_status(thread_id, {
            **current,
            "status": "resolved" if request.decision == "APPROVE" else "rejected",
            "current_node": None,
        })

        logger.info(
            "Approval processed — thread=%s decision=%s outcome=%s",
            thread_id, request.decision, outcome
        )

        return ApprovalResponse(
            thread_id=thread_id,
            decision=request.decision,
            strategy_executed=strategy,
            outcome=outcome,
            incident_id=final_values.get("incident_id"),
        )

    except Exception as e:
        logger.error("Approval failed — thread=%s error=%s", thread_id, str(e))
        raise HTTPException(status_code=500, detail=f"Approval error: {str(e)}")
