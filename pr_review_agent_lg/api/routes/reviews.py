"""
POST /reviews       — trigger a PR review, returns thread_id immediately.
GET  /reviews/{id}  — poll for status and results.

Agent runs in a background thread via run_in_executor so POST returns in <10ms.
"""
import uuid
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from api.schemas import ReviewRequest, ReviewResponse, ReviewStatusResponse
from api import status_store
from agent.graph import graph

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run_review(thread_id: str, initial_state: dict) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    loop = asyncio.get_event_loop()

    def _stream() -> None:
        try:
            for _ in graph.stream(initial_state, config, stream_mode="updates"):
                pass  # state is collected via checkpointer

            final = graph.get_state(config).values
            report = final.get("critic_report")
            results = final.get("agent_results") or []

            status_store.set_status(thread_id, {
                "thread_id":     thread_id,
                "status":        "completed",
                "verdict":       final.get("verdict"),
                "critic_report": report.model_dump() if report else None,
                "agent_results": [r.model_dump() for r in results],
                "review_id":     final.get("review_id"),
            })
            logger.info("Review complete — thread=%s  verdict=%s", thread_id, final.get("verdict"))

        except Exception as e:
            logger.error("Review failed — thread=%s  error=%s", thread_id, e)
            status_store.set_status(thread_id, {
                "thread_id": thread_id,
                "status":    "failed",
                "error":     str(e),
            })

    await loop.run_in_executor(None, _stream)


@router.post("/reviews", response_model=ReviewResponse)
async def start_review(request: ReviewRequest, background_tasks: BackgroundTasks):
    if not request.pr_url and not request.diff:
        raise HTTPException(status_code=400, detail="Either pr_url or diff must be provided")

    thread_id = str(uuid.uuid4())
    initial_state = {
        "pr_url":         request.pr_url or "",
        "diff":           request.diff or "",
        "agent_results":  [],
        "iteration_count": 0,
    }

    status_store.set_status(thread_id, {"thread_id": thread_id, "status": "processing"})
    background_tasks.add_task(_run_review, thread_id, initial_state)
    logger.info("Review started — thread=%s  pr_url=%s", thread_id, request.pr_url)

    return ReviewResponse(thread_id=thread_id, status="processing")


@router.get("/reviews/{thread_id}", response_model=ReviewStatusResponse)
async def get_review_status(thread_id: str):
    data = status_store.get_status(thread_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return ReviewStatusResponse(**data)
