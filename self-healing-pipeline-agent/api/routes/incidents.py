"""
POST /incidents — trigger the agent with a pipeline failure event.
GET  /incidents/{thread_id}/status — poll for result.

Agent runs in a background task (thread pool executor) so POST returns immediately.
graph.stream() emits one chunk per completed node — status store is updated in real
time so the demo script can show node-by-node progress as it happens.
Client polls GET /incidents/{thread_id}/status until status != "processing".
"""
import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException
from api.schemas import TriggerIncidentRequest, TriggerIncidentResponse, IncidentStatusResponse
from api import status_store
from models.events import PipelineEvent
from agent.graph import graph

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run_agent(thread_id: str, pipeline_id: str, initial_state: dict) -> None:
    """Background task — streams the agent node by node, updates status store after each node."""
    config = {"configurable": {"thread_id": thread_id}}
    loop = asyncio.get_event_loop()

    def _stream_graph() -> None:
        nodes_completed: list[str] = []
        try:
            for chunk in graph.stream(initial_state, config, stream_mode="updates"):
                node_name = list(chunk.keys())[0]
                nodes_completed.append(node_name)
                current = status_store.get_status(thread_id) or {}
                status_store.set_status(thread_id, {
                    **current,
                    "current_node": node_name,
                    "nodes_completed": list(nodes_completed),
                })

            # Stream complete — check if graph paused at interrupt (HITL) or fully done
            graph_state = graph.get_state(config)
            is_paused = bool(graph_state.next)
            final_values = graph_state.values

            status = "awaiting_approval" if is_paused else "resolved"
            current = status_store.get_status(thread_id) or {}
            status_store.set_status(thread_id, {
                **current,
                "status": status,
                "current_node": None,
                "anomaly_type": final_values.get("anomaly_type") or None,
                "severity": final_values.get("severity") or None,
                "risk_score": final_values.get("risk_score"),
            })
            logger.info("Agent complete — thread=%s status=%s nodes=%s", thread_id, status, nodes_completed)

        except Exception as e:
            logger.error("Agent failed — thread=%s error=%s", thread_id, str(e))
            status_store.set_status(thread_id, {
                "thread_id": thread_id,
                "pipeline_id": pipeline_id,
                "status": "failed",
                "current_node": None,
                "nodes_completed": nodes_completed,
                "error": str(e),
            })

    await loop.run_in_executor(None, _stream_graph)


@router.post("/incidents", response_model=TriggerIncidentResponse)
async def trigger_incident(request: TriggerIncidentRequest, background_tasks: BackgroundTasks):
    """
    Accept a pipeline failure event. Returns immediately with thread_id.
    Poll GET /incidents/{thread_id}/status for the result.
    """
    thread_id = str(uuid.uuid4())

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

    # Write initial status before spawning so GET is immediately valid
    status_store.set_status(thread_id, {
        "thread_id": thread_id,
        "pipeline_id": request.pipeline_id,
        "status": "processing",
        "current_node": None,
        "nodes_completed": [],
    })

    background_tasks.add_task(_run_agent, thread_id, request.pipeline_id, initial_state)
    logger.info("Incident accepted — thread=%s pipeline=%s", thread_id, request.pipeline_id)

    return TriggerIncidentResponse(
        thread_id=thread_id,
        pipeline_id=request.pipeline_id,
        status="processing",
    )


@router.get("/incidents/{thread_id}/status", response_model=IncidentStatusResponse)
async def get_incident_status(thread_id: str):
    """Poll for agent result. Status: processing → resolved | awaiting_approval | failed."""
    data = status_store.get_status(thread_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return IncidentStatusResponse(**data)
