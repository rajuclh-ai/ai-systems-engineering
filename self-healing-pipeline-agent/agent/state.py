from typing import TypedDict, Optional, List
from models.events import PipelineEvent
from models.diagnosis import RootCause
from models.remediation import RemediationPlan
from models.execution import ExecutionResult


class AgentState(TypedDict):
    # --- Input ---
    event: PipelineEvent

    # --- Monitor Node output ---
    anomaly_type: Optional[str]        # AnomalyType enum value
    severity: Optional[str]            # Severity enum value
    combination: Optional[str]         # Combination enum value

    # --- Diagnosis Node output ---
    root_cause: Optional[RootCause]
    similar_incidents: Optional[List[dict]]

    # --- Remediation Node output ---
    remediation_plan: Optional[RemediationPlan]
    risk_score: Optional[float]
    requires_approval: Optional[bool]

    # --- Human Checkpoint output ---
    human_decision: Optional[str]      # APPROVE | REJECT

    # --- Executor Node output ---
    execution_result: Optional[ExecutionResult]

    # --- Learning Node output ---
    incident_id: Optional[str]
    stored: Optional[bool]

    # --- Metadata ---
    messages: List[dict]               # LangChain message history
    iteration_count: int               # guard against infinite loops
