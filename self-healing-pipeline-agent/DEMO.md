# Self-Healing Pipeline Agent — Demo Prep

---

## The Story (say this first — 60 seconds)

> "In distributed data systems, pipeline failures are inevitable.
> The expensive part isn't the failure — it's the human interrupt cycle:
> alert fires, engineer gets paged, diagnoses manually, applies a fix, verifies it.
> That loop takes 15-30 minutes at 2am. This agent compresses it to under 60 seconds,
> autonomously — and when the risk is too high to act alone, it pauses and asks."

This one paragraph is your entire demo. Everything else is evidence for it.

---

## Demo Flow (8 minutes)

| Time | Action | What to say |
|---|---|---|
| 0:00 | Show architecture diagram | "Single agent, seven nodes, one shared state. Three nodes use an LLM — four are deterministic. That split is intentional." |
| 1:00 | Run Scenario 1 — show curl panel | "Consumer lag spike — 2.8M messages behind, 94% CPU. Watch what the monitor sees." |
| 1:30 | Replay nodes live | Narrate each node — see talking points below |
| 3:30 | Bridge to Scenario 3 | "That was simulated. Now a real Flink cluster." |
| 4:00 | Open Flink UI — show job RUNNING | "This is the job about to fail." |
| 4:30 | Show curl panel, explain payload | "Kafka topic repartitioned 8→12 partitions. Checkpoint state is incompatible. Flink already tried twice." |
| 5:00 | Press Enter — switch to Flink UI | Watch RUNNING → CANCELED → RUNNING |
| 6:30 | Replay nodes — Executor + Verification | "Cancelled the stuck job. Submitted fresh. Verified RUNNING via real Flink REST API." |
| 7:30 | Land the key insight | See below |

---

## Node Talking Points

**Monitor**
- Rule-based. No LLM. Deterministic threshold checks.
- *Why no LLM here:* "Anomaly classification is a lookup problem, not a reasoning problem. An LLM adds latency and non-determinism where I need speed and testability."

**Diagnosis**
- LLM queries SQLite for similar past incidents before reasoning.
- *What to highlight:* "It found 3 similar past incidents on this pipeline — all resolved with RESTART. That history becomes part of the LLM prompt. The agent gets smarter with every incident."

**Remediation**
- LLM maps root cause → fix strategy + risk score.
- *What to highlight:* "Risk score drives the branching. Below 0.70 — auto-execute. Above 0.70 — human checkpoint. The threshold is a single config value."

**Human Checkpoint** *(Scenario 2 only)*
- LangGraph `interrupt()` — graph state is persisted to SQLite, server can restart.
- *What to highlight:* "This isn't a sleep loop or a polling hack. LangGraph's interrupt suspends the graph at the node boundary. The state survives a server restart."

**Executor**
- RESTART = real Flink REST API (cancel + resubmit). All other strategies simulated.
- *What to highlight:* "One real integration changes the story. This isn't a toy."

**Verification**
- Polls `GET /jobs/{id}` every 5s for 60s. RUNNING → verified. Timeout → retry.
- *What to highlight:* "The agent doesn't trust its own action. It verifies the outcome independently."

**Learning**
- Writes incident record to SQLite. Future Diagnosis queries benefit.
- *What to highlight:* "Closed loop. The outcome of this incident becomes context for the next one on this pipeline."

---

## Key Lines to Land

1. **On the agent pattern:** "This is a single agent, not multi-agent. One graph, one shared state, seven nodes. Multi-agent adds coordination overhead — it's the right call when you have parallel workstreams or competing objectives. Here the problem is sequential and well-defined, so a structured single-agent pipeline is the better design."

2. **On the Monitor design:** "I deliberately kept the Monitor rule-based. The LLM is expensive — in compute, latency, and explainability. You use it where reasoning adds value, not where a threshold check will do."

3. **On LangGraph vs raw asyncio:** "LangGraph gives me durable state and interruptible graphs out of the box. With raw asyncio I'd be building a state machine from scratch and hand-rolling the HITL pause logic. That's not the interesting problem here."

4. **On the async API:** "POST /incidents returns in under 10ms. The agent runs in a background thread. The client polls. That's the only design that works when your graph can take 60 seconds and your LLM calls can fail."

5. **On the closing line:** "Every incident this agent handles is one fewer 2am page. And every outcome it stores makes the next diagnosis slightly more informed."

---

## Honest Scope (say this confidently, not apologetically)

| What's real | What's simulated | Why |
|---|---|---|
| RESTART via Flink REST API | All other strategies | One real integration proves the pattern |
| SQLite incident store | — | Real relational DB, zero infrastructure |
| LangGraph HITL interrupt | — | Real durable state, survives restarts |
| LangSmith traces | — | Full observability on every run |
| — | Kafka/Flink event ingestion | Events triggered manually — not the interesting problem |
| — | SAVEPOINT_REDEPLOY execution | Requires async polling loop — deferred |

---

## Anticipated Questions

**"Why gpt-4o-mini and not GPT-4?"**
Cost and latency. A monitoring agent runs on every failure — at scale that's hundreds of LLM calls per day. gpt-4o-mini handles root cause analysis well enough. GPT-4 is reserved for harder reasoning tasks.

**"What happens if the LLM picks the wrong strategy?"**
The risk score gates execution. A low-confidence diagnosis produces a low-risk plan, which may fall back to ALERT_ONLY. The human checkpoint catches high-risk decisions before they execute. Nothing irreversible happens without either a low risk score or human approval.

**"Why SQLite and not Postgres?"**
SQLite is a real relational database — it's not a toy. For this prototype, zero infrastructure overhead lets the focus stay on the agent design. The upgrade path is one SQLAlchemy connection string change.

**"Is this production-ready?"**
The patterns are — durable state, async API, typed contracts, HITL, observability. The gaps are documented honestly: no auth, no Prometheus metrics, SQLite not Postgres. This is a production-grade prototype that demonstrates the architecture works.

**"Why LangGraph over a custom state machine?"**
Durable checkpointing, interruptible graphs, and built-in LangSmith tracing are the three things I'd spend weeks building from scratch. LangGraph gives them for free. The graph structure also makes the agent logic auditable — you can read the edges and understand the decision flow without reading code.

---

## Node Output Format (demo replay)

Each completed node prints two sections during replay:

```
✓  NodeName    description
       received:           ← what this node was handed (inputs)
           key:   value
       <label>:            ← what this node produced (outputs)
           key:   value
```

- **received** (blue) — inputs passed into the node from previous state
- **label / output** (green or cyan) — the node's decision or result

| Node | received | output label |
|---|---|---|
| Monitor | pipeline_id, event_type, all raw metrics | `detected` — anomaly_type, classifier, severity reasoning, next node |
| Diagnosis | anomaly + severity, similar past incidents | `diagnosed` — primary_cause, contributing_factors, confidence |
| Remediation | root_cause, confidence, recommended_action | `decided` — strategy, risk_score, approval status |
| Human Checkpoint | strategy, risk_score | `awaiting` — approval instructions |
| Executor | strategy, human_decision | `executed` — action_taken, status, new_job_id (real Flink) |
| Verification | strategy, new_job_id | `result` — RUNNING ✓ or skipped/retry reason |
| Learning | anomaly, strategy, outcome, human_approved | `stored` — incident_id, note |

---

## Pre-Demo Checklist

- [ ] `docker compose down && docker compose up` — Flink cluster fresh
- [ ] `curl -s http://localhost:8081/jobs | jq` — confirm job RUNNING
- [ ] `uv run uvicorn api.main:app --reload` — API running on :8000
- [ ] `.env` has `OPENAI_API_KEY` and `FLINK_REST_URL=http://localhost:8081`
- [ ] Browser tab open: `http://localhost:8081` (Flink UI)
- [ ] Browser tab open: LangSmith project (if showing traces)
- [ ] Terminal font size increased for screen sharing
- [ ] Run `demo.py --scenario 1` once dry-run to warm the LLM cache
