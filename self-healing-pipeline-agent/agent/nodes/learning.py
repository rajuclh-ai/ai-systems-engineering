"""
Learning Node — writes resolved incident to SQLite.
Every incident (success or failure) is stored for future Diagnosis queries.
"""
import uuid
import logging
from models.db import get_session, IncidentRow, init_db
from agent.state import AgentState

logger = logging.getLogger(__name__)


def learning_node(state: AgentState) -> dict:
    """
    Store the resolved incident in SQLite.
    Runs for every incident — including UNKNOWN and SKIPPED.
    """
    event = state["event"]
    root_cause = state.get("root_cause")
    remediation_plan = state.get("remediation_plan")
    execution_result = state.get("execution_result")
    human_decision = state.get("human_decision")

    incident_id = str(uuid.uuid4())

    # Determine what to store — handle cases where nodes were skipped
    primary_cause = root_cause.primary_cause if root_cause else "Unknown — classified as UNKNOWN anomaly"
    strategy = remediation_plan.strategy.value if remediation_plan else "none"
    outcome = execution_result.status.value if execution_result else "skipped"
    human_approved = human_decision == "APPROVE" if human_decision else False

    init_db()

    try:
        with get_session() as session:
            row = IncidentRow(
                id=incident_id,
                pipeline_id=event.pipeline_id,
                timestamp=event.timestamp,
                anomaly_type=state.get("anomaly_type", "unknown"),
                root_cause=primary_cause,
                strategy_executed=strategy,
                outcome=outcome,
                human_approved=human_approved,
            )
            session.add(row)
            session.commit()

        logger.info("[LEARNING] stored incident  pipeline=%s  strategy=%s  outcome=%s  id=%s",
                    event.pipeline_id, strategy, outcome, incident_id)
        return {"incident_id": incident_id, "stored": True}

    except Exception as e:
        logger.error("Failed to store incident — %s", str(e))
        return {"incident_id": incident_id, "stored": False}
