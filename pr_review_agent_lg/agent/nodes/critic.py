"""
Critic Node — LLM synthesis.
Receives all specialist findings, deduplicates, ranks, and produces the final verdict.
Uses gpt-4o — synthesis requires the strongest model.
"""
import json
import logging
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agent.state import ReviewState
from models.schemas import AgentResult, CriticReport, Finding

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

SYSTEM_PROMPT = """You are a senior engineering lead doing a final code review synthesis.

You receive findings from three specialist agents (security, logic, style).
Your job:
1. Deduplicate: if two findings target the same file + line + category, keep only the most severe one.
2. Rank: sort all findings by severity — HIGH first, then MEDIUM, then LOW.
3. Summarise: write a 2-sentence natural language summary of the overall review.
4. Verdict: decide one of APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION based on the findings and explain why.

Use your judgment for the verdict — don't apply a mechanical rule.
Consider the number, severity, and nature of findings.

You do NOT look at the raw diff. You only reason over the findings provided."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Here are the findings from all specialist agents:\n\n{findings_json}\n\n{error_note}"),
])


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    seen: dict[tuple, Finding] = {}
    for f in findings:
        key = (f.file_name, f.line_number, f.category)
        if key not in seen or SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[seen[key].severity]:
            seen[key] = f
    result = list(seen.values())
    result.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 3))
    return result


def critic_node(state: ReviewState) -> dict:
    agent_results: list[AgentResult] = state.get("agent_results") or []
    logger.info("[CRITIC] received results from %d agents", len(agent_results))
    start = time.perf_counter()

    all_findings = []
    errors = []
    for r in agent_results:
        all_findings.extend(r.findings)
        if r.error:
            errors.append(f"{r.agent} ({r.error})")

    findings_json = json.dumps([f.model_dump() for f in all_findings], indent=2)
    error_note = f"Note: these agents failed and returned no findings: {', '.join(errors)}" if errors else ""

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    chain = prompt | llm.with_structured_output(CriticReport)

    try:
        report: CriticReport = chain.invoke({
            "findings_json": findings_json,
            "error_note": error_note,
        })
        elapsed = round(time.perf_counter() - start, 2)
        logger.info("[CRITIC] done — verdict=%s  findings=%d  %.1fs",
                    report.verdict, len(report.findings), elapsed)
        return {"critic_report": report, "verdict": report.verdict}

    except Exception as e:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("[CRITIC] failed after %.1fs: %s", elapsed, e)
        fallback_findings = _deduplicate(all_findings)
        return {
            "critic_report": CriticReport(
                findings=fallback_findings,
                summary="Critic agent unavailable. Raw findings from specialist agents shown.",
                verdict="NEEDS_DISCUSSION",
                verdict_reason=f"Critic failed: {e}",
            ),
            "verdict": "NEEDS_DISCUSSION",
        }
