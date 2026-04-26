"""
Monitor Node — rule-based anomaly classification.
No LLM. Fully deterministic.
Implements FR2 severity rules and combination detection.
"""
import logging
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity rules per failure type (FR2)
# ---------------------------------------------------------------------------

def _classify_lag_spike(metrics: dict) -> tuple[str, str]:
    current_lag = metrics.get("current_lag", 0)
    threshold = metrics.get("threshold", 1)
    ratio = current_lag / threshold

    if ratio > 5:
        severity = "critical"
    elif ratio > 2:
        severity = "high"
    else:
        severity = "medium"

    return "lag_spike", severity


def _classify_restart_storm(metrics: dict) -> tuple[str, str]:
    restart_count = metrics.get("restart_count", 0)
    threshold = metrics.get("restart_threshold", 1)

    if restart_count > threshold * 2:
        severity = "critical"
    elif restart_count > threshold:
        severity = "high"
    else:
        severity = "medium"

    return "restart_storm", severity


def _classify_schema_drift(metrics: dict) -> tuple[str, str]:
    affected_pct = metrics.get("affected_pct", 0)

    if affected_pct == 100:
        severity = "critical"
    elif affected_pct > 50:
        severity = "high"
    else:
        severity = "medium"

    return "schema_drift", severity


def _classify_null_spike(metrics: dict) -> tuple[str, str]:
    null_rate = metrics.get("null_rate", 0)

    if null_rate > 0.5:
        severity = "critical"
    elif null_rate > 0.2:
        severity = "high"
    else:
        severity = "medium"

    return "null_spike", severity


def _classify_job_failure(metrics: dict) -> tuple[str, str]:
    restart_count = metrics.get("restart_count", 0)

    if restart_count > 0:
        severity = "high"
    else:
        severity = "medium"

    return "job_failure", severity


# ---------------------------------------------------------------------------
# Combination detection (FR2 — 2 cases only)
# ---------------------------------------------------------------------------

def _detect_combination(anomaly_type: str, metrics: dict) -> str:
    if anomaly_type == "lag_spike":
        cpu_pct = metrics.get("cpu_pct", 0)
        if cpu_pct > 80:
            return "lag_spike_high_cpu"

    if anomaly_type == "restart_storm":
        # RESTART_STORM_LAG_SPIKE: restarts are so frequent they're causing lag
        # Detected when restart_count is more than 3x the threshold
        restart_count = metrics.get("restart_count", 0)
        restart_threshold = metrics.get("restart_threshold", 1)
        if restart_count > restart_threshold * 3:
            return "restart_storm_lag_spike"

    return "none"


# ---------------------------------------------------------------------------
# Monitor Node
# ---------------------------------------------------------------------------

# Maps event_type strings to classifier functions
_CLASSIFIERS = {
    "consumer_lag_spike":    _classify_lag_spike,
    "restart_storm":         _classify_restart_storm,
    "schema_drift":          _classify_schema_drift,
    "schema_validation_error": _classify_schema_drift,   # Kafka registry error maps to same classifier
    "null_spike":            _classify_null_spike,
    "job_failure":           _classify_job_failure,
}


def monitor_node(state: AgentState) -> dict:
    """
    Classify the incoming pipeline event.
    Returns anomaly_type, severity, combination.
    """
    event = state["event"]
    event_type = event.event_type
    metrics = event.metrics

    classifier = _CLASSIFIERS.get(event_type)

    if classifier is None:
        logger.info("[MONITOR] pipeline=%s  event=%s  → UNKNOWN (no classifier)", event.pipeline_id, event_type)
        return {
            "anomaly_type": "unknown",
            "severity": None,
            "combination": "none",
        }

    anomaly_type, severity = classifier(metrics)
    combination = _detect_combination(anomaly_type, metrics)

    combo_str = f"  combination={combination}" if combination != "none" else ""
    logger.info("[MONITOR] pipeline=%s  event=%s  → anomaly=%s  severity=%s%s",
                event.pipeline_id, event_type, anomaly_type, severity, combo_str)

    return {
        "anomaly_type": anomaly_type,
        "severity": severity,
        "combination": combination,
    }
