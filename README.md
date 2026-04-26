# AI Systems Engineering

Production-ready AI systems built by applying distributed systems principles to large language models.

## Projects

### [PR Review Agent](./pr_review_agent)

A multi-agent AI pipeline that reviews GitHub pull requests using specialist agents running in parallel.

```
GitHub PR URL
      ↓
  Supervisor  (Python asyncio — not an LLM)
      ↓  asyncio.gather()
┌─────────────────────────────────────┐
│ SecurityAgent │ LogicAgent │ StyleAgent │  ← run in parallel
└─────────────────────────────────────┘
      ↓
  Critic Agent  →  deduplicate → rank → verdict
      ↓
  Structured Report (UI)
```

**Key concepts:** Multi-agent orchestration · Parallel async execution · Typed inter-agent communication (Pydantic) · Structured LLM outputs · Graceful failure handling

**Tech:** Python · Flask · OpenAI gpt-4o-mini · asyncio · Pydantic · GitHub REST API

---

### [Arxiv Expert RAG](./arxiv-expert-rag)

A retrieval-augmented generation pipeline that answers natural language questions about AI/ML research papers fetched from ArXiv.

```
ArXiv RSS (cs.AI, cs.LG)
      ↓  ingest + chunk
  ChromaDB  (vector store)
      ↓  similarity search
  Retrieved Chunks  →  GPT-4o-mini  →  Grounded Answer
```

**Key concepts:** Retrieval-augmented generation · Vector search · Incremental ingestion · LLM grounding · Two implementations (notebook for learning, production CLI)

**Tech:** Python · ChromaDB · sentence-transformers · OpenAI gpt-4o-mini

---

### [LLM Eval Framework](./llm-eval-framework)

An automated evaluation framework that tests the two systems above — runs in CI and fails the build when quality drops below defined thresholds.

```
eval_config.yaml (thresholds)
        ↓
    cli.py run
   ┌────┴────┐
   ▼         ▼
RAG Eval   Agent Eval
   │              │
RAGAS metrics   LLM-as-judge
faithfulness    bug recall
answer rel.     false positive rate
context recall  comment quality
   └────┬────┘
   PASS / FAIL  →  outputs/reports/latest_report.md
                →  outputs/history/metrics_log.jsonl  (trend log)
                →  GitHub Actions CI gate (exit 1 on FAIL)
```

**Key concepts:** LLM-as-judge evaluation · RAGAS metrics · Testset auto-generation · CI quality gates · Metric trend tracking

**Tech:** Python · RAGAS · OpenAI gpt-4o-mini · pytest (56 tests, all LLM calls mocked) · GitHub Actions

---

### [Self-Healing Pipeline Agent](./self-healing-pipeline-agent)

A production-grade LangGraph agent that monitors data pipeline failures, diagnoses root causes autonomously, proposes remediations, and learns from outcomes over time. Built on real Flink/Kafka failure patterns.

```
POST /incidents  (FastAPI)
        ↓
  Monitor Node    rule-based classification — no LLM
        ↓  conditional edge (anomaly_type)
  Diagnosis Node  LLM root cause analysis + SQLite memory query
        ↓
  Remediation Node  LLM fix strategy selection + risk scoring
        ↓  conditional edge (risk_score > 0.7?)
  Human Checkpoint  LangGraph interrupt() — APPROVE | REJECT
        ↓
  Executor Node   simulated fix execution per strategy
        ↓
  Learning Node   writes IncidentRecord to SQLite
        ↓
  LangSmith  (full trace per incident)
```

**Key concepts:** LangGraph stateful orchestration · Conditional routing · Human-in-the-loop interrupt/resume · LangSmith observability · SQLite incident memory · Durable state via MemorySaver

**Tech:** Python · LangGraph · LangChain · OpenAI gpt-4o-mini · LangSmith · FastAPI · SQLAlchemy · Pydantic · pytest (65 tests, all LLM calls mocked) · GitHub Actions

---

## Engineering Philosophy

Coming from 18 years building distributed systems (Kafka, Flink, microservices), I apply the same principles to AI applications:

| Distributed Systems | Applied to AI |
|---|---|
| Microservice separation of concerns | Specialist agents with non-overlapping scopes |
| Typed message contracts (Protobuf) | Pydantic structs between agents — no free text |
| Parallel service calls | `asyncio.gather()` for concurrent agent execution |
| Circuit breakers & fault tolerance | `return_exceptions=True` — partial failures never crash the pipeline |
| Know when not to add a service | Know when not to use an LLM (Supervisor is Python code) |
