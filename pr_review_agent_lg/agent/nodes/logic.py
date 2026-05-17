"""
Logic Node — LLM-powered specialist.
Finds logic bugs in the diff.
Uses gpt-4o — complex reasoning required.
"""
import logging
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agent.state import ReviewState
from models.schemas import AgentFindings, AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a logic code reviewer. Your ONLY job is to find logic bugs in the code diff provided.

You look for:
- Null/None dereferences without checks
- Off-by-one errors
- Missing edge case handling
- Race conditions and concurrency bugs
- Incorrect boolean logic
- Missing error handling for operations that can fail
- Unreachable code or dead branches
- Incorrect algorithm implementation

You do NOT flag:
- Security vulnerabilities
- Code style or naming issues
- Performance problems unrelated to correctness

For each finding, provide the exact file name, line number, severity (HIGH/MEDIUM/LOW),
a clear message, and a concrete suggestion to fix it.
If there are no logic issues, return an empty findings list."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Review this diff for logic bugs:\n\n{diff}"),
])


def logic_node(state: ReviewState) -> dict:
    diff = state["diff"]
    logger.info("[LOGIC] starting review (%d chars)", len(diff))
    start = time.perf_counter()

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    chain = prompt | llm.with_structured_output(AgentFindings)

    try:
        result: AgentFindings = chain.invoke({"diff": diff})
        for f in result.findings:
            f.agent = "logic"
            f.category = "logic"
        elapsed = round(time.perf_counter() - start, 2)
        logger.info("[LOGIC] done — %d findings in %.1fs", len(result.findings), elapsed)
        return {"agent_results": [AgentResult(
            agent="logic",
            findings=result.findings,
            tokens_used=0,
            duration_seconds=elapsed,
        )]}
    except Exception as e:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("[LOGIC] failed after %.1fs: %s", elapsed, e)
        return {"agent_results": [AgentResult(
            agent="logic",
            findings=[],
            error=str(e),
            duration_seconds=elapsed,
        )]}
