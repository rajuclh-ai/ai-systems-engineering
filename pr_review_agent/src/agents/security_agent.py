"""SecurityAgent — finds security issues in the diff."""

import logging
import time
import openai
from models.schemas import AgentFindings, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a security code reviewer. Your ONLY job is to find security vulnerabilities in the code diff provided.

You look for:
- Hardcoded secrets, passwords, API keys, tokens
- SQL injection, command injection, XSS vulnerabilities
- Broken authentication or authorization
- Unsafe deserialization
- Exposed PII or sensitive data
- Insecure direct object references
- Missing input validation at security boundaries

You do NOT flag:
- Code style or naming issues
- Logic bugs unrelated to security
- Performance problems

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW), a clear message, and a concrete suggestion to fix it.
If there are no security issues, return an empty findings list."""


async def run_security_agent(diff: str) -> AgentResult:
    client = openai.AsyncOpenAI()
    logger.info("SecurityAgent started")
    start = time.perf_counter()
    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review this diff for security issues:\n\n{diff}"},
            ],
            response_format=AgentFindings,
        )
        findings = response.choices[0].message.parsed.findings
        for f in findings:
            f.agent = "security"
            f.category = "security"
        tokens = response.usage.total_tokens if response.usage else 0
        elapsed = time.perf_counter() - start
        logger.info(f"SecurityAgent done — {len(findings)} findings, {tokens} tokens, {elapsed:.1f}s")
        return AgentResult(agent="security", findings=findings, tokens_used=tokens, duration_seconds=round(elapsed, 2))
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(f"SecurityAgent failed after {elapsed:.1f}s: {e}")
        return AgentResult(agent="security", findings=[], error=str(e), duration_seconds=round(elapsed, 2))
