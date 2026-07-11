# ArXiv Expert RAG

A Retrieval-Augmented Generation (RAG) system that answers natural language questions about the latest AI/ML research papers from ArXiv.

This project ships **two implementations of the same system** — pick the one that fits your goal:

| | [Notebook](#notebook--for-learning--research) | [Production](#production--for-real-deployment) |
|---|---|---|
| Goal | Understand how RAG works step by step | Deploy, extend, and maintain a real system |
| Interface | Jupyter cells | CLI + importable Python modules |
| Who it's for | Learners, researchers, prototypers | Engineers building on top of RAG |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION PIPELINE                       │
│                                                                 │
│  ArXiv RSS Feeds          Paper Files          ChromaDB         │
│  (cs.AI, cs.LG)  ──────►  ./papers/*.txt  ──────►  ./chroma_db │
│                   fetch    (incremental)    embed               │
│                            seen.json        (upsert, no dups)  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         QUERY PIPELINE                          │
│                                                                 │
│  User Question                                                  │
│       │                                                         │
│       ▼                                                         │
│  Embed Question  ──►  ChromaDB Semantic Search  ──►  Top-5      │
│  (MiniLM-L6-v2)        (cosine similarity)          Chunks      │
│                                                        │        │
│                                                        ▼        │
│                                                  GPT-4o-mini    │
│                                                  (grounded      │
│                                                   answer +      │
│                                                   citations)    │
└─────────────────────────────────────────────────────────────────┘
```

### Stack

| Component       | Technology                          |
|-----------------|-------------------------------------|
| Data source     | ArXiv RSS feeds (cs.AI + cs.LG)     |
| Embeddings      | `all-MiniLM-L6-v2` (local, free)    |
| Vector database | ChromaDB (persistent, local)        |
| LLM             | GPT-4o-mini via OpenAI API          |
| CLI             | Click                               |
| Config          | pydantic-settings                   |
| Tests           | pytest                              |

---

## Project Structure

```
arxiv-expert-rag/
│
├── notebook/
│   └── arxiv_expert_rag.ipynb   # Self-contained notebook — learning & research
│
├── src/                         # Production implementation
│   ├── config.py                # Centralized settings via pydantic-settings + .env
│   ├── ingest.py                # ArXiv RSS fetcher with incremental seen.json manifest
│   ├── embed.py                 # Text chunker + ChromaDB upsert
│   ├── retriever.py             # Semantic search (Retriever class)
│   ├── generator.py             # GPT-4o-mini answer generation
│   └── pipeline.py              # Orchestrates ingest and query pipelines
│
├── tests/                       # pytest suite — all externals mocked
│   ├── conftest.py
│   ├── test_ingest.py
│   ├── test_embed.py
│   ├── test_retriever.py
│   └── test_pipeline.py
│
├── cli.py                       # Entry point: ingest / query / stats
├── .env.example
└── requirements.txt
```

---

## Notebook — For Learning & Research

**`notebook/arxiv_expert_rag.ipynb`**

Use this when you want to **understand how RAG works** or **experiment with the pipeline** interactively. The notebook walks through every step with explanations, so you can see exactly what's happening at each stage — fetching papers, chunking, embedding, storing in ChromaDB, and generating a grounded answer.

**When to use the notebook:**
- Learning RAG architecture from scratch
- Prototyping changes to the chunking or retrieval strategy
- Exploring what papers were fetched and how they were chunked
- Presenting or teaching the concepts to others
- One-off research queries where you want full visibility

**How to run:**
```bash
pip install -r requirements.txt
jupyter notebook notebook/arxiv_expert_rag.ipynb
```
1. Add your `OPENAI_API_KEY` directly in the Step 5 cell
2. Run all cells top to bottom — each step is labelled and explained

The notebook is fully self-contained. Every step is visible, inspectable, and re-runnable independently.

---

## Production — For Real Deployment

**`src/` + `cli.py`**

Use this when you want to **run the system reliably**, **automate ingestion**, or **build something on top of it**. This is a proper Python application — modular, tested, configurable, and safe to run repeatedly without side effects.

**When to use production:**
- Running ingestion on a schedule (cron job, CI pipeline)
- Querying from scripts, APIs, or other tools
- Extending the system (add new data sources, swap the LLM, add a web frontend)
- Any context where you need tests, logging, and environment-based config

### Setup

```bash
git clone https://github.com/rajuclh-ai/ai-systems-engineering.git
cd ai-systems-engineering/arxiv-expert-rag
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
```

### Ingest papers

```bash
python cli.py ingest
```

Fetches the latest papers from ArXiv (cs.AI + cs.LG), saves them to `./papers/`, and embeds them into ChromaDB. **Re-running is safe** — a `seen.json` manifest tracks which papers have already been processed. Only new papers are fetched and embedded.

### Query

```bash
python cli.py query "What are the latest techniques for improving LLM efficiency?"
python cli.py query "What research exists on AI agents and reasoning?"
python cli.py query "What evaluation benchmarks are used for large language models?"
python cli.py query "..." --top-k 8   # retrieve more chunks
```

### Stats

```bash
python cli.py stats
```

### Run tests

```bash
pytest tests/ -v
```

All 25 tests run fully offline — OpenAI, ChromaDB, and ArXiv RSS are mocked.

---

## Example Output

```
Question: What are the latest techniques for improving LLM efficiency?
============================================================

Answer:
Based on the retrieved papers, recent work focuses on two directions.
"Efficient Attention Mechanisms for Large Language Models" proposes sparse
attention patterns that reduce compute by 40% with minimal accuracy loss...

Sources (2):
  [cs.LG] Efficient Attention Mechanisms for Large Language Models
           https://arxiv.org/abs/...
  [cs.AI] LoRA variants for memory-efficient fine-tuning
           https://arxiv.org/abs/...

Tokens used: 312
```

---

## How They Differ

| | Notebook | Production (`src/`) |
|---|---|---|
| **Purpose** | Learning, research, prototyping | Reliable, repeatable, deployable |
| **Ingestion** | Re-fetches everything on every run | Incremental — only new papers |
| **Interface** | Jupyter cells, step by step | `python cli.py ingest / query / stats` |
| **Config** | Hardcoded values in cells | `.env` + pydantic-settings |
| **Data types** | Plain dicts | `Paper`, `Chunk`, `Answer` dataclasses |
| **Logging** | `print()` statements | Structured `logging` with timestamps |
| **Error handling** | Bare exceptions | Graceful fallbacks with logged errors |
| **Tests** | None | 25 pytest tests, all externals mocked |
| **Extensibility** | Edit the notebook | Import `src/` modules, swap components |
| **LLM** | GPT-4o-mini | GPT-4o-mini |
| **Embeddings** | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 |
| **Vector DB** | ChromaDB | ChromaDB |

---

## Key Concepts

### RAG (Retrieval-Augmented Generation)
```
Normal LLM:  Question → LLM answers from training memory (may be outdated/hallucinated)
RAG:         Question → Search YOUR documents → Feed relevant chunks to LLM → Grounded answer
```
The LLM only sees content you retrieved — it cannot hallucinate about papers it hasn't been shown.

### Semantic Search vs Keyword Search
```
Keyword: "LoRA"  → finds only papers containing the exact word "LoRA"
Semantic: "LoRA" → also finds "parameter-efficient fine-tuning", "low-rank adaptation"
```

### Why Incremental Ingestion?
A `seen.json` manifest tracks every fetched paper URL. Re-running `ingest` skips already-processed papers — no duplicate chunks, no redundant embedding calls, no wasted tokens.

### What is Cosine Similarity?
Cosine similarity measures how similar two pieces of text are in meaning — by measuring the angle between their embedding vectors.

```
"transformer attention"       →  [0.23, -0.11, 0.87, ...]  ─┐
"self-attention mechanism"    →  [0.21, -0.09, 0.85, ...]  ─┴─► small angle → high similarity
"stock market prediction"     →  [-0.54, 0.33, -0.12, ...] ────► large angle → low similarity
```

Two texts with similar meaning point in nearly the same direction in vector space — the angle between them is small, so cosine similarity is high (close to 1.0). Unrelated texts point in different directions — large angle, low similarity (close to 0.0).

This is how ChromaDB finds the most relevant chunks for a query: it embeds the question into the same vector space as all stored chunks, then returns the ones with the smallest angle — the closest meaning match.
