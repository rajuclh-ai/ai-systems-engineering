# Self-Healing Pipeline Agent — Claude Instructions

## Project Goal

A production-grade LangGraph agent that monitors data pipeline failures,
diagnoses root causes autonomously, proposes remediations, and learns from
outcomes over time. Covers Kafka/Flink failure patterns: schema drift,
consumer lag, job failures, null spikes, restart storms.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph, conditional edges, MemorySaver) |
| LLM | OpenAI gpt-4o-mini via LangChain |
| Observability | LangSmith |
| Data contracts | Pydantic v2 |
| Config | pydantic-settings |
| API | FastAPI |
| Database | SQLite via SQLAlchemy |
| Testing | pytest |
| CI | GitHub Actions |
| Package manager | uv |

---

## Project Structure

```
self-healing-pipeline-agent/
├── agent/
│   ├── graph.py          # LangGraph StateGraph — entry point
│   ├── state.py          # AgentState TypedDict
│   ├── nodes/            # One file per node
│   └── tools/            # LangChain tools used by LLM nodes
├── models/               # All Pydantic models
├── api/                  # FastAPI app and routes
├── simulator/            # Static JSON failure scenarios
├── tests/                # pytest suite
└── docs/                 # Architecture and decisions
```

---

## Code Conventions

- All inter-node data passed via `AgentState` TypedDict — no free-form dicts
- All inputs and outputs typed with Pydantic models — no raw dicts between components
- Node functions signature: `def node_name(state: AgentState) -> dict`
- Return only the keys being updated — LangGraph merges partial updates
- Enums for all fixed-value fields (AnomalyType, Severity, FixStrategy, etc.)
- SQLAlchemy models in `models/db.py`, Pydantic models in `models/*.py`

---

## What NOT to Do

- Never pass raw dicts between agent nodes — always use typed models
- Never call OpenAI directly — always go through LangChain
- Never write tests that make real LLM calls — mock everything in conftest.py
- Never use print() for logging — use Python logging
- Monitor node must be rule-based only — no LLM calls
- Do not add features beyond what is in the requirements doc

---

## Test Conventions

- All LLM calls mocked via pytest fixtures in `tests/conftest.py`
- Tests must pass with `OPENAI_API_KEY=test-key`
- One test file per node/module
- Test the contract (inputs → outputs), not the implementation

---

## Requirements Reference

Full requirements, design decisions, and session context:
`docs/Self-Healing Pipeline Agent.md`
