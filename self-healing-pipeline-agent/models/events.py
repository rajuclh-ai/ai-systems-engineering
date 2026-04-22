from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class AnomalyType(str, Enum):
    SCHEMA_DRIFT = "schema_drift"
    LAG_SPIKE = "lag_spike"
    JOB_FAILURE = "job_failure"
    NULL_SPIKE = "null_spike"
    RESTART_STORM = "restart_storm"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Combination(str, Enum):
    LAG_SPIKE_HIGH_CPU = "lag_spike_high_cpu"
    RESTART_STORM_LAG_SPIKE = "restart_storm_lag_spike"
    NONE = "none"


# Typed metrics per failure type

class SchemaMetrics(BaseModel):
    expected_version: str
    received_version: str
    affected_pct: float
    new_fields: List[str] = []
    removed_fields: List[str] = []


class LagMetrics(BaseModel):
    current_lag: int
    threshold: int
    growth_rate: int           # messages per minute
    partition_count: int
    consumer_group: str
    cpu_pct: Optional[float] = None


class JobMetrics(BaseModel):
    job_id: str
    error_code: str
    restart_count: int
    last_checkpoint: Optional[str] = None
    error_message: str


class NullMetrics(BaseModel):
    field_name: str
    null_rate: float
    baseline_null_rate: float
    affected_pipelines: List[str] = []


class RestartStormMetrics(BaseModel):
    job_id: str
    restart_count: int
    window_minutes: int
    restart_threshold: int
    last_savepoint: Optional[str] = None
    savepoint_path: Optional[str] = None   # s3 path
    error_code: str
    error_message: str


class PipelineEvent(BaseModel):
    pipeline_id: str
    timestamp: datetime
    event_type: str
    metrics: dict              # raw metrics dict — typed per failure in nodes
    raw_log: Optional[str] = None
