# PR Review Agent

A multi-agent AI system that reviews GitHub pull requests using a pipeline of specialist agents — each focused on one concern — synthesized into a single actionable report.

---

## Demo

**1. Submit a GitHub PR URL or paste a raw diff**

![Input form](https://github.com/rajuclh-ai/ai-systems-engineering/blob/main/pr_review_agent/assets/screenshot_input.png?raw=true)

**2. Three specialist agents run in parallel — each with token count and duration**

![Results — verdict and agent cards](https://github.com/rajuclh-ai/ai-systems-engineering/blob/main/pr_review_agent/assets/screenshot_results.png?raw=true)

**3. Critic synthesizes all findings — deduplicated, ranked by severity**

![Critic findings table](https://github.com/rajuclh-ai/ai-systems-engineering/blob/main/pr_review_agent/assets/screenshot_findings.png?raw=true)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER (Browser)                             │
│                  http://localhost:5002                               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  GitHub PR URL  or  Raw Diff
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           app.py  (Flask)                           │
│                                                                     │
│   GET  /        →  render input form                                │
│   POST /review  →  fetch diff → run pipeline → render results       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      utils/github.py                                │
│                                                                     │
│   Parse PR URL  →  Call GitHub REST API  →  Return raw unified diff │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  diff (raw text)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   supervisor/pipeline.py                            │
│                                                                     │
│   Pure Python orchestrator — NOT an LLM                             │
│   asyncio.gather() fires all 3 agents simultaneously                │
│                                                                     │
│        diff ──────────────────────────────────────────┐            │
│               │                  │                    │            │
│               ▼                  ▼                    ▼            │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         │
│   │ SecurityAgent │  │  LogicAgent   │  │  StyleAgent   │         │
│   │               │  │               │  │               │         │
│   │ Injection     │  │ Null checks   │  │ Naming        │         │
│   │ Secrets       │  │ Off-by-one    │  │ Dead code     │         │
│   │ Auth flaws    │  │ Edge cases    │  │ Complexity    │         │
│   │ PII exposure  │  │ Race conds.   │  │ Missing docs  │         │
│   │               │  │               │  │               │         │
│   │  OpenAI API   │  │  OpenAI API   │  │  OpenAI API   │         │
│   │  gpt-4o-mini  │  │  gpt-4o-mini  │  │  gpt-4o-mini  │         │
│   └───────┬───────┘  └───────┬───────┘  └───────┬───────┘         │
│           │                  │                   │                 │
│           └──────────────────┴───────────────────┘                 │
│                              │                                      │
│                    list[AgentResult]                                │
│              (typed Pydantic structs — no free text)                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    agents/critic_agent.py                           │
│                                                                     │
│   Receives all findings from 3 agents                               │
│   1. Deduplicate  — same line + same category → keep highest sev.   │
│   2. Rank         — HIGH → MEDIUM → LOW                             │
│   3. Summarise    — 2-sentence natural language summary             │
│   4. Verdict      — APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION    │
│                                                                     │
│                         OpenAI API  gpt-4o-mini                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  CriticReport (Pydantic)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      templates/index.html                           │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  VERDICT BANNER  —  REQUEST CHANGES / APPROVE / DISCUSS     │  │
│   └─────────────────────────────────────────────────────────────┘  │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         │
│   │ Security Card │  │  Logic Card   │  │  Style Card   │         │
│   │  N findings   │  │  N findings   │  │  N findings   │         │
│   └───────────────┘  └───────────────┘  └───────────────┘         │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  CRITIC FINDINGS TABLE  —  ranked by severity               │  │
│   │  Severity │ Category │ File │ Line │ Message │ Suggestion   │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                        [ Copy as Markdown ]                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Contract

All agents communicate through typed Pydantic structs — no free text passing between components.

```
Finding
  ├── file_name    : str
  ├── line_number  : int
  ├── severity     : HIGH | MEDIUM | LOW
  ├── category     : security | logic | style
  ├── message      : str
  ├── suggestion   : str
  └── agent        : security | logic | style

AgentResult
  ├── agent        : security | logic | style
  ├── findings     : list[Finding]
  └── error        : str | None         ← populated if agent failed

CriticReport
  ├── findings     : list[Finding]      ← deduplicated + ranked
  ├── summary      : str
  ├── verdict      : APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION
  └── verdict_reason : str
```

---

## Why `asyncio.gather()`?

The three specialist agents are **I/O-bound** — they spend their time waiting for OpenAI API responses over the network. `asyncio.gather()` fires all three simultaneously so total wait time equals the slowest agent, not the sum of all three.

```
Sequential (without gather):  5s + 5s + 5s = 15 seconds
Parallel   (with gather):     max(5s, 5s, 5s) = ~5 seconds
```

`return_exceptions=True` ensures one agent timing out does not cancel the others — the Critic works with whatever came back.

---

## Why Supervisor is Python, not an LLM

The Supervisor's job is to call three functions and wait. That is control-flow code — not a reasoning task. Using an LLM here would be slower, more expensive, and less reliable. This is a deliberate design choice that demonstrates knowing **when not to use an LLM**.

---

## Project Structure

```
pr_review_agent/
├── README.md
├── requirements.md
└── src/
    ├── app.py                    ← Flask app — routes + request handling
    ├── requirements.txt
    ├── .env                      ← OPENAI_API_KEY, GITHUB_TOKEN
    ├── templates/
    │   └── index.html            ← UI — input form + results page
    ├── agents/
    │   ├── security_agent.py     ← Finds security vulnerabilities
    │   ├── logic_agent.py        ← Finds logic bugs
    │   ├── style_agent.py        ← Finds style issues
    │   └── critic_agent.py       ← Deduplicates, ranks, verdict
    ├── models/
    │   └── schemas.py            ← Pydantic models — Finding, AgentResult, CriticReport
    ├── supervisor/
    │   └── pipeline.py           ← asyncio.gather() orchestration
    └── utils/
        └── github.py             ← Fetch PR diff from GitHub API
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Async orchestration | asyncio |
| LLM | OpenAI gpt-4o-mini |
| Structured outputs | OpenAI structured outputs + Pydantic |
| GitHub diff fetching | GitHub REST API |
| Frontend | HTML, CSS, JavaScript |
| Config | python-dotenv |

No LangChain. No LangGraph. The orchestration logic is the project.

---

## Setup & Run

**1. Install dependencies**
```bash
cd pr_review_agent/src
pip install -r requirements.txt
```

**2. Add your OpenAI key to `.env`**
```
OPENAI_API_KEY="sk-proj-..."
GITHUB_TOKEN=""   # optional — only needed for private repos
```

**3. Run**
```bash
python app.py
```

**4. Open in browser**
```
http://localhost:5002
```

---

## Key Concepts Demonstrated

| Concept | Where |
|---|---|
| Agent separation of concerns | Each specialist has a tight, non-overlapping system prompt |
| Typed inter-agent communication | Pydantic structs between every agent — no free text |
| Parallel orchestration | `asyncio.gather()` — concurrent agent execution |
| Structured LLM output | OpenAI structured outputs — no fragile JSON parsing |
| Graceful failure handling | `return_exceptions=True` — partial failures never crash the pipeline |
| Deliberate non-use of LLM | Supervisor is Python code, not an LLM |
| Critic as synthesis layer | Deduplication, ranking, and verdict in one reasoned step |
