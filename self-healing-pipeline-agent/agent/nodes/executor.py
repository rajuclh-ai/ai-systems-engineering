"""
Executor Node — fix execution.
RESTART strategy calls the real Flink REST API (FLINK_REST_URL required).
All other strategies remain simulated.
If human rejected, falls back to ALERT_ONLY.
Tracks restart_attempts to support verification retry loop.
"""
import logging
from datetime import datetime
from models.remediation import FixStrategy
from models.execution import ExecutionResult, ExecutionStatus
from agent.tools.flink_client import get_flink_client
from agent.state import AgentState

logger = logging.getLogger(__name__)

MAX_RESTART_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Action handlers — one per strategy
# ---------------------------------------------------------------------------

def _restart_job(pipeline_id: str, metrics: dict) -> tuple[str, str | None]:
    """Returns (action_taken, new_job_id). new_job_id is None for simulated strategies."""
    job_id = metrics.get("job_id", pipeline_id)
    client = get_flink_client()
    result = client.restart_job(job_id=job_id, pipeline_id=pipeline_id)
    return result.action_taken, result.new_job_id


def _reroute_traffic(pipeline_id: str, metrics: dict) -> tuple[str, None]:
    consumer_group = metrics.get("consumer_group", "unknown")
    return f"Rerouted traffic from {consumer_group} to backup consumer group on {pipeline_id}", None


def _apply_schema_patch(pipeline_id: str, metrics: dict) -> tuple[str, None]:
    received = metrics.get("received_version", "unknown")
    return f"Applied schema patch to align {pipeline_id} to version {received}", None


def _quarantine_topic(pipeline_id: str, metrics: dict) -> tuple[str, None]:
    field = metrics.get("field_name", "unknown")
    return f"Quarantined {pipeline_id} due to null spike in field '{field}'", None


def _redeploy_from_savepoint(pipeline_id: str, metrics: dict) -> tuple[str, None]:
    savepoint_path = metrics.get("savepoint_path", "latest")
    job_id = metrics.get("job_id", pipeline_id)
    return f"Redeployed job {job_id} from savepoint {savepoint_path}", None


def _alert_only(pipeline_id: str, metrics: dict) -> tuple[str, None]:
    return f"Alert raised for {pipeline_id} — no automated action taken", None


# Maps FixStrategy → handler function
_ACTION_HANDLERS = {
    FixStrategy.RESTART:            _restart_job,
    FixStrategy.REROUTE:            _reroute_traffic,
    FixStrategy.SCHEMA_PATCH:       _apply_schema_patch,
    FixStrategy.QUARANTINE:         _quarantine_topic,
    FixStrategy.SAVEPOINT_REDEPLOY: _redeploy_from_savepoint,
    FixStrategy.LAG_CATCHUP:        _redeploy_from_savepoint,
    FixStrategy.ALERT_ONLY:         _alert_only,
}


# ---------------------------------------------------------------------------
# Executor Node
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> dict:
    """
    Execute the remediation plan.
    - Increments restart_attempts for RESTART strategy.
    - Returns new_job_id in execution_result for verification.
    - Falls back to ALERT_ONLY if human rejected or attempts exhausted.
    """
    plan = state["remediation_plan"]
    event = state["event"]
    human_decision = state.get("human_decision")
    restart_attempts = state.get("restart_attempts", 0)

    # Human rejected — ALERT_ONLY, no execution
    if human_decision == "REJECT":
        action_taken = f"Human rejected fix — alert raised for {event.pipeline_id}, no action taken"
        result = ExecutionResult(
            strategy_executed=plan.strategy.value,
            status=ExecutionStatus.SKIPPED,
            action_taken=action_taken,
            timestamp=datetime.utcnow(),
        )
        logger.info("[EXECUTOR] REJECTED by human  → action=SKIPPED  pipeline=%s", event.pipeline_id)
        return {"execution_result": result, "restart_attempts": restart_attempts}

    # Retry exhausted — fall back to ALERT_ONLY
    if plan.strategy == FixStrategy.RESTART and restart_attempts >= MAX_RESTART_ATTEMPTS:
        action_taken = (
            f"RESTART exhausted after {restart_attempts} attempts on {event.pipeline_id} "
            f"— alert raised, manual intervention required"
        )
        result = ExecutionResult(
            strategy_executed=plan.strategy.value,
            status=ExecutionStatus.FAILED,
            action_taken=action_taken,
            timestamp=datetime.utcnow(),
        )
        logger.info("[EXECUTOR] RESTART exhausted after %d attempts  pipeline=%s",
                    restart_attempts, event.pipeline_id)
        return {"execution_result": result, "restart_attempts": restart_attempts}

    # Execute the fix
    handler = _ACTION_HANDLERS.get(plan.strategy, _alert_only)
    action_taken, new_job_id = handler(event.pipeline_id, event.metrics)

    # Increment attempt counter for RESTART
    if plan.strategy == FixStrategy.RESTART:
        restart_attempts += 1

    result = ExecutionResult(
        strategy_executed=plan.strategy.value,
        status=ExecutionStatus.SUCCESS,
        action_taken=action_taken,
        timestamp=datetime.utcnow(),
        new_job_id=new_job_id,
    )

    logger.info("[EXECUTOR] attempt=%d  strategy=%s  → %s",
                restart_attempts, plan.strategy.value, action_taken)

    return {"execution_result": result, "restart_attempts": restart_attempts}
