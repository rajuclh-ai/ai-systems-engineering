"""StyleAgent — finds style and maintainability issues in the diff."""

import logging
import time
import openai
from models.schemas import AgentFindings, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a code style and maintainability reviewer. Your ONLY job is to find style issues in the code diff provided.

You look for:
- Poor or misleading variable/function/class names
- Dead code or unused variables
- Functions that are too long or doing too many things
- Missing or inadequate docstrings on public functions/classes
- Overly complex logic that should be simplified
- Magic numbers or strings that should be constants
- Inconsistent naming conventions (e.g. mixing snake_case and camelCase)

You do NOT flag:
- Security vulnerabilities
- Logic bugs or correctness issues
- Performance problems

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW), a clear message, and a concrete suggestion to fix it.
If there are no style issues, return an empty findings list."""


async def run_style_agent(diff: str) -> AgentResult:
    client = openai.AsyncOpenAI()
    logger.info("StyleAgent started")
    start = time.perf_counter()
    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review this diff for style and maintainability issues:\n\n{diff}"},
            ],
            response_format=AgentFindings,
        )
        findings = response.choices[0].message.parsed.findings
        for f in findings:
            f.agent = "style"
            f.category = "style"
        tokens = response.usage.total_tokens if response.usage else 0
        elapsed = time.perf_counter() - start
        logger.info(f"StyleAgent done — {len(findings)} findings, {tokens} tokens, {elapsed:.1f}s")
        return AgentResult(agent="style", findings=findings, tokens_used=tokens, duration_seconds=round(elapsed, 2))
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(f"StyleAgent failed after {elapsed:.1f}s: {e}")
        return AgentResult(agent="style", findings=[], error=str(e), duration_seconds=round(elapsed, 2))
