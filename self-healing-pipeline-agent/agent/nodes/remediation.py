"""
Remediation Node — LLM selects fix strategy and generates remediation plan.
Implements FR4: strategy mapping, risk scores, HITL routing.
"""
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from models.remediation import RemediationPlan, FixStrategy
from agent.state import AgentState

logger = logging.getLogger(__name__)

# FR4 strategy mapping — anomaly_type + combination → allowed strategies
STRATEGY_MAP = {
    "schema_drift":            [FixStrategy.SCHEMA_PATCH],
    "lag_spike":               [FixStrategy.RESTART, FixStrategy.REROUTE],
    "lag_spike_high_cpu":      [FixStrategy.REROUTE],           # RESTART ruled out
    "job_failure":             [FixStrategy.RESTART],
    "restart_storm":           [FixStrategy.SAVEPOINT_REDEPLOY],
    "restart_storm_lag_spike": [FixStrategy.SAVEPOINT_REDEPLOY, FixStrategy.LAG_CATCHUP],
    "null_spike":              [FixStrategy.QUARANTINE, FixStrategy.ALERT_ONLY],
    "unknown":                 [FixStrategy.ALERT_ONLY],
}

# FR4 risk scores per strategy
RISK_SCORES = {
    FixStrategy.ALERT_ONLY:          0.1,
    FixStrategy.RESTART:             0.3,
    FixStrategy.SCHEMA_PATCH:        0.5,
    FixStrategy.REROUTE:             0.6,
    FixStrategy.QUARANTINE:          0.6,
    FixStrategy.SAVEPOINT_REDEPLOY:  0.8,
    FixStrategy.LAG_CATCHUP:         0.9,
}

RISK_THRESHOLD = 0.7   # above this → human approval required

REMEDIATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior data pipeline reliability engineer.
Generate a remediation plan for the pipeline failure below.
You MUST choose one strategy from the allowed strategies list.
Return your response as a JSON object with these exact fields:
- strategy: one of the allowed strategies (exact string)
- description: why this fix for this root cause (2-3 sentences)
- estimated_impact: what will change if this works (1-2 sentences)
- risk_score: use the provided risk score for the chosen strategy
- rollback_plan: specific steps to reverse this fix if it fails
- steps: ordered list of action strings"""),
    ("human", """Pipeline failure:
Pipeline ID: {pipeline_id}
Anomaly type: {anomaly_type}
Severity: {severity}
Root cause: {primary_cause}
Recommended action: {recommended_action}

Allowed strategies: {allowed_strategies}
Risk score for each strategy: {risk_scores}

Generate the remediation plan.""")
])


def _get_allowed_strategies(anomaly_type: str, combination: str) -> list[FixStrategy]:
    """Return allowed strategies based on anomaly type and combination."""
    key = combination if combination and combination != "none" else anomaly_type
    return STRATEGY_MAP.get(key, [FixStrategy.ALERT_ONLY])


def remediation_node(state: AgentState) -> dict:
    """
    Generate a remediation plan for the diagnosed failure.
    Sets risk_score and requires_approval based on FR4 thresholds.
    """
    event = state["event"]
    root_cause = state["root_cause"]
    anomaly_type = state["anomaly_type"]
    severity = state["severity"]
    combination = state.get("combination", "none")

    allowed_strategies = _get_allowed_strategies(anomaly_type, combination)
    risk_scores = {s.value: RISK_SCORES[s] for s in allowed_strategies}

    logger.info("[REMEDIATION] pipeline=%s  allowed_strategies=%s  → calling LLM ...",
                event.pipeline_id, [s.value for s in allowed_strategies])

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(RemediationPlan)
    chain = REMEDIATION_PROMPT | structured_llm

    plan: RemediationPlan = chain.invoke({
        "pipeline_id": event.pipeline_id,
        "anomaly_type": anomaly_type,
        "severity": severity,
        "primary_cause": root_cause.primary_cause,
        "recommended_action": root_cause.recommended_action,
        "allowed_strategies": [s.value for s in allowed_strategies],
        "risk_scores": risk_scores,
    })

    # Override risk_score with our defined value — don't trust LLM to set it
    plan.risk_score = RISK_SCORES.get(plan.strategy, 0.5)
    requires_approval = plan.risk_score > RISK_THRESHOLD

    hitl_str = "⚠️  HITL required" if requires_approval else "auto-execute"
    logger.info("[REMEDIATION] strategy=%s  risk=%.1f  → %s",
                plan.strategy.value, plan.risk_score, hitl_str)

    return {
        "remediation_plan": plan,
        "risk_score": plan.risk_score,
        "requires_approval": requires_approval,
    }
