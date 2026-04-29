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
         ├── risk > 0.7 ────────────────────────────────┐
         │                                               │
         │                                               ▼
         │                                   ┌───────────────────┐
         │                                   │ Human Checkpoint  │  LangGraph interrupt()
         │                                   │                   │  Agent pauses — engineer reviews
         │                                   │                   │  POST /approval → APPROVE | REJECT
         │                                   └────────┬──────────┘
         │                                            │ APPROVE
         ▼ ◄──────────────────────────────────────────┘
┌───────────────────┐
│  Executor Node    │  RESTART → real Flink REST API (when FLINK_REST_URL set)
│                   │  REROUTE | SCHEMA_PATCH | QUARANTINE | SAVEPOINT_REDEPLOY → simulated
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

| Anomaly | Strategy | Risk Score | HITL? | Execution |
|---|---|---|---|---|
| `LAG_SPIKE` | `RESTART` or `REROUTE` | 0.3 / 0.6 | No | Simulated |
| `LAG_SPIKE_HIGH_CPU` | `REROUTE` only | 0.6 | No | Simulated |
| `SCHEMA_DRIFT` | `SCHEMA_PATCH` | 0.5 | No | Simulated |
| `JOB_FAILURE` | `RESTART` | 0.3 | No | **Real Flink REST API** |
| `NULL_SPIKE` | `QUARANTINE` or `ALERT_ONLY` | 0.6 / 0.1 | No | Simulated |
| `RESTART_STORM` | `SAVEPOINT_REDEPLOY` | 0.8 | **Yes** | Simulated |
| `RESTART_STORM + LAG` | `SAVEPOINT_REDEPLOY + LAG_CATCHUP` | 0.9 | **Yes** | Simulated |
| Any (low confidence) | `ALERT_ONLY` | 0.1 | No | Simulated |

Risk score > 0.7 → Human approval required before execution.

---

## Out of Scope

| Item | Reason |
|---|---|
| Real Kafka/Flink event ingestion | Events are triggered manually via `POST /incidents`. No poller or Kafka consumer. |
| All strategies except RESTART | REROUTE, SCHEMA_PATCH, QUARANTINE, SAVEPOINT_REDEPLOY remain simulated. |
| SAVEPOINT_REDEPLOY with real Flink | Requires async polling loop — planned for a future iteration. |
| Production authentication | No API key auth on endpoints — not the focus of this prototype. |
| Async API under load | `graph.invoke()` is synchronous — concurrent incidents are not handled. |
| Prometheus metrics | No counters or latency tracking — stdout logs only. |
| Postgres | SQLite only — MemorySaver is in-memory and does not survive restarts. |

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Monitor Node | Rule-based (no LLM) | Deterministic, explainable, testable — LLM adds no value for threshold checks |
| Learning Node | Passive memory | LLM reasons over past incidents as context — no automated feedback loops |
| HITL payload | Minimal: `thread_id` + `decision` | Clean API contract — engineer has full context in the UI |
| Simulator | Static JSON files per scenario | Deterministic tests — same input always produces same output |
| FastAPI contracts | Typed Pydantic on every endpoint | Consistent with agent layer — typed everywhere, self-documenting |
| Memory store | SQLite via SQLAlchemy | Real relational DB, zero infrastructure, easy upgrade path to Postgres |
| LLM | gpt-4o-mini | Cost-efficient for high-frequency monitoring — handles diagnosis well |
| Orchestration | LangGraph over raw asyncio | Durable state, HITL interrupts, crash recovery — not possible with asyncio |
| RESTART execution | Real Flink REST API | One real integration changes the story from simulation to prototype |
| Flink job ID | Passed in request metrics | Caller owns the real job ID — no hidden discovery logic in the agent |

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
| Flink integration | httpx → Flink REST API |
| Local Flink cluster | Docker Compose + StateMachineExample |
| Testing | pytest (67 unit tests, all LLM calls mocked) + integration tests |
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
│   ├── nodes/
│   │   ├── monitor.py        # Rule-based anomaly classification
│   │   ├── diagnosis.py      # LLM root cause analysis
│   │   ├── remediation.py    # LLM fix strategy selection
│   │   ├── executor.py       # Fix execution (RESTART = real, others = simulated)
│   │   └── learning.py       # SQLite incident store
│   └── tools/
│       └── flink_client.py   # FlinkRestClient + FlinkSimClient
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
├── docker/
│   ├── docker-compose.yml    # Flink jobmanager + taskmanager + init
│   ├── init-flink.sh         # Uploads JAR and submits StateMachineExample on startup
│   └── README.md             # Flink local run instructions
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
│   ├── test_api.py
│   └── integration/
│       └── test_flink_executor.py  # Requires FLINK_REST_URL — skipped in CI
└── docs/
    └── Self-Healing Pipeline Agent.md   # Full requirements + session context
```

---

## Build Status

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Project structure, Pydantic models, test fixtures | ✅ Done |
| Week 1 | AgentState, Monitor Node, event simulator, test_monitor | ✅ Done |
| Week 2 | Diagnosis, Remediation, Executor, Learning, graph wiring | ✅ Done |
| Week 3 | FastAPI, approval endpoint, CI, README | ✅ Done |
| Gap 1 | Real Flink RESTART via Docker + FlinkRestClient | ✅ Done |

---

## Setup

```bash
# Install dependencies
pip install uv
uv sync --extra dev

# Configure environment
cp .env.example .env
# Set OPENAI_API_KEY (required)
# Set FLINK_REST_URL=http://localhost:8081 to enable real Flink execution (optional)

# Run unit tests (no Flink needed)
uv run pytest tests/ --ignore=tests/integration -v

# Start the API
uv run uvicorn api.main:app --reload
```

---

## Running with Real Flink

```bash
# Terminal 1 — start Flink
cd docker
docker compose up

# Verify a job is running
curl http://localhost:8081/jobs | jq

# Get the real Flink job ID
curl -s http://localhost:8081/jobs | jq '.jobs[] | select(.status=="RUNNING") | .id'
```

Add to `.env`:
```
FLINK_REST_URL=http://localhost:8081
```

```bash
# Terminal 2 — start the API
uv run uvicorn api.main:app --reload

# Terminal 3 — trigger a job_failure incident with the real Flink job ID
curl -s -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": "enrichment-job-05",
    "event_type": "job_failure",
    "metrics": {
      "job_id": "<real-flink-job-id>",
      "error_code": "NPE",
      "restart_count": 1,
      "error_message": "NullPointerException in EnrichmentMapper"
    }
  }' | jq
```

Watch the Flink UI at [http://localhost:8081](http://localhost:8081) — the job goes `RUNNING → CANCELED → RUNNING`.

```bash
# Run integration tests (requires Flink running)
FLINK_REST_URL=http://localhost:8081 uv run pytest tests/integration/ -v
```

---

## Simulated Scenarios (no Flink needed)

```bash
# LAG_SPIKE — auto-resolved, no approval
curl -s -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d @simulator/scenarios/lag_spike.json | jq

# RESTART_STORM — pauses for human approval
curl -s -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d @simulator/scenarios/restart_storm.json | jq

# Approve (use thread_id from above response)
curl -s -X POST http://localhost:8000/approval/<thread_id> \
  -H "Content-Type: application/json" \
  -d '{"decision": "APPROVE"}' | jq
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
  "status": "resolved",
  "anomaly_type": "lag_spike",
  "severity": "critical",
  "risk_score": 0.6
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
