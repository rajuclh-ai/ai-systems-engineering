"""
Verification Node — confirms the fix worked after RESTART execution.

Polls Flink GET /jobs/{new_job_id} every 5s for up to 60s.
  - Job reaches RUNNING within 60s → verification_status = "verified"
  - Timeout                        → verification_status = "failed" (triggers retry)
  - Non-RESTART strategy           → verification_status = "skipped" (pass-through)
"""
import logging
import time
from agent.tools.flink_client import FlinkRestClient, get_flink_client
from agent.state import AgentState
from models.remediation import FixStrategy

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 60


def verification_node(state: AgentState) -> dict:
    """
    Verify the RESTART fix worked by polling Flink for the new job status.
    Non-RESTART strategies are skipped — no real system was touched.
    """
    plan = state["remediation_plan"]
    execution_result = state.get("execution_result")

    # Non-RESTART strategies — nothing real to verify
    if plan.strategy != FixStrategy.RESTART:
        logger.info("[VERIFICATION] strategy=%s  → skipped (not a real execution)",
                    plan.strategy.value)
        return {"verification_status": "skipped"}

    # No execution result or execution already failed/skipped — skip
    if not execution_result or not execution_result.new_job_id:
        logger.info("[VERIFICATION] no new_job_id in execution_result  → skipped")
        return {"verification_status": "skipped"}

    new_job_id = execution_result.new_job_id
    client: FlinkRestClient = get_flink_client()

    logger.info("[VERIFICATION] polling Flink for job %s  (timeout=%ds  interval=%ds)",
                new_job_id, POLL_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS)

    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECONDS:
        try:
            status = client.get_job_status(new_job_id)
            logger.info("[VERIFICATION] elapsed=%ds  job=%s  status=%s",
                        elapsed, new_job_id, status)

            if status == "RUNNING":
                logger.info("[VERIFICATION] job %s is RUNNING  → verified", new_job_id)
                return {"verification_status": "verified"}

            if status in ("FAILED", "CANCELED"):
                logger.info("[VERIFICATION] job %s reached terminal state=%s  → failed",
                            new_job_id, status)
                return {"verification_status": "failed"}

        except Exception as e:
            logger.warning("[VERIFICATION] poll error  job=%s  error=%s", new_job_id, str(e))

        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    logger.info("[VERIFICATION] timeout after %ds  job=%s  → failed", POLL_TIMEOUT_SECONDS, new_job_id)
    return {"verification_status": "failed"}
