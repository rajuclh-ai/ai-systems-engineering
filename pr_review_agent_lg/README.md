# PR Review Agent — LangGraph Edition

> v2 of [pr_review_agent](../pr_review_agent) — rebuilt with LangGraph, LangChain, and LangSmith.
> v1 used raw OpenAI SDK + `asyncio.gather()`. This version adds durable state, parallel fan-out via `Send()`, human-in-the-loop approval, iterative review rounds, and full LangSmith observability.

---

## The Story

Code review is a reasoning problem, not a lookup problem.
Three specialists examine a diff from different angles — security, logic, style.
A critic synthesizes their findings into a single actionable verdict.
When the risk is too high to post automatically, the agent pauses and asks.
Every outcome is stored — the agent gets smarter with each review.

---

## Architecture

```
GitHub PR URL
      │
      ▼
┌─────────────┐
│   fetcher   │  rule-based — fetch diff from GitHub REST API (no LLM)
└──────┬──────┘
       │  diff
       ▼
  Send() parallel fan-out
  ┌────────────────────────────────────┐
  │                                    │
  ▼            ▼                       ▼
security_node  logic_node         style_node
  │            │                       │
  └────────────┴───────────────────────┘
               │  list[AgentResult]
               ▼
        ┌──────────────┐
        │    critic    │  LLM — deduplicate, rank, verdict
        └──────┬───────┘
               │
               ▼
        post_comment_node  →  GitHub PR comment
               │
               ▼
        learning_node  →  SQLite incident store
               │
              END
```

> No HITL — the agent posts a review comment, not an execution action.
> The engineer reads the comment and decides. The human is already in the loop
> by the nature of the PR review process. Compare with self-healing-pipeline-agent
> where HITL gates irreversible production actions (Flink job restart, redeployment).

---

## Graph Flow

| Node | Type | Description |
|---|---|---|
| `fetcher` | Rule-based | Parse PR URL → call GitHub REST API → return raw unified diff |
| `security_node` | LLM (gpt-4o) | Find injection, secrets, auth flaws, PII exposure |
| `logic_node` | LLM (gpt-4o) | Find null checks, off-by-one, race conditions, edge cases |
| `style_node` | LLM (gpt-4o-mini) | Find naming, dead code, complexity, missing docs |
| `critic` | LLM (gpt-4o) | Deduplicate + rank findings → verdict |
| `post_comment` | Rule-based | POST review comment to GitHub PR via REST API — skips gracefully if no `GITHUB_TOKEN` (display-only mode) |
| `learning` | Rule-based | Write verdict + findings to SQLite for future context |

---

## Key Design Decisions

### 1. `Send()` replaces `asyncio.gather()`

v1 used `asyncio.gather()` to run the three specialists in parallel.
v2 uses LangGraph's `Send()` API — same parallelism, but each agent run is a graph node with full state, tracing, and retry support.

```
Sequential:  security(5s) + logic(5s) + style(5s) = 15s
Parallel:    max(security, logic, style)           = ~5s
```

### 2. Model per node — cost vs stakes

| Node | Model | Reason |
|---|---|---|
| security | gpt-4o | High stakes — missing a vulnerability is expensive |
| logic | gpt-4o | Complex reasoning required |
| style | gpt-4o-mini | Low stakes, high volume — cheap is fine |
| critic | gpt-4o | Synthesis requires the strongest model |

### 3. No HITL — posting a comment is not an irreversible action

self-healing-pipeline-agent uses HITL because it executes fixes on production systems
(Flink job restarts, redeployments). Those are irreversible — human sign-off is warranted.

This agent posts a review comment. The engineer reads it and decides what to act on.
The human is already in the loop by the nature of the PR review process.
Adding HITL here would be unnecessary complexity with no safety benefit.

### 4. Iterative review loop

After posting a review, the agent can re-run on the next commit push.
State is persisted via `MemorySaver` — the agent remembers what it flagged in round 1
and checks if those issues were addressed in round 2.

### 5. Learning node

Every completed review is stored to SQLite:
- pipeline/repo, verdict, findings count, severity breakdown
- Future reviews on the same repo get this as context in the Critic prompt:
  *"This repo has had 4 SQL injection findings in the past 30 days."*

### 6. Fetcher is rule-based — not an LLM

Parsing a GitHub URL and calling a REST API is control-flow code, not a reasoning task.
Same principle as self-healing-pipeline-agent's Monitor node:
**use an LLM where reasoning adds value, not where a function call will do.**

---

## State Design

```python
from typing import Annotated
from operator import add

class ReviewState(TypedDict):
    # Input
    pr_url:           Optional[str]
    diff:             Optional[str]

    # Specialist outputs — reducer appends each AgentResult as Send() branches complete
    # Annotated[list, add] is the idiomatic LangGraph fan-out pattern:
    #   - each specialist returns {"agent_results": [its_result]}
    #   - the reducer appends automatically — no hardcoded security/logic/style fields
    #   - adding a 4th specialist later requires zero state schema changes
    #   - AgentResult.agent ("security" | "logic" | "style") identifies the source
    agent_results:    Annotated[list[AgentResult], add]

    # Critic output
    critic_report:    Optional[CriticReport]
    verdict:          Optional[str]       # APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION

    # Learning
    incident_id:      Optional[str]

    # Metadata
    messages:         List[dict]
    iteration_count:  int
```

---

## Data Contracts (unchanged from v1)

```
Finding
  ├── file_name      : str
  ├── line_number    : int
  ├── severity       : HIGH | MEDIUM | LOW
  ├── category       : security | logic | style
  ├── message        : str
  ├── suggestion     : str
  └── agent          : security | logic | style

AgentResult
  ├── agent          : security | logic | style
  ├── findings       : list[Finding]
  ├── tokens_used    : int
  ├── duration_secs  : float
  └── error          : str | None

CriticReport
  ├── findings       : list[Finding]     ← deduplicated + ranked HIGH→MEDIUM→LOW
  ├── summary        : str
  ├── verdict        : APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION
  └── verdict_reason : str
```

---

## Tech Stack

| Layer | v1 | v2 |
|---|---|---|
| LLM calls | `openai.AsyncOpenAI()` | `ChatOpenAI` + `with_structured_output()` |
| Orchestration | `asyncio.gather()` | LangGraph `StateGraph` + `Send()` |
| Parallel fan-out | `asyncio.gather()` | LangGraph `Send()` |
| Observability | None | LangSmith (automatic per-node tracing) |
| HITL | None | Not needed — comment posting is not an irreversible action |
| State persistence | None | `MemorySaver` checkpointer |
| Learning | None | SQLite via SQLAlchemy |
| API | Flask | FastAPI |
| Config | python-dotenv | pydantic-settings |
| Package manager | pip | uv |

---

## Project Structure (planned)

```
pr_review_agent_lg/
├── agent/
│   ├── graph.py              # LangGraph StateGraph — entry point
│   ├── state.py              # ReviewState TypedDict
│   ├── nodes/
│   │   ├── fetcher.py        # Fetch diff from GitHub (rule-based)
│   │   ├── security.py       # Security specialist (LLM)
│   │   ├── logic.py          # Logic specialist (LLM)
│   │   ├── style.py          # Style specialist (LLM)
│   │   ├── critic.py         # Synthesis + verdict (LLM)
│   │   ├── post_comment.py   # Post review to GitHub (rule-based)
│   │   └── learning.py       # Store outcome to SQLite (rule-based)
│   └── checkpointer.py       # MemorySaver setup
├── models/
│   ├── schemas.py            # Finding, AgentResult, CriticReport (Pydantic)
│   └── db.py                 # SQLAlchemy ReviewRow model
├── api/
│   ├── main.py               # FastAPI app
│   ├── routes/
│   │   ├── reviews.py        # POST /reviews, GET /reviews/{thread_id}/status
│   │   └── approval.py       # POST /approval/{thread_id}
│   └── schemas.py            # API request/response models
├── utils/
│   └── github.py             # GitHub REST API client (carry over from v1)
├── tests/
├── .env
└── pyproject.toml
```

---

## Build Plan

| Week | Deliverable |
|---|---|
| 1 | `ReviewState`, `fetcher_node`, 3 specialist nodes via `Send()`, `critic_node` — graph running end to end |
| 2 | FastAPI layer, LangSmith tracing, SQLite learning node |
| 3 | `post_comment_node`, iterative review loop, demo script |

---

## v1 vs v2 — What Changes, What Stays

| | Stays | Changes |
|---|---|---|
| Pydantic schemas | ✓ | — |
| Specialist system prompts | ✓ | Wrapped in `ChatPromptTemplate` |
| GitHub diff fetching | ✓ | Moves into `fetcher_node` |
| Deduplication logic | ✓ | Moves into `critic_node` |
| Orchestration | — | `asyncio.gather()` → `Send()` |
| Observability | — | None → LangSmith |
| HITL | — | Not needed — comment is not an irreversible action |
| State persistence | — | None → `MemorySaver` |
| Learning | — | None → SQLite |
| API framework | — | Flask → FastAPI |
