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

A retrieval-augmented generation pipeline for AI/ML research question answering.

**Key concepts:** Multi-tier retrieval · Vector search · Document chunking · LLM grounding

**Tech:** Python · FAISS · OpenAI · LangChain

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
