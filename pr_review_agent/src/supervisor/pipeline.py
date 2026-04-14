"""
Supervisor — pure Python orchestration pipeline.

Dispatches the three specialist agents in parallel via asyncio.gather(),
collects their results, then passes everything to the Critic for synthesis.

This is intentionally NOT an LLM — the Supervisor is control-plane code.
"""

import asyncio
import logging
import time
from models.schemas import AgentResult, CriticReport, Finding
from agents.security_agent import run_security_agent
from agents.logic_agent import run_logic_agent
from agents.style_agent import run_style_agent
from agents.critic_agent import run_critic_agent

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """
    Deduplication rule:
      - Same file + line + category → keep the highest severity finding
      - Same file + line + different category → keep both

    Returns findings sorted HIGH → MEDIUM → LOW.
    """
    seen: dict[tuple, Finding] = {}
    for f in findings:
        key = (f.file_name, f.line_number, f.category)
        if key not in seen:
            seen[key] = f
        else:
            existing = seen[key]
            if SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[existing.severity]:
                seen[key] = f
    result = list(seen.values())
    result.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 3))
    return result


async def run_pipeline(diff: str) -> tuple[list[AgentResult], CriticReport, int]:
    """
    Run the full review pipeline against a diff.

    Returns:
        agent_results  : List of AgentResult from each specialist (for UI display)
        critic_report  : Final CriticReport with deduplicated findings and verdict
        total_tokens   : Total tokens used across all agents + critic
    """
    logger.info("Pipeline started — dispatching 3 agents in parallel")
    pipeline_start = time.perf_counter()

    results = await asyncio.gather(
        run_security_agent(diff),
        run_logic_agent(diff),
        run_style_agent(diff),
        return_exceptions=True,
    )

    # Normalise any unexpected exceptions into AgentResult errors
    agent_results: list[AgentResult] = []
    for i, result in enumerate(results):
        agent_name = ["security", "logic", "style"][i]
        if isinstance(result, Exception):
            logger.error(f"{agent_name.capitalize()}Agent raised exception: {result}")
            agent_results.append(AgentResult(agent=agent_name, findings=[], error=str(result)))
        else:
            agent_results.append(result)

    specialist_tokens = sum(r.tokens_used for r in agent_results)
    total_findings = sum(len(r.findings) for r in agent_results)
    logger.info(f"All agents complete — {total_findings} total findings, {specialist_tokens} specialist tokens")

    # Pass all results to the Critic
    critic_report, critic_tokens = await run_critic_agent(agent_results)
    total_tokens = specialist_tokens + critic_tokens

    elapsed = time.perf_counter() - pipeline_start
    logger.info(f"Pipeline complete — verdict={critic_report.verdict}, total_tokens={total_tokens}, elapsed={elapsed:.1f}s")

    return agent_results, critic_report, total_tokens
