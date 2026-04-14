# PR Review Agent — Requirements

A multi-agent AI system that reviews GitHub pull requests using a pipeline of specialist agents, each focused on one concern, synthesized into a single actionable report.

---

## Problem Statement

Code review is a bottleneck in every engineering team. A single human reviewer must context-switch across security, logic, and style concerns simultaneously — and misses things because one brain is playing three specialist roles at once.

This project replaces the "one reviewer does everything" model with a pipeline of specialist AI agents running in parallel, synthesized by a Critic agent into one structured report.

---

## Users

| User | What they submit | What they want back |
|---|---|---|
| Developer | A GitHub PR URL or raw code diff | A structured review before merging |
| Tech lead | Any PR in a team repo | A second opinion on risky changes |
| Portfolio reviewer | Anything | Proof of multi-agent system design skills |

---

## Functional Requirements

### Must Have

- Accept a GitHub PR URL and fetch the real diff via GitHub API
- Accept raw code paste as fallback (works without a GitHub token)
- Run SecurityAgent, LogicAgent, and StyleAgent against the diff in parallel
- Each specialist agent returns structured findings (Pydantic model — see Data Contract)
- Critic agent deduplicates, ranks, and produces a final verdict with explanation
- Final report rendered in a UI — not a terminal JSON dump
- Each finding tied to a specific file name and line number in the diff
- Show which agent flagged each finding

### Out of Scope (v1)

- Streaming live findings as each agent finishes (all results appear at once)
- Post report back to GitHub PR as a comment
- Support for private repositories
- GitHub webhook auto-trigger on PR open
- Storing review history in a database
- Diff chunking by file (v1 sends full diff)
- Multi-language support (v1 targets Python only)
- CVE/CWE vulnerability database lookup

---

## Agent Responsibilities

| Agent | Looks for | Does NOT look for |
|---|---|---|
| SecurityAgent | Injection, hardcoded secrets, auth flaws, unsafe deserialization, exposed PII | Style, naming, logic correctness |
| LogicAgent | Null checks, edge cases, off-by-one errors, unreachable code, race conditions | Formatting, security, variable names |
| StyleAgent | Naming conventions, dead code, cyclomatic complexity, missing docstrings | Security, correctness, logic |
| Critic | Deduplication, ranking, verdict + explanation | Never reads the raw diff |
| Supervisor | Dispatches 3 specialists in parallel, collects results, passes to Critic | Never produces findings itself |

**Supervisor is pure Python** (`asyncio.gather`) — not an LLM. This is a deliberate design choice: not every step in a pipeline needs to be an LLM call.

**Critic is an LLM** — it reads all findings, deduplicates, ranks by severity, writes a 2-sentence natural language summary, and decides the verdict.

---

## Data Contract

### Finding (output of each specialist agent)

```python
class Finding(BaseModel):
    file_name: str
    line_number: int
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    category: Literal["security", "logic", "style"]
    message: str
    suggestion: str
    agent: Literal["security", "logic", "style"]
```

### AgentResult (one per specialist)

```python
class AgentResult(BaseModel):
    agent: Literal["security", "logic", "style"]
    findings: list[Finding]
    error: str | None  # populated if agent failed
```

### CriticReport (final output)

```python
class CriticReport(BaseModel):
    findings: list[Finding]       # deduplicated, sorted by severity
    summary: str                  # 2-sentence natural language summary
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "NEEDS_DISCUSSION"]
    verdict_reason: str           # Critic's explanation for the verdict
```

---

## Deduplication Rule

- Same `line_number` + same `category` → keep the one with higher severity, discard the other
- Same `line_number` + different `category` → keep both (different concerns)

---

## Verdict Logic

The Critic LLM decides the verdict based on all findings. It explains its reasoning in `verdict_reason`. No hardcoded rules — the Critic reasons to its conclusion.

---

## Orchestration Flow

```
User submits PR URL or raw diff
        ↓
Supervisor fetches diff (GitHub API or raw paste)
        ↓
asyncio.gather() → [SecurityAgent, LogicAgent, StyleAgent] run in parallel
        ↓
All 3 AgentResults collected
        ↓
Critic receives all findings → deduplicates → ranks → writes verdict
        ↓
CriticReport returned to UI
        ↓
Results page rendered (all at once)
```

---

## UI Flow

```
IDLE        → User sees input form (URL field + raw paste toggle + Review button)
SUBMITTING  → Spinner shown, agents running in background
RESULTS     → Full report rendered:
                - Security findings card
                - Logic findings card
                - Style findings card
                - Critic summary card (verdict + summary + ranked findings)
                - "Copy as Markdown" button
```

---

## Failure Handling

| Failure | Behavior |
|---|---|
| One specialist agent times out | `AgentResult.error` is set, that card shows "Agent unavailable" in UI, Critic works with remaining results |
| Critic fails | Show raw findings from specialists, display "Critic unavailable" |
| GitHub API returns 404 | Show "PR not found — check URL or paste diff manually" |
| GitHub API returns 401 | Show "GitHub token missing or invalid — paste diff manually" |
| Agent returns malformed JSON | Pydantic validation catches it, treated as agent failure |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Async orchestration | asyncio |
| LLM | OpenAI gpt-4o-mini (all agents) |
| Structured outputs | OpenAI structured outputs + Pydantic |
| GitHub diff fetching | GitHub REST API (requests) |
| Frontend | HTML, CSS, JavaScript |
| Config | python-dotenv (.env for OPENAI_API_KEY + GITHUB_TOKEN) |

**No LangChain. No LangGraph.** The orchestration logic is the project.

---

## Project Structure

```
pr_review_agent/
├── src/
│   ├── app.py                        ← Flask app, routes, request handling
│   ├── requirements.txt
│   ├── .env                          ← OPENAI_API_KEY, GITHUB_TOKEN (not committed)
│   ├── templates/
│   │   └── index.html                ← Single UI: input form + results page
│   ├── agents/
│   │   ├── security_agent.py         ← SecurityAgent — finds security issues
│   │   ├── logic_agent.py            ← LogicAgent — finds logic issues
│   │   ├── style_agent.py            ← StyleAgent — finds style issues
│   │   └── critic_agent.py           ← Critic — deduplicates, ranks, verdict
│   ├── models/
│   │   └── schemas.py                ← Pydantic models: Finding, AgentResult, CriticReport
│   ├── supervisor/
│   │   └── pipeline.py               ← Pure Python orchestration: asyncio.gather + Critic call
│   └── utils/
│       └── github.py                 ← Fetch diff from GitHub PR URL
├── requirements.md                   ← This file
```

---

## Constraints

| Constraint | Reason |
|---|---|
| No paid services beyond OpenAI | Near-zero cost for portfolio project |
| Must run fully locally | No cloud deploy needed for demo |
| gpt-4o-mini for all agents | Cost control |
| No LangChain / LangGraph | Orchestration logic is the portfolio proof |
| GitHub token optional | App works with raw paste if token not set |

---

## Key Concepts Demonstrated

- **Agent separation of concerns** — each specialist has a tight, non-overlapping scope enforced by system prompt
- **Typed inter-agent communication** — Pydantic structs between every agent, no free text passing
- **Parallel orchestration** — `asyncio.gather()` for concurrent agent execution
- **Structured LLM output** — OpenAI structured outputs, not free text parsing
- **Failure handling** — partial failures degrade gracefully, never crash the pipeline
- **Deliberate non-use of LLM** — Supervisor is Python, not an LLM (shows judgment)
- **Critic as synthesis layer** — deduplication, ranking, and verdict in one reasoned step
