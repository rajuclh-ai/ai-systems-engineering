# Self-Healing Pipeline Agent

A production-grade LangGraph agent that monitors data pipeline failures, diagnoses root causes autonomously, proposes remediations, and learns from outcomes over time.

Built on real Flink/Kafka failure patterns — schema drift, consumer lag, job failures, null spikes, restart storms.

---

## Architecture

```
POST /incidents  (FastAPI)
        │
        ▼
┌───────────────────┐
│   Monitor Node    │  Rule-based. No LLM.
│                   │  Classifies anomaly type + severity
│                   │  Detects combinations (LAG_SPIKE_HIGH_CPU etc.)
└────────┬──────────┘
         │
         ├── UNKNOWN ──────────────────────────────────► Learning Node ──► END
         │
         ▼
┌───────────────────┐
│  Diagnosis Node   │  LLM-powered (gpt-4o-mini)
│                   │  Queries SQLite for similar past incidents
│                   │  Output: RootCause + confidence score
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ Remediation Node  │  LLM-powered
│                   │  Maps root cause → fix strategy
│                   │  Output: RemediationPlan + risk score
└────────┬──────────┘
         │
         ├── risk ≤ 0.7 ────────────────────────────────────────────┐
         │                                                           │
         ▼                                                           │
┌───────────────────┐                                               │
│ Human Checkpoint  │  LangGraph interrupt()                        │
│                   │  Agent pauses — engineer reviews:             │
│                   │  pipeline + anomaly + proposed fix + risk     │
│                   │  POST /approval → APPROVE | REJECT            │
└────────┬──────────┘                                               │
         │ APPROVE                                                   │
         ▼ ◄────────────────────────────────────────────────────────┘
┌───────────────────┐
│  Executor Node    │  Simulated action per strategy
│                   │  RESTART | REROUTE | SCHEMA_PATCH |
│                   │  QUARANTINE | SAVEPOINT_REDEPLOY | ALERT_ONLY
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Learning Node    │  Writes IncidentRecord to SQLite
│                   │  Future Diagnosis queries benefit from this
└───────────────────┘
         │
         ▼
LangSmith  (full trace per incident — every node, every LLM call)
```

---

## Failure Types

| Type | What it means | Example |
|---|---|---|
| `SCHEMA_DRIFT` | Kafka topic schema changed unexpectedly | New field added upstream, breaking downstream consumers |
| `LAG_SPIKE` | Consumer falling behind — messages accumulating | Flink job processing too slowly, lag at 5.7x threshold |
| `JOB_FAILURE` | Pipeline job crashed | NullPointerException in enrichment mapper |
| `NULL_SPIKE` | Sudden rise in null values in a field | `user_id` null rate jumped from 2% to 45% |
| `RESTART_STORM` | Flink job restarting repeatedly | OOM causing 14 restarts in 10 minutes |

---

## Fix Strategies

| Anomaly | Strategy | Risk Score | HITL? |
|---|---|---|---|
| `LAG_SPIKE` | `RESTART` or `REROUTE` | 0.3 / 0.6 | No |
| `LAG_SPIKE_HIGH_CPU` | `REROUTE` only | 0.6 | No |
| `SCHEMA_DRIFT` | `SCHEMA_PATCH` | 0.5 | No |
| `JOB_FAILURE` | `RESTART` | 0.3 | No |
| `NULL_SPIKE` | `QUARANTINE` or `ALERT_ONLY` | 0.6 / 0.1 | No |
| `RESTART_STORM` | `SAVEPOINT_REDEPLOY` | 0.8 | **Yes** |
| `RESTART_STORM + LAG` | `SAVEPOINT_REDEPLOY + LAG_CATCHUP` | 0.9 | **Yes** |
| Any (low confidence) | `ALERT_ONLY` | 0.1 | No |

Risk score > 0.7 → Human approval required before execution.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Monitor Node | Simple rule-based (no LLM) | Deterministic, explainable, testable — LLM adds no value for threshold checks |
| Learning Node | Passive memory | LLM reasons over past incidents as context — no automated feedback loops |
| HITL payload | Minimal: `thread_id` + `decision` | Clean API contract — engineer has full context in the UI |
| Simulator | Static JSON files per scenario | Deterministic tests — same input always produces same output |
| FastAPI contracts | Typed Pydantic on every endpoint | Consistent with agent layer — typed everywhere, self-documenting |
| Memory store | SQLite via SQLAlchemy | Real relational DB, zero infrastructure, easy upgrade path to Postgres |
| LLM | gpt-4o-mini | Cost-efficient for high-frequency monitoring — handles diagnosis well |
| Orchestration | LangGraph over raw asyncio | Durable state, HITL interrupts, crash recovery — not possible with asyncio |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM integration | LangChain + OpenAI gpt-4o-mini |
| Observability | LangSmith |
| Data contracts | Pydantic v2 |
| Config | pydantic-settings |
| API | FastAPI |
| Database | SQLite via SQLAlchemy |
| Testing | pytest (all LLM calls mocked) |
| CI | GitHub Actions |
| Package manager | uv |

---

## Project Structure

```
self-healing-pipeline-agent/
├── agent/
│   ├── graph.py              # LangGraph StateGraph — entry point
│   ├── state.py              # AgentState TypedDict
│   ├── checkpointer.py       # MemorySaver setup
│   └── nodes/
│       ├── monitor.py        # Rule-based anomaly classification
│       ├── diagnosis.py      # LLM root cause analysis
│       ├── remediation.py    # LLM fix strategy selection
│       ├── executor.py       # Simulated fix execution
│       └── learning.py       # SQLite incident store
├── models/
│   ├── events.py             # PipelineEvent + typed metrics per failure
│   ├── diagnosis.py          # RootCause
│   ├── remediation.py        # RemediationPlan + FixStrategy enum
│   ├── execution.py          # ExecutionResult + IncidentRecord
│   └── db.py                 # SQLAlchemy table definitions
├── api/
│   ├── main.py               # FastAPI app
│   └── routes/
│       ├── incidents.py      # POST /incidents — trigger agent
│       └── approval.py       # POST /approval — APPROVE | REJECT
├── simulator/
│   └── scenarios/            # Static JSON failure events
│       ├── lag_spike.json
│       ├── schema_drift.json
│       ├── job_failure.json
│       ├── null_spike.json
│       └── restart_storm.json
├── tests/
│   ├── conftest.py           # Fixtures + LLM mocks
│   ├── test_monitor.py
│   ├── test_diagnosis.py
│   ├── test_remediation.py
│   ├── test_executor.py
│   ├── test_learning.py
│   ├── test_graph.py
│   └── test_api.py
└── docs/
    └── Self-Healing Pipeline Agent.md   # Full requirements + session context
```

---

## Build Status

| Week | Scope | Status |
|---|---|---|
| Phase 0 | Project structure, Pydantic models, test fixtures | ✅ Done |
| Week 1 | AgentState, Monitor Node, event simulator, test_monitor | ✅ Done |
| Week 2 | Diagnosis, Remediation, Executor, Learning, graph wiring | ✅ Done |
| Week 3 | FastAPI, approval endpoint, CI, README | ✅ Done |

---

## Setup

```bash
# Install dependencies
pip install uv
uv sync

# Configure environment
cp .env.example .env
# Add OPENAI_API_KEY and LANGCHAIN_API_KEY

# Run tests
uv run pytest tests/ -v

# Start API
uv run uvicorn api.main:app --reload

# Trigger a simulated incident
curl -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d @simulator/scenarios/lag_spike.json
```

---

## API

### `POST /incidents`
Trigger the agent with a pipeline failure event.

```json
{
  "pipeline_id": "clickstream-flink-job-03",
  "event_type": "consumer_lag_spike",
  "metrics": {
    "current_lag": 2850000,
    "threshold": 500000,
    "cpu_pct": 94
  }
}
```

Response:
```json
{
  "thread_id": "abc-123",
  "status": "running",
  "anomaly_type": "lag_spike"
}
```

### `POST /approval/{thread_id}`
Resume a paused agent after human review.

```json
{ "decision": "APPROVE" }
```

---

## Observability

Set `LANGCHAIN_TRACING_V2=true` in `.env`. Every incident run is automatically traced in LangSmith — node by node, LLM call by LLM call, token usage included.
