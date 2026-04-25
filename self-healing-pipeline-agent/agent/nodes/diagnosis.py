"""
Diagnosis Node — LLM-powered root cause analysis.
Queries SQLite for similar past incidents before calling the LLM.
Implements FR3: confidence routing.
"""
import json
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from models.db import get_session, IncidentRow
from models.diagnosis import RootCause
from agent.state import AgentState

logger = logging.getLogger(__name__)

DIAGNOSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior data pipeline reliability engineer.
Diagnose the root cause of the pipeline failure described below.
Be specific — reference the exact metrics that led to your conclusion.
Return your response as a JSON object with these exact fields:
- primary_cause: one clear sentence
- contributing_factors: list of strings
- confidence: float 0.0 to 1.0
- evidence: list of strings (which metrics drove this conclusion)
- recommended_action: what the remediation agent should consider"""),
    ("human", """Pipeline failure details:
Pipeline ID: {pipeline_id}
Anomaly type: {anomaly_type}
Severity: {severity}
Combination: {combination}
Metrics: {metrics}
Raw log: {raw_log}

Similar past incidents (may be empty):
{similar_incidents}

Diagnose the root cause.""")
])


def _query_similar_incidents(pipeline_id: str, anomaly_type: str) -> list[dict]:
    """
    Query SQLite for similar past incidents.
    Strategy: same pipeline_id first, then same anomaly_type across fleet.
    """
    try:
        with get_session() as session:
            # 1st — same pipeline
            rows = session.query(IncidentRow).filter(
                IncidentRow.pipeline_id == pipeline_id
            ).order_by(IncidentRow.created_at.desc()).limit(3).all()

            # 2nd — same anomaly type across fleet (fallback)
            if not rows:
                rows = session.query(IncidentRow).filter(
                    IncidentRow.anomaly_type == anomaly_type
                ).order_by(IncidentRow.created_at.desc()).limit(3).all()

            return [
                {
                    "pipeline_id": r.pipeline_id,
                    "anomaly_type": r.anomaly_type,
                    "root_cause": r.root_cause,
                    "strategy": r.strategy_executed,
                    "outcome": r.outcome,
                }
                for r in rows
            ]
    except Exception:
        logger.warning("Could not query incident history — proceeding without context")
        return []


def diagnosis_node(state: AgentState) -> dict:
    """
    Diagnose the root cause of the pipeline failure.
    Queries past incidents for context, then calls LLM.
    Routes based on confidence (FR3).
    """
    event = state["event"]
    anomaly_type = state["anomaly_type"]
    severity = state["severity"]
    combination = state.get("combination", "none")

    # Query memory before calling LLM
    similar_incidents = _query_similar_incidents(event.pipeline_id, anomaly_type)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(RootCause)

    chain = DIAGNOSIS_PROMPT | structured_llm

    root_cause: RootCause = chain.invoke({
        "pipeline_id": event.pipeline_id,
        "anomaly_type": anomaly_type,
        "severity": severity,
        "combination": combination,
        "metrics": json.dumps(event.metrics, indent=2),
        "raw_log": event.raw_log or "none",
        "similar_incidents": json.dumps(similar_incidents, indent=2) if similar_incidents else "none",
    })

    logger.info(
        "Diagnosis complete — pipeline=%s confidence=%.2f cause=%s",
        event.pipeline_id, root_cause.confidence, root_cause.primary_cause
    )

    return {
        "root_cause": root_cause,
        "similar_incidents": similar_incidents,
    }
