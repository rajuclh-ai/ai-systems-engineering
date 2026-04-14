"""CriticAgent — deduplicates findings, ranks them, and produces the final verdict."""

import json
import logging
import time
import openai
from models.schemas import AgentResult, CriticReport, Finding

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior engineering lead doing a final code review synthesis.

You receive findings from three specialist agents (security, logic, style).
Your job:
1. Deduplicate: if two findings target the same file + line + category, keep only the most severe one.
2. Rank: sort all findings by severity — HIGH first, then MEDIUM, then LOW.
3. Summarise: write a 2-sentence natural language summary of the overall review.
4. Verdict: decide one of APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION based on the findings and explain why.

Use your judgment for the verdict — don't apply a mechanical rule. Consider the number, severity, and nature of findings.

You do NOT look at the raw diff. You only reason over the findings provided."""


def _serialize_findings(results: list[AgentResult]) -> str:
    all_findings = []
    for result in results:
        for f in result.findings:
            all_findings.append(f.model_dump())
    return json.dumps(all_findings, indent=2)


async def run_critic_agent(results: list[AgentResult]) -> tuple[CriticReport, int]:
    """
    Returns:
        CriticReport : the final synthesised report
        int          : total tokens used by the Critic call
    """
    client = openai.AsyncOpenAI()
    logger.info("CriticAgent started")
    start = time.perf_counter()

    findings_json = _serialize_findings(results)
    agent_errors = [r for r in results if r.error]

    user_content = f"Here are the findings from all specialist agents:\n\n{findings_json}"
    if agent_errors:
        error_note = ", ".join(f"{r.agent} ({r.error})" for r in agent_errors)
        user_content += f"\n\nNote: The following agents failed and returned no findings: {error_note}"

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=CriticReport,
        )
        report = response.choices[0].message.parsed
        tokens = response.usage.total_tokens if response.usage else 0
        elapsed = time.perf_counter() - start
        logger.info(f"CriticAgent done — {len(report.findings)} findings, verdict={report.verdict}, {tokens} tokens, {elapsed:.1f}s")
        return report, tokens
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(f"CriticAgent failed after {elapsed:.1f}s: {e}")
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        all_findings: list[Finding] = []
        for result in results:
            all_findings.extend(result.findings)
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 3))
        return CriticReport(
            findings=all_findings,
            summary="Critic agent unavailable. Raw findings from specialist agents shown below.",
            verdict="NEEDS_DISCUSSION",
            verdict_reason=f"Critic failed: {str(e)}",
        ), 0
