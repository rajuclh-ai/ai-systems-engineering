"""LogicAgent — finds logic bugs in the diff."""

import logging
import time
import openai
from models.schemas import AgentFindings, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a logic and correctness code reviewer. Your ONLY job is to find logic bugs in the code diff provided.

You look for:
- Missing null/None checks
- Off-by-one errors
- Unreachable code
- Incorrect conditionals or boolean logic
- Unhandled edge cases (empty list, zero division, negative input)
- Race conditions or concurrency bugs
- Incorrect return values or missing returns
- Infinite loops or broken iteration

You do NOT flag:
- Security vulnerabilities
- Code style, naming, or formatting issues
- Performance optimisations

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW), a clear message, and a concrete suggestion to fix it.
If there are no logic issues, return an empty findings list."""


async def run_logic_agent(diff: str) -> AgentResult:
    client = openai.AsyncOpenAI()
    logger.info("LogicAgent started")
    start = time.perf_counter()
    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review this diff for logic bugs:\n\n{diff}"},
            ],
            response_format=AgentFindings,
        )
        findings = response.choices[0].message.parsed.findings
        for f in findings:
            f.agent = "logic"
            f.category = "logic"
        tokens = response.usage.total_tokens if response.usage else 0
        elapsed = time.perf_counter() - start
        logger.info(f"LogicAgent done — {len(findings)} findings, {tokens} tokens, {elapsed:.1f}s")
        return AgentResult(agent="logic", findings=findings, tokens_used=tokens, duration_seconds=round(elapsed, 2))
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(f"LogicAgent failed after {elapsed:.1f}s: {e}")
        return AgentResult(agent="logic", findings=[], error=str(e), duration_seconds=round(elapsed, 2))
