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


def _get_field(obj, *keys, default=""):
    """Get a field from a Pydantic object or a serialized dict — handles both."""
    for key in keys:
        if obj is None:
            return default
        if hasattr(obj, key):
            obj = getattr(obj, key)
        elif isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return default
    return obj if obj is not None else default


def _strategy_str(plan) -> str:
    """Extract strategy string from RemediationPlan object or dict."""
    raw = _get_field(plan, "strategy", default=None)
    if raw is None:
        return "unknown"
    if hasattr(raw, "value"):
        return raw.value
    if isinstance(raw, dict):
        return raw.get("value") or str(raw)
    return str(raw)


def _extract_node_detail(node_name: str, values: dict, accumulated: dict) -> dict:
    """
    Return structured detail for a node: {received: [...], label: str, output: [...]}.
    `values`      — keys this node returned (the chunk update)
    `accumulated` — full merged state up to and including this node
                    (initialized with initial_state so Monitor can read the event)
    Handles both live Pydantic objects and LangGraph-serialized dicts.
    """
    try:
        # ── Monitor ────────────────────────────────────────────────────────
        if node_name == "monitor":
            event   = accumulated.get("event")
            pid     = _get_field(event, "pipeline_id", default="?")
            etype   = _get_field(event, "event_type",  default="?")
            metrics = _get_field(event, "metrics",     default={}) or {}

            anomaly  = values.get("anomaly_type") or "unknown"
            severity = values.get("severity")     or "unknown"
            risk     = values.get("risk_score")
            combo    = values.get("anomaly_combination") or values.get("combination") or None

            # Build received: pipeline/event header, then each metric on its own line
            received = [
                f"pipeline_id:   {pid}",
                f"event_type:    {etype}",
            ]
            if isinstance(metrics, dict) and metrics:
                for k, v in metrics.items():
                    received.append(f"  {k}:  {v}")
            elif metrics:
                received.append(f"  metrics:     {metrics}")

            # Build classifier explanation based on event type
            classifier_rules = {
                "job_failure":       "event_type='job_failure' → _classify_job_failure (rule-based, no LLM)",
                "consumer_lag_spike":"event_type='consumer_lag_spike' → _classify_lag_spike (rule-based, no LLM)",
                "schema_change":     "event_type='schema_change' → _classify_schema_drift (rule-based, no LLM)",
                "null_spike":        "event_type='null_spike' → _classify_null_spike (rule-based, no LLM)",
                "restart_storm":     "event_type='restart_storm' → _classify_restart_storm (rule-based, no LLM)",
            }
            classifier_hint = classifier_rules.get(etype, f"event_type='{etype}' → rule-based classifier")

            # Severity reasoning per anomaly type
            severity_reason = ""
            if isinstance(metrics, dict):
                if etype == "job_failure":
                    rc = metrics.get("restart_count", 0)
                    severity_reason = f"restart_count={rc} > 0 → severity: high (active crash, not first occurrence)" if int(rc or 0) > 0 else "restart_count=0 → severity: medium (first-time failure)"
                elif etype == "consumer_lag_spike":
                    lag = metrics.get("current_lag")
                    thresh = metrics.get("threshold")
                    cpu = metrics.get("cpu_pct")
                    if lag and thresh:
                        ratio = round(int(lag) / int(thresh), 1) if int(thresh) > 0 else "?"
                        severity_reason = f"current_lag={lag} / threshold={thresh} = {ratio}x threshold → severity: {severity}"
                        if cpu and int(cpu or 0) >= 90:
                            severity_reason += f"  |  cpu_pct={cpu}% ≥ 90 → combination: LAG_SPIKE_HIGH_CPU"
                elif etype == "restart_storm":
                    rc = metrics.get("restart_count", 0)
                    severity_reason = f"restart_count={rc} → classified as restart storm → severity: {severity}"

            # Downstream hint per anomaly
            downstream_hints = {
                "job_failure":    "JOB_FAILURE → Diagnosis → Remediation will select RESTART strategy",
                "lag_spike":      "LAG_SPIKE → Diagnosis → Remediation will select RESTART or REROUTE",
                "schema_drift":   "SCHEMA_DRIFT → Diagnosis → Remediation will select SCHEMA_PATCH",
                "null_spike":     "NULL_SPIKE → Diagnosis → Remediation will select QUARANTINE or ALERT_ONLY",
                "restart_storm":  "RESTART_STORM → Diagnosis → Remediation will select SAVEPOINT_REDEPLOY (risk > 0.7 → HITL)",
            }
            downstream = downstream_hints.get(anomaly, f"{anomaly.upper()} → Diagnosis node next")

            output = [
                f"anomaly_type:    {anomaly}",
                f"classifier:      {classifier_hint}",
            ]
            if severity_reason:
                output.append(f"severity:        {severity_reason}")
            else:
                output.append(f"severity:        {severity}")
            output.append("method:          deterministic rule-based — no LLM involved")
            if combo:
                output.append(f"combination:     {combo}")
            output.append(f"next:            {downstream}")

            return {
                "received": received,
                "label": "detected",
                "output": output,
            }

        # ── Diagnosis ──────────────────────────────────────────────────────
        if node_name == "diagnosis":
            anomaly  = accumulated.get("anomaly_type") or "?"
            severity = accumulated.get("severity")     or "?"
            similar  = values.get("similar_incidents") or []
            rc       = values.get("root_cause")

            cause   = str(_get_field(rc, "primary_cause",    default=""))
            conf    = _get_field(rc, "confidence",           default=None)
            factors = _get_field(rc, "contributing_factors", default=[]) or []
            evidence= _get_field(rc, "evidence",             default=[]) or []
            action  = str(_get_field(rc, "recommended_action", default=""))
            conf_str = f"{conf:.2f}" if isinstance(conf, float) else "?"

            received = [f"anomaly:      {anomaly} ({severity})"]
            if similar:
                received.append(f"history:      {len(similar)} similar past incident{'s' if len(similar)>1 else ''} found")
                for s in similar[:3]:
                    received.append(
                        f"              → {s.get('pipeline_id','?')}  "
                        f"{s.get('strategy','?')} → {s.get('outcome','?')}"
                    )
            else:
                received.append("history:      no similar incidents — first occurrence")

            output = [f"primary_cause:        {cause}"]
            if factors:
                output.append(f"contributing_factors: {' · '.join(str(f) for f in factors)}")
            if evidence:
                output.append(f"evidence:             {' · '.join(str(e) for e in evidence)}")
            output.append(f"confidence:           {conf_str}")
            if action:
                output.append(f"recommended_action:   {action}")

            return {"received": received, "label": "diagnosed", "output": output}

        # ── Remediation ────────────────────────────────────────────────────
        if node_name == "remediation":
            rc       = accumulated.get("root_cause")
            cause    = str(_get_field(rc, "primary_cause",      default=""))
            conf     = _get_field(rc, "confidence",             default=None)
            rec_act  = str(_get_field(rc, "recommended_action", default=""))
            conf_str = f"{conf:.2f}" if isinstance(conf, float) else "?"

            plan     = values.get("remediation_plan")
            risk     = values.get("risk_score") or 0
            requires = values.get("requires_approval", False)
            strategy = _strategy_str(plan)
            approval = "required (%.2f > 0.70 threshold)" % risk if requires else "not required — auto-executing"

            return {
                "received": [
                    f"root_cause:   {cause[:80]}",
                    f"confidence:   {conf_str}",
                    f"recommended:  {rec_act[:80]}" if rec_act else "",
                ],
                "label": "decided",
                "output": [
                    f"strategy:     {strategy}",
                    f"risk_score:   {risk:.2f}",
                    f"approval:     {approval}",
                ],
            }

        # ── Human Checkpoint ───────────────────────────────────────────────
        if node_name == "human_checkpoint":
            strategy = _strategy_str(accumulated.get("remediation_plan"))
            risk     = accumulated.get("risk_score")
            risk_str = f"{risk:.2f}" if risk is not None else "?"
            return {
                "received": [
                    f"strategy:     {strategy}",
                    f"risk_score:   {risk_str}  (threshold: 0.70 — approval required)",
                ],
                "label": "awaiting",
                "output": [
                    "human review required before execution",
                    "POST /approval/{thread_id}  with  APPROVE  or  REJECT",
                ],
            }

        # ── Executor ───────────────────────────────────────────────────────
        if node_name == "executor":
            strategy      = _strategy_str(accumulated.get("remediation_plan"))
            human_decision= accumulated.get("human_decision") or "N/A (auto)"
            er            = values.get("execution_result")
            action        = str(_get_field(er, "action_taken", default=""))
            status_raw    = _get_field(er, "status", default=None)
            status_str    = status_raw.value if hasattr(status_raw, "value") else str(status_raw or "")
            new_job_id    = _get_field(er, "new_job_id", default=None)

            output = [
                f"action:       {action}",
                f"status:       {status_str}",
            ]
            if new_job_id:
                output.append(f"new_job_id:   {new_job_id}")

            return {
                "received": [
                    f"strategy:       {strategy}",
                    f"human_decision: {human_decision}",
                ],
                "label": "executed",
                "output": output,
            }

        # ── Verification ───────────────────────────────────────────────────
        if node_name == "verification":
            strategy = _strategy_str(accumulated.get("remediation_plan"))
            vs       = values.get("verification_status") or ""
            new_jid  = _get_field(accumulated.get("execution_result"), "new_job_id", default=None)

            if vs == "verified":
                result = ["Flink job confirmed RUNNING ✓", f"polled GET /jobs/{new_jid} every 5s"]
            elif vs == "skipped":
                result = [
                    "status:  skipped",
                    f"reason:  {strategy} is a simulated strategy — no real Flink job to verify",
                    "note:    RESTART strategy triggers real polling (GET /jobs/{{id}} every 5s for 60s)",
                ]
            elif vs == "failed":
                result = ["job failed to reach RUNNING", "retry triggered → executor will re-attempt"]
            else:
                result = [f"status: {vs}"]

            received = [f"strategy:     {strategy}"]
            if new_jid:
                received.append(f"new_job_id:   {new_jid}")

            return {"received": received, "label": "result", "output": result}

        # ── Learning ───────────────────────────────────────────────────────
        if node_name == "learning":
            anomaly  = accumulated.get("anomaly_type") or "?"
            strategy = _strategy_str(accumulated.get("remediation_plan"))
            er       = accumulated.get("execution_result")
            status_r = _get_field(er, "status", default=None)
            outcome  = status_r.value if hasattr(status_r, "value") else str(status_r or "")
            approved = accumulated.get("human_decision") not in (None, "N/A", "REJECT")
            inc_id   = values.get("incident_id") or ""

            return {
                "received": [
                    f"anomaly:        {anomaly}",
                    f"strategy:       {strategy}",
                    f"outcome:        {outcome}",
                    f"human_approved: {approved}",
                ],
                "label": "stored",
                "output": [
                    f"incident_id:  {inc_id}",
                    "note:         used as context for future similar incidents on this pipeline",
                ],
            }

    except Exception:
        pass
    return {"received": [], "label": "output", "output": []}


async def _run_agent(thread_id: str, pipeline_id: str, initial_state: dict) -> None:
    """Background task — streams the agent node by node, updates status store after each node."""
    config = {"configurable": {"thread_id": thread_id}}
    loop = asyncio.get_event_loop()

    def _stream_graph() -> None:
        nodes_completed: list[str] = []
        node_details: dict = {}
        accumulated: dict = dict(initial_state)  # seed with event so Monitor can read metrics
        try:
            for chunk in graph.stream(initial_state, config, stream_mode="updates"):
                node_name = list(chunk.keys())[0]
                chunk_values = chunk[node_name] or {}
                accumulated.update(chunk_values)
                nodes_completed.append(node_name)
                node_details[node_name] = _extract_node_detail(node_name, chunk_values, accumulated)
                current = status_store.get_status(thread_id) or {}
                status_store.set_status(thread_id, {
                    **current,
                    "current_node": node_name,
                    "nodes_completed": list(nodes_completed),
                    "node_details": dict(node_details),
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
                "node_details": node_details,
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
                "node_details": node_details,
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
