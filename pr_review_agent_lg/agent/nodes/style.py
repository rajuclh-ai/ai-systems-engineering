"""
Style Node — LLM-powered specialist.
Finds style and readability issues in the diff.
Uses gpt-4o-mini — low stakes, high volume, cheap.
"""
import logging
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agent.state import ReviewState
from models.schemas import AgentFindings, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a code style reviewer. Your ONLY job is to find style and readability issues in the code diff provided.

You look for:
- Poor naming (variables, functions, classes)
- Missing or inadequate docstrings and comments
- Overly complex functions that should be broken down
- Dead code — unused variables, unreachable branches
- Inconsistent formatting or conventions
- Magic numbers or strings that should be constants
- Functions that do too many things

You do NOT flag:
- Security vulnerabilities
- Logic bugs
- Performance issues

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW),
a clear message, and a concrete suggestion to fix it.
If there are no style issues, return an empty findings list."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Review this diff for style and readability issues:\n\n{diff}"),
])


def style_node(state: ReviewState) -> dict:
    diff = state["diff"]
    logger.info("[STYLE] starting review (%d chars)", len(diff))
    start = time.perf_counter()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm.with_structured_output(AgentFindings)

    try:
        result: AgentFindings = chain.invoke({"diff": diff})
        for f in result.findings:
            f.agent = "style"
            f.category = "style"
        elapsed = round(time.perf_counter() - start, 2)
        logger.info("[STYLE] done — %d findings in %.1fs", len(result.findings), elapsed)
        return {"agent_results": [AgentResult(
            agent="style",
            findings=result.findings,
            tokens_used=0,
            duration_seconds=elapsed,
        )]}
    except Exception as e:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("[STYLE] failed after %.1fs: %s", elapsed, e)
        return {"agent_results": [AgentResult(
            agent="style",
            findings=[],
            error=str(e),
            duration_seconds=elapsed,
        )]}
