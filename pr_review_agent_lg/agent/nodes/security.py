"""
Security Node — LLM-powered specialist.
Finds security vulnerabilities in the diff.
Uses gpt-4o — high stakes, missing a vuln is expensive.
"""
import logging
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agent.state import ReviewState
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

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW),
a clear message, and a concrete suggestion to fix it.
If there are no security issues, return an empty findings list."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Review this diff for security issues:\n\n{diff}"),
])


def security_node(state: ReviewState) -> dict:
    diff = state["diff"]
    logger.info("[SECURITY] starting review (%d chars)", len(diff))
    start = time.perf_counter()

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    chain = prompt | llm.with_structured_output(AgentFindings)

    try:
        result: AgentFindings = chain.invoke({"diff": diff})
        for f in result.findings:
            f.agent = "security"
            f.category = "security"
        tokens = 0  # LangChain structured output doesn't expose usage directly here
        elapsed = round(time.perf_counter() - start, 2)
        logger.info("[SECURITY] done — %d findings in %.1fs", len(result.findings), elapsed)
        return {"agent_results": [AgentResult(
            agent="security",
            findings=result.findings,
            tokens_used=tokens,
            duration_seconds=elapsed,
        )]}
    except Exception as e:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("[SECURITY] failed after %.1fs: %s", elapsed, e)
        return {"agent_results": [AgentResult(
            agent="security",
            findings=[],
            error=str(e),
            duration_seconds=elapsed,
        )]}
