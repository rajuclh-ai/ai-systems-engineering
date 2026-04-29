"""
Executor Node — fix execution.
RESTART strategy calls the real Flink REST API when FLINK_REST_URL is set.
All other strategies remain simulated.
If human rejected, falls back to ALERT_ONLY.
"""
import logging
from datetime import datetime
from models.remediation import FixStrategy
from models.execution import ExecutionResult, ExecutionStatus
from agent.tools.flink_client import get_flink_client
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action handlers — one per strategy
# ---------------------------------------------------------------------------

def _restart_job(pipeline_id: str, metrics: dict) -> str:
    job_id = metrics.get("job_id", pipeline_id)
    client = get_flink_client()
    return client.restart_job(job_id=job_id, pipeline_id=pipeline_id)


def _reroute_traffic(pipeline_id: str, metrics: dict) -> str:
    consumer_group = metrics.get("consumer_group", "unknown")
    return f"Rerouted traffic from {consumer_group} to backup consumer group on {pipeline_id}"


def _apply_schema_patch(pipeline_id: str, metrics: dict) -> str:
    received = metrics.get("received_version", "unknown")
    return f"Applied schema patch to align {pipeline_id} to version {received}"


def _quarantine_topic(pipeline_id: str, metrics: dict) -> str:
    field = metrics.get("field_name", "unknown")
    return f"Quarantined {pipeline_id} due to null spike in field '{field}'"


def _redeploy_from_savepoint(pipeline_id: str, metrics: dict) -> str:
    savepoint_path = metrics.get("savepoint_path", "latest")
    job_id = metrics.get("job_id", pipeline_id)
    return f"Redeployed job {job_id} from savepoint {savepoint_path}"


def _alert_only(pipeline_id: str, metrics: dict) -> str:
    return f"Alert raised for {pipeline_id} — no automated action taken"


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
    Execute the remediation plan (simulated).
    Falls back to ALERT_ONLY if human rejected.
    """
    plan = state["remediation_plan"]
    event = state["event"]
    human_decision = state.get("human_decision")

    # Human rejected — fall back to ALERT_ONLY
    if human_decision == "REJECT":
        action_taken = f"Human rejected fix — alert raised for {event.pipeline_id}, no action taken"
        result = ExecutionResult(
            strategy_executed=plan.strategy.value,
            status=ExecutionStatus.SKIPPED,
            action_taken=action_taken,
            timestamp=datetime.utcnow(),
        )
        logger.info("[EXECUTOR] REJECTED by human  → action=SKIPPED  pipeline=%s", event.pipeline_id)
        return {"execution_result": result}

    # Execute the fix
    handler = _ACTION_HANDLERS.get(plan.strategy, _alert_only)
    action_taken = handler(event.pipeline_id, event.metrics)

    result = ExecutionResult(
        strategy_executed=plan.strategy.value,
        status=ExecutionStatus.SUCCESS,
        action_taken=action_taken,
        timestamp=datetime.utcnow(),
    )

    logger.info("[EXECUTOR] strategy=%s  → %s", plan.strategy.value, action_taken)

    return {"execution_result": result}
