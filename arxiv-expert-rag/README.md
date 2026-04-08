# arxiv-expert-rag — RAG-Powered AI Research Q&A

Ask natural language questions about the latest AI/ML research papers from ArXiv. Built with Retrieval-Augmented Generation (RAG) — answers are grounded in actual paper content, not the LLM's training memory.

---

## What It Does

```
ArXiv RSS Feed (cs.AI + cs.LG)
        ↓
  Fetch 30 recent papers → save as .txt files
        ↓
  Split each paper into 300-word overlapping chunks
        ↓
  Embed chunks with sentence-transformers → 384-dimensional vectors
        ↓
  Store vectors + text + metadata in ChromaDB
        ↓
User Question → Embed → Semantic Search → Top 5 Chunks → GPT-4o-mini → Answer with Citations
```

---

## Example Output

```
❓ Question: What are the latest techniques for improving LLM efficiency?

🤖 Answer:
Based on the retrieved papers, recent work focuses on two main directions.
"Efficient Attention Mechanisms for Large Language Models" proposes sparse
attention patterns that reduce compute by 40% with minimal accuracy loss...

📚 Papers used as sources:
  [cs.LG] Efficient Attention Mechanisms for Large Language Models
          https://arxiv.org/abs/...
  [cs.AI] LoRA variants for memory-efficient fine-tuning
          https://arxiv.org/abs/...
```

---

## Stack

| Component | Technology | Why |
|---|---|---|
| Data Source | ArXiv RSS (cs.AI + cs.LG) | Public, recent, not in LLM training data |
| Web Scraping | `feedparser` + `BeautifulSoup` | Fetch and parse paper metadata |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Free, local, no API key needed |
| Vector Database | ChromaDB (persistent, local) | Semantic search over paper chunks |
| LLM | GPT-4o-mini (OpenAI API) | Generate grounded answers with citations |
| API Key | Loaded from `.env` file | No hardcoded secrets |

---

## Project Structure

```
arxiv-expert-rag/
├── arxiv_expert_rag.ipynb   ← main notebook (6 steps)
├── requirements.txt         ← all dependencies
├── .gitignore               ← excludes papers/, chroma_db/, .env
├── README.md
├── papers/                  ← downloaded paper .txt files (auto-created when run)
└── chroma_db/               ← vector database (auto-created when run)
```

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/arxiv-expert-rag.git
cd arxiv-expert-rag
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Add your OpenAI API key
Create a `.env` file inside the `arxiv-expert-rag/` folder:
```
OPENAI_API_KEY="sk-proj-..."
```

Then update the `load_dotenv` path in Step 5 of the notebook to:
```python
load_dotenv(".env")   # if .env is in the same folder as the notebook
```

> Get your OpenAI API key at: https://platform.openai.com/api-keys

### 4. Run the notebook
Open `arxiv_expert_rag.ipynb` and run all cells top to bottom.

---

## The 6 Steps

| Step | What it does |
|---|---|
| **1. Install & Imports** | Install packages + SSL fix for Mac certificate errors |
| **2. Paper Collection** | Fetch 15 papers each from cs.AI and cs.LG via RSS → save as `.txt` |
| **3. Chunking** | Split each paper into 300-word overlapping chunks |
| **4. Vector Database** | Embed all chunks → store in ChromaDB with cosine similarity |
| **5. RAG Pipeline** | Define `retrieve()` and `ask()` — load OpenAI key from `.env` |
| **6. Ask Questions** | Run 4 research questions through the full pipeline |

---

## Key Concepts

### RAG (Retrieval-Augmented Generation)
```
Normal LLM:  Question → AI answers from training memory (may be outdated)
RAG:         Question → Search YOUR papers → Feed relevant chunks to LLM → Grounded answer
```
The LLM only sees content you retrieved — it cannot hallucinate about papers it hasn't seen.

### Semantic Search vs Keyword Search
```
Keyword: "LoRA"    → finds only papers containing exact word "LoRA"
Semantic: "LoRA"   → also finds "parameter-efficient fine-tuning", "low-rank adaptation"
```

### Why ChromaDB?
Local, persistent vector database. No cloud account needed. Data stays on your machine. Survives kernel restarts — no need to re-embed on every run.

### Why Chunking?
Papers are too long to fit in one prompt. Splitting into 300-word chunks means:
- Only the relevant section is retrieved, not the whole paper
- More precise answers with better citations

---

## Re-running After a Break

| Scenario | What to run |
|---|---|
| Fresh data (new papers) | All 6 steps top to bottom |
| Existing data, new questions | Steps 1 → 5 → 6 only |
| Just testing questions | Steps 1, 5, 6 (imports + pipeline + ask) |

---

## What This Demonstrates

| Skill | Where used |
|---|---|
| Live API data collection | ArXiv RSS feed |
| Text processing pipeline | Chunking + cleaning abstracts |
| Vector embeddings | sentence-transformers |
| Vector database design | ChromaDB |
| RAG architecture | retrieve() + ask() pipeline |
| LLM integration | OpenAI GPT-4o-mini |
| Secure config management | API key from .env |
