"""
Test fixtures and LLM mocks.
All LLM calls are mocked — tests run with OPENAI_API_KEY=test-key.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from models.events import (
    PipelineEvent, AnomalyType, Severity,
    LagMetrics, RestartStormMetrics, SchemaMetrics,
    NullMetrics, JobMetrics,
)
from models.diagnosis import RootCause
from models.remediation import RemediationPlan, FixStrategy
from models.execution import ExecutionResult, ExecutionStatus


# ---------------------------------------------------------------------------
# Sample pipeline events
# ---------------------------------------------------------------------------

@pytest.fixture
def lag_spike_event():
    return PipelineEvent(
        pipeline_id="clickstream-flink-job-03",
        timestamp=datetime(2026, 4, 22, 10, 0, 0),
        event_type="consumer_lag_spike",
        metrics={
            "current_lag": 2850000,
            "threshold": 500000,
            "growth_rate": 125000,
            "partition_count": 12,
            "consumer_group": "flink-clickstream-processor",
            "cpu_pct": 94,
        },
        raw_log="Consumer lag exceeded threshold: 2850000 messages",
    )


@pytest.fixture
def restart_storm_event():
    return PipelineEvent(
        pipeline_id="payments-flink-job-01",
        timestamp=datetime(2026, 4, 22, 10, 5, 0),
        event_type="restart_storm",
        metrics={
            "job_id": "flink-job-payments-01",
            "restart_count": 14,
            "window_minutes": 10,
            "restart_threshold": 5,
            "savepoint_path": "s3://pipeline-checkpoints/job-01/sp-20260422-1000",
            "error_code": "OOM",
            "error_message": "Java heap space exceeded",
        },
        raw_log="Job restarted 14 times in 10 minutes",
    )


@pytest.fixture
def schema_drift_event():
    return PipelineEvent(
        pipeline_id="transactions-pipeline-01",
        timestamp=datetime(2026, 4, 22, 10, 10, 0),
        event_type="schema_validation_error",
        metrics={
            "expected_version": "v4",
            "received_version": "v5",
            "affected_pct": 100.0,
            "new_fields": ["merchant_category_code"],
            "removed_fields": [],
        },
        raw_log="SchemaRegistryException: Incompatible schema evolution",
    )


@pytest.fixture
def null_spike_event():
    return PipelineEvent(
        pipeline_id="user-events-pipeline-02",
        timestamp=datetime(2026, 4, 22, 10, 15, 0),
        event_type="null_spike",
        metrics={
            "field_name": "user_id",
            "null_rate": 0.45,
            "baseline_null_rate": 0.02,
            "affected_pipelines": ["user-events-pipeline-02"],
        },
        raw_log="Null rate for user_id exceeded baseline by 22x",
    )


@pytest.fixture
def job_failure_event():
    return PipelineEvent(
        pipeline_id="enrichment-job-05",
        timestamp=datetime(2026, 4, 22, 10, 20, 0),
        event_type="job_failure",
        metrics={
            "job_id": "flink-enrichment-05",
            "error_code": "NPE",
            "restart_count": 1,
            "last_checkpoint": "cp-20260422-0950",
            "error_message": "NullPointerException in EnrichmentMapper",
        },
        raw_log="Job failed with NullPointerException",
    )


# ---------------------------------------------------------------------------
# Sample model outputs
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_root_cause():
    return RootCause(
        primary_cause="Consumer lag caused by upstream throughput spike exceeding partition capacity",
        contributing_factors=[
            "CPU at 94% — processing bottleneck",
            "Lag growing at 125k messages/min",
            "12 partitions insufficient for current load",
        ],
        confidence=0.87,
        evidence=["current_lag 5.7x threshold", "cpu_pct > 80%"],
        recommended_action="Reroute traffic to reduce load — restart ruled out due to high CPU",
    )


@pytest.fixture
def sample_remediation_plan():
    return RemediationPlan(
        strategy=FixStrategy.REROUTE,
        description="Reroute traffic away from overloaded consumer group",
        estimated_impact="Lag stabilises within 5 minutes",
        risk_score=0.6,
        rollback_plan="Restore original routing configuration",
        steps=[
            "Identify backup consumer group",
            "Redirect 50% of partitions to backup group",
            "Monitor lag for 5 minutes",
            "Complete reroute if lag stabilising",
        ],
    )


@pytest.fixture
def sample_execution_result():
    return ExecutionResult(
        strategy_executed="reroute",
        status=ExecutionStatus.SUCCESS,
        action_taken="Traffic rerouted from clickstream-flink-job-03 to backup consumer group",
        timestamp=datetime(2026, 4, 22, 10, 1, 0),
    )


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Mock LangChain LLM — returns a configurable response."""
    with patch("langchain_openai.ChatOpenAI") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance
