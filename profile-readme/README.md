# Raju

Staff engineer with 18 years building distributed systems at scale — Kafka pipelines, Flink streaming, event-driven microservices. Now applying those same engineering principles to LLM-based systems.

The pattern I keep finding: the hard problems in AI (reliability, observability, fault tolerance, testability) are the same problems distributed systems solved a decade ago. The solutions just need translating.

---

## Projects

### [LLM Eval Framework](https://github.com/rajuclh-ai/ai-systems-engineering/tree/main/llm-eval-framework)

Automated evaluation pipeline that runs in CI and fails the build when AI quality regresses.
Evaluates a RAG pipeline and a multi-agent PR reviewer — RAGAS metrics for retrieval quality,
LLM-as-judge for agent behavior. Prevents silent quality regressions before they reach users.

`ragas` `openai` `pytest` `github-actions`

---

### [PR Review Agent](https://github.com/rajuclh-ai/ai-systems-engineering/tree/main/pr_review_agent)

Multi-agent pipeline that reviews pull request diffs for security issues, logic bugs, and style problems.
Three specialist agents run in parallel via `asyncio.gather()`, a Critic synthesises and deduplicates.
Typed Pydantic contracts between agents — no free-text passing, no silent failures.

`python` `openai` `asyncio` `pydantic` `flask`

---

### [ArXiv Expert RAG](https://github.com/rajuclh-ai/ai-systems-engineering/tree/main/arxiv-expert-rag)

RAG system that ingests AI/ML research papers from ArXiv and answers natural language questions against them.
Incremental ingestion, ChromaDB vector store, grounded generation — answers cite the source chunks,
not the model's training data.

`python` `chromadb` `sentence-transformers` `openai`

---

## Engineering Philosophy

The instinct from distributed systems that transfers most directly to AI:

| Distributed Systems | Applied to AI |
|---|---|
| Microservice separation of concerns | Specialist agents with non-overlapping scopes |
| Typed message contracts | Pydantic structs between agents — no free text |
| Parallel service calls | `asyncio.gather()` for concurrent agent execution |
| Circuit breakers | `return_exceptions=True` — partial failures never crash the pipeline |
| Observability first | Every eval run logged, metrics trended, regressions caught in CI |

---

## Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6B35?style=flat)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat&logo=github-actions&logoColor=white)
![Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=flat&logo=apache-kafka&logoColor=white)
![Flink](https://img.shields.io/badge/Apache_Flink-E6526F?style=flat&logo=apache-flink&logoColor=white)
