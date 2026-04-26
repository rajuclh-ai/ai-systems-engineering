"""
Tests for the Monitor Node.
Rule-based classification — no LLM calls, fully deterministic.
Each test verifies one FR2 rule.
"""
import pytest
from agent.nodes.monitor import monitor_node


# ---------------------------------------------------------------------------
# LAG_SPIKE tests
# ---------------------------------------------------------------------------

def test_lag_spike_classified(lag_spike_event):
    """LAG_SPIKE event is classified correctly."""
    result = monitor_node({"event": lag_spike_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "lag_spike"


def test_lag_spike_critical_when_over_5x_threshold(lag_spike_event):
    """current_lag 5.7x threshold → CRITICAL."""
    result = monitor_node({"event": lag_spike_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "critical"


def test_lag_spike_high_cpu_combination_detected(lag_spike_event):
    """cpu_pct 94 > 80 → combination LAG_SPIKE_HIGH_CPU."""
    result = monitor_node({"event": lag_spike_event, "messages": [], "iteration_count": 0})
    assert result["combination"] == "lag_spike_high_cpu"


def test_lag_spike_no_combination_when_cpu_normal(lag_spike_event):
    """cpu_pct below 80 → no combination."""
    lag_spike_event.metrics["cpu_pct"] = 50
    result = monitor_node({"event": lag_spike_event, "messages": [], "iteration_count": 0})
    assert result["combination"] == "none"


# ---------------------------------------------------------------------------
# RESTART_STORM tests
# ---------------------------------------------------------------------------

def test_restart_storm_classified(restart_storm_event):
    """RESTART_STORM event is classified correctly."""
    result = monitor_node({"event": restart_storm_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "restart_storm"


def test_restart_storm_critical_when_over_2x_threshold(restart_storm_event):
    """restart_count 14 vs threshold 5 = 2.8x → CRITICAL."""
    result = monitor_node({"event": restart_storm_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "critical"


def test_restart_storm_high_when_over_threshold(restart_storm_event):
    """restart_count just over threshold → HIGH."""
    restart_storm_event.metrics["restart_count"] = 6   # just over threshold of 5
    result = monitor_node({"event": restart_storm_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "high"


def test_restart_storm_lag_spike_combination_detected(restart_storm_event):
    """restart_count > 3x threshold → RESTART_STORM_LAG_SPIKE combination."""
    # restart_count=14, threshold=5 → 14 > 15? No → 14 > 5*3=15? No.
    # Set restart_count=16 to exceed 3x threshold of 5
    restart_storm_event.metrics["restart_count"] = 16
    result = monitor_node({"event": restart_storm_event, "messages": [], "iteration_count": 0})
    assert result["combination"] == "restart_storm_lag_spike"


def test_restart_storm_no_combination_below_3x(restart_storm_event):
    """restart_count ≤ 3x threshold → no combination."""
    restart_storm_event.metrics["restart_count"] = 14   # 14 < 5*3=15
    result = monitor_node({"event": restart_storm_event, "messages": [], "iteration_count": 0})
    assert result["combination"] == "none"


# ---------------------------------------------------------------------------
# SCHEMA_DRIFT tests
# ---------------------------------------------------------------------------

def test_schema_drift_classified(schema_drift_event):
    """SCHEMA_DRIFT event is classified correctly."""
    result = monitor_node({"event": schema_drift_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "schema_drift"


def test_schema_drift_critical_when_100pct_affected(schema_drift_event):
    """affected_pct 100% → CRITICAL."""
    result = monitor_node({"event": schema_drift_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "critical"


def test_schema_drift_high_when_over_50pct(schema_drift_event):
    """affected_pct 75% → HIGH."""
    schema_drift_event.metrics["affected_pct"] = 75.0
    result = monitor_node({"event": schema_drift_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "high"


def test_schema_drift_medium_when_partial(schema_drift_event):
    """affected_pct 20% → MEDIUM."""
    schema_drift_event.metrics["affected_pct"] = 20.0
    result = monitor_node({"event": schema_drift_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "medium"


# ---------------------------------------------------------------------------
# NULL_SPIKE tests
# ---------------------------------------------------------------------------

def test_null_spike_classified(null_spike_event):
    """NULL_SPIKE event is classified correctly."""
    result = monitor_node({"event": null_spike_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "null_spike"


def test_null_spike_critical_when_over_50pct(null_spike_event):
    """null_rate 55% → CRITICAL (FR2: > 50% = CRITICAL)."""
    null_spike_event.metrics["null_rate"] = 0.55
    result = monitor_node({"event": null_spike_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "critical"


def test_null_spike_high_when_over_20pct(null_spike_event):
    """null_rate 25% → HIGH."""
    null_spike_event.metrics["null_rate"] = 0.25
    result = monitor_node({"event": null_spike_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "high"


# ---------------------------------------------------------------------------
# JOB_FAILURE tests
# ---------------------------------------------------------------------------

def test_job_failure_classified(job_failure_event):
    """JOB_FAILURE event is classified correctly."""
    result = monitor_node({"event": job_failure_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "job_failure"


def test_job_failure_high_on_first_failure(job_failure_event):
    """restart_count 1 (first failure) → HIGH."""
    result = monitor_node({"event": job_failure_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "high"


def test_job_failure_medium_on_zero_restarts(job_failure_event):
    """restart_count 0 → MEDIUM."""
    job_failure_event.metrics["restart_count"] = 0
    result = monitor_node({"event": job_failure_event, "messages": [], "iteration_count": 0})
    assert result["severity"] == "medium"


# ---------------------------------------------------------------------------
# UNKNOWN test
# ---------------------------------------------------------------------------

def test_unknown_event_type(lag_spike_event):
    """Unrecognised event_type → UNKNOWN anomaly, no severity."""
    lag_spike_event.event_type = "some_unknown_event"
    result = monitor_node({"event": lag_spike_event, "messages": [], "iteration_count": 0})
    assert result["anomaly_type"] == "unknown"
    assert result["severity"] is None
