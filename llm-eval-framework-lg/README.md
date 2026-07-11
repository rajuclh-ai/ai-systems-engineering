# LLM Eval Framework — LangGraph Edition

> v2 of [llm-eval-framework](../llm-eval-framework) — rebuilt with LangGraph, LangChain, and LangSmith.
> v1 used raw OpenAI SDK, sequential evaluation loops, and imperative orchestration.
> This version adds parallel fan-out at two levels, LangSmith audit trails for every judge decision, and typed structured output replacing manual `json.loads()`.

---

## The Story

Evaluating AI systems is itself an AI problem.
The RAG pipeline and the PR review agent run in parallel — no reason to wait for one before starting the other.
Within agent evaluation, 7 test PRs are scored simultaneously instead of one at a time.
Every LLM judge decision is traced in LangSmith — when a metric drops you can drill in and see exactly which judge call failed and why.
The CLI interface stays the same. The orchestration underneath becomes a graph.

---

## Architecture

### Three Graphs

```
cli.py run
    │
    ▼
Top-level EvalGraph
    │
    ├── route_to_evaluators()
    │       │
    │       ├── Send("rag_eval",   state) ──────────────────┐
    │       └── Send("agent_eval", state) ──────────────┐   │  parallel
    │                                                    │   │
    │   ┌────────────────────────────────────────────┐   │   │
    │   │  RAG Sub-graph                             │◄──┘   │
    │   │                                            │       │
    │   │  load_testset_node                         │       │
    │   │      │                                     │       │
    │   │  Send() × 10 questions (parallel)          │       │
    │   │  rag_question_node × 10                    │       │
    │   │      │  Annotated[list[EnrichedSample], add]│       │
    │   │  ragas_scorer_node  ← ragas.evaluate()     │       │
    │   └────────────────────────────────────────────┘       │
    │                                                        │
    │   ┌────────────────────────────────────────────┐       │
    │   │  Agent Sub-graph                           │◄──────┘
    │   │                                            │
    │   │  load_testset_node                         │
    │   │      │                                     │
    │   │  Send() × 7 PRs (parallel)                 │
    │   │  score_pr_node × 7                         │
    │   │      │  Annotated[list[AgentPRScore], add] │
    │   │  aggregate_agent_node                      │
    │   └────────────────────────────────────────────┘
    │
    │   Annotated[list[EvalSubResult], add]
    │   (reducer merges RAG result + Agent result as sub-graphs complete)
    │
    ▼
aggregator_node → threshold_check_node → reporter_node → END
```

> No HITL — evaluation is a read-only operation. Results are written to disk.
> The engineer reads the report and decides. No production system is modified.

---

## Graph Flow

### Top-level nodes

| Node | Type | Description |
|---|---|---|
| `route_to_evaluators` | Router | `Send("rag_eval", state)` + `Send("agent_eval", state)` based on `--target` flag |
| `rag_eval` | Sub-graph | Full RAG evaluation — returns `EvalSubResult` |
| `agent_eval` | Sub-graph | Full Agent evaluation — returns `EvalSubResult` |
| `aggregator_node` | Rule-based | Merges both `EvalSubResult`s, computes total tokens and cost |
| `threshold_check_node` | Rule-based | Checks each metric against `eval_config.yaml` thresholds |
| `reporter_node` | Rule-based | Writes JSON result, appends to `metrics_log.jsonl`, generates markdown report |

### RAG sub-graph nodes

| Node | Type | Description |
|---|---|---|
| `load_testset_node` | Rule-based | Load `arxiv_rag_testset.json` — if missing, auto-generate with RAGAS `TestsetGenerator` from arxiv papers |
| `rag_question_node` | Rule-based | Call live `arxiv-expert-rag` pipeline for one question → return answer + retrieved chunks |
| `ragas_scorer_node` | LLM (RAGAS) | Receive all 10 enriched samples, run `ragas.evaluate()` → 4 metric scores |

### Agent sub-graph nodes

| Node | Type | Description |
|---|---|---|
| `load_testset_node` | Rule-based | Load `pr_agent_testset.json` (7 synthetic PRs with known bugs) |
| `score_pr_node` | LLM (judge) | Call live `pr_review_agent` on one diff, run all 3 LangChain judge chains |
| `aggregate_agent_node` | Rule-based | Average `pr_scores` reducer list → final aggregates dict |

---

## Where LLMs Are Used — and Why

Most nodes in this framework are plain Python: load a file, call an API, average numbers, check a threshold, write a report.
LLMs are used in exactly two places. Both exist for the same reason: **the thing being evaluated is natural language, and only an LLM can judge natural language reliably.**

---

### LLM Use #1 — RAGAS inside `ragas_scorer_node`

**Node:** `ragas_scorer_node` (RAG sub-graph)
**File:** `nodes/rag/ragas_scorer.py`

RAGAS calls an LLM internally when it runs `ragas.evaluate()` on the 10 enriched samples.
You do not write this LLM code — RAGAS handles it as a black box.

The four metrics it computes all require semantic understanding:

| Metric | What it asks | Pipeline stage | Why an LLM, not a rule |
|---|---|---|---|
| **Faithfulness** | Is every claim in the answer entailed by the retrieved chunks? | Generation | Requires reading comprehension — judging whether a claim is supported by differently-worded context |
| **Answer Relevance** | Does the answer actually address the question asked? | Generation | Requires natural language understanding — an answer can be grounded yet off-topic |
| **Context Recall** | Did retrieval surface the right information needed to answer? | Retrieval | Requires semantic matching, not keyword matching |
| **Context Precision** | Are the retrieved chunks focused, or noisy with irrelevant content? | Retrieval | Requires judgment about relevance — signal-to-noise can't be string-matched |

A regex or embedding similarity score cannot reliably answer any of these. RAGAS uses an LLM as a semantic judge.

---

### LLM Use #2 — Three judge chains inside `score_pr_node`

**Node:** `score_pr_node` (Agent sub-graph)
**Files:** `judges/llm_judge.py`, `judges/schemas.py`

The PR review agent outputs free-text comments. There is no structured signal to parse.
Three LangChain chains — each a `ChatPromptTemplate | ChatOpenAI | with_structured_output()` pipeline — turn that free text into typed metrics:

| Chain | Question it answers | Output type |
|---|---|---|
| `bug_recall` | Did any comment catch this specific known bug? | `BugCaughtResult(caught: bool, reason: str)` |
| `false_positive` | Is this comment raising a real concern or a non-issue? | `ValidConcernResult(valid: bool, reason: str)` |
| `comment_quality` | How accurate and actionable is this comment? | `CommentQualityResult(score: float, reason: str)` |

**Why an LLM is necessary here:**
The agent might comment *"the `>=` should be `>`"* when the known bug is *"off-by-one in age validation"*.
A string matcher would miss that. Only an LLM can bridge the gap between how the bug is described in the testset and how the agent phrased its finding.

**Why structured output (`with_structured_output`) instead of `json.loads()`:**
v1 used raw `openai.OpenAI()` and parsed the response with `json.loads()` — fragile and untyped.
v2 uses Pydantic schemas so the output is validated and typed at the call site, and every judge call is automatically traced in LangSmith.

```python
# v1 — fragile
response = client.chat.completions.create(...)
raw = json.loads(response.choices[0].message.content)
score = float(raw.get("score", 0.0))   # no validation, no trace

# v2 — typed + traced
chain = prompt | ChatOpenAI(model="gpt-4o-mini") | with_structured_output(CommentQualityResult)
result: CommentQualityResult = chain.invoke({"diff": diff, "comment": comment})
score = result.score   # validated, typed, visible in LangSmith
```

---

### Everything else is rule-based Python

| Node | What it does |
|---|---|
| `route_to_evaluators` | Reads `--target` flag, emits `Send()` calls |
| `load_testset_node` | Reads a JSON file from disk |
| `rag_question_node` | Calls the live RAG pipeline HTTP API |
| `aggregate_agent_node` | Averages a list of floats |
| `aggregator_node` | Merges two result dicts, sums token counts |
| `threshold_check_node` | Compares floats against thresholds in `eval_config.yaml` |
| `reporter_node` | Writes JSON, appends to JSONL, renders markdown |

If a node is not in the two LLM sections above, it contains no LLM call.

---

## Key Design Decisions

### 1. Two-level `Send()` fan-out

v1 ran RAG eval then Agent eval sequentially, and looped through PRs one at a time.
v2 fans out at two levels:

```
Level 1 (top-level graph):
  Sequential:  rag_eval(~2min) + agent_eval(~3min) = ~5min
  Parallel:    max(rag_eval, agent_eval)            = ~3min

Level 2 (agent sub-graph):
  Sequential:  score_pr × 7 = 7 × 30s = ~3.5min
  Parallel:    max(score_pr × 7)       = ~30s
```

### 2. Sub-graphs — not a flat graph

RAG eval and Agent eval are compiled as independent `StateGraph` instances and registered as nodes in the top-level graph. This keeps each evaluation domain self-contained — you can run, test, and reason about the RAG sub-graph independently from the Agent sub-graph.

```python
rag_subgraph   = build_rag_graph().compile()
agent_subgraph = build_agent_graph().compile()

workflow.add_node("rag_eval",   rag_subgraph)
workflow.add_node("agent_eval", agent_subgraph)
```

### 3. RAGAS stays — judge migrates to LangChain

RAGAS is the industry standard for RAG metrics. It stays unchanged for the four RAG scores (faithfulness, answer relevance, context recall, context precision).

The `llm_judge.py` calls — bug recall, false positive rate, comment quality — migrate from raw `openai.OpenAI()` to `ChatOpenAI + with_structured_output()`. This eliminates `json.loads()`, gives typed results, and traces every judge decision in LangSmith.

```python
# v1 — raw OpenAI SDK
response = client.chat.completions.create(...)
raw = json.loads(response.choices[0].message.content)
score = float(raw.get("score", 0.0))   # fragile

# v2 — LangChain structured output
chain = prompt | ChatOpenAI(model="gpt-4o-mini") | with_structured_output(CommentQualityResult)
result: CommentQualityResult = chain.invoke({"diff": diff, "comment": comment})
score = result.score   # typed, no json.loads, traced in LangSmith
```

### 4. LangSmith — audit trail for judge decisions

For an eval framework, observability is especially valuable. When `bug_recall` drops from 0.71 to 0.58 between runs, LangSmith shows exactly which judge calls changed:

```
LangSmith trace — run-2026-05-24T10-30Z
│
├── agent_eval (sub-graph)
│   ├── pr-001 → caught=true  "comment identified the >= boundary change"
│   ├── pr-002 → caught=false "comment discussed style, missed inverted condition"  ← drill in
│   └── pr-007 → caught=true  "comment flagged the comparison flip explicitly"
```

Without LangSmith, you only see the aggregate score. With it, you see which specific PR caused the regression.

### 5. `Annotated[list, add]` reducers at two levels

Same pattern as `pr_review_agent_lg`. Each parallel branch appends its result — no hardcoded merging:

```python
# Top-level — RAG result + Agent result merge here
eval_results: Annotated[list[EvalSubResult], add]

# RAG sub-graph — each rag_question_node appends one enriched sample
enriched: Annotated[list[EnrichedRagSample], add]

# Agent sub-graph — each score_pr_node appends one AgentPRScore
pr_scores: Annotated[list[AgentPRScore], add]
```

### 6. CLI stays — no FastAPI

Evaluation is a batch job with a CI gate, not an interactive system. `python cli.py run` is the right interface. LangGraph orchestrates internally; the CLI surface is unchanged.

---

## State Design

```python
# Top-level
class EvalState(TypedDict):
    config:        EvalConfig
    target:        str                                   # "all" | "rag" | "agent"
    run_id:        str
    eval_results:  Annotated[list[EvalSubResult], add]   # reducer
    overall:       Optional[str]                         # "PASS" | "FAIL"
    total_tokens:  int
    cost_usd:      float

# RAG sub-graph
class RagEvalState(TypedDict):
    config:     EvalConfig
    samples:    list[RagSample]
    enriched:   Annotated[list[EnrichedRagSample], add]  # reducer — one per question
    scores:     list[RagQuestionScore]
    aggregates: dict[str, float]

# Agent sub-graph
class AgentEvalState(TypedDict):
    config:     EvalConfig
    samples:    list[AgentSample]
    pr_scores:  Annotated[list[AgentPRScore], add]       # reducer — one per PR
    aggregates: dict[str, float]
```

---

## Data Contracts

```
EvalSubResult
  ├── target      : "rag" | "agent"
  ├── aggregates  : dict[str, float]
  └── tokens_used : int

RagQuestionScore
  ├── question          : str
  ├── faithfulness      : float
  ├── answer_relevance  : float
  ├── context_recall    : float
  └── context_precision : float

EnrichedRagSample
  ├── question     : str
  ├── ground_truth : str
  ├── answer       : str
  ├── contexts     : list[str]
  └── tokens_used  : int

AgentPRScore
  ├── pr_id               : str
  ├── bug_recall          : float
  ├── false_positive_rate : float
  ├── comment_quality     : float
  ├── bugs_caught         : int
  ├── bugs_missed         : int
  └── false_positives     : int

BugCaughtResult       (LLM judge structured output)
  ├── caught : bool
  └── reason : str

ValidConcernResult    (LLM judge structured output)
  ├── valid  : bool
  └── reason : str

CommentQualityResult  (LLM judge structured output)
  ├── score  : float   # 0.0 – 1.0
  └── reason : str
```

---

## Metrics Reference

### RAG Metrics (via RAGAS — unchanged from v1)

| Metric | What it measures | Threshold |
|---|---|---|
| Faithfulness | Is the answer grounded in retrieved context? No hallucination. | ≥ 0.70 |
| Answer Relevance | Does the answer address the question? | ≥ 0.70 |
| Context Recall | Did retrieval surface the right chunks? | ≥ 0.65 |
| Context Precision | Are retrieved chunks focused, not noisy? | ≥ 0.65 |

### Agent Metrics (LangChain LLM-as-judge)

| Metric | What it measures | Threshold |
|---|---|---|
| Bug Recall | Did any comment address each known bug (even with different wording)? | ≥ 0.70 |
| False Positive Rate | What fraction of comments raise non-issues? | ≤ 0.40 |
| Comment Quality | How accurate and actionable is each comment? (0.0–1.0) | ≥ 0.60 |

---

## Tech Stack

| Layer | v1 | v2 |
|---|---|---|
| LLM judge calls | `openai.OpenAI()` + `json.loads()` | `ChatOpenAI` + `with_structured_output()` |
| Orchestration | Imperative Python loops | LangGraph `StateGraph` + `Send()` |
| Parallelism | None (sequential) | `Send()` at two levels — eval targets + per PR/question |
| Observability | None | LangSmith (every judge call traced) |
| RAG scoring | RAGAS | RAGAS (unchanged) |
| State | Local variables | LangGraph `TypedDict` state with `Annotated` reducers |
| Config | pydantic-settings + YAML | pydantic-settings + YAML (unchanged) |
| Interface | `python cli.py run` | `python cli.py run` (unchanged) |
| Package manager | pip | uv |

---

## Project Structure

```
llm-eval-framework-lg/
│
├── cli.py                          # entry point — same interface as v1
├── eval_config.yaml                # thresholds and dataset paths (unchanged)
├── pyproject.toml
├── .env.example
│
├── graphs/
│   ├── eval_graph.py               # top-level StateGraph
│   ├── rag_graph.py                # RAG eval sub-graph
│   └── agent_graph.py              # Agent eval sub-graph
│
├── state/
│   ├── eval_state.py               # EvalState TypedDict
│   ├── rag_state.py                # RagEvalState TypedDict
│   └── agent_state.py              # AgentEvalState TypedDict
│
├── nodes/
│   ├── rag/
│   │   ├── load_testset.py         # load or generate testset with RAGAS
│   │   ├── rag_question_node.py    # call live RAG pipeline for one question
│   │   └── ragas_scorer.py         # run ragas.evaluate() on all enriched samples
│   ├── agent/
│   │   ├── load_testset.py         # load pr_agent_testset.json
│   │   ├── score_pr_node.py        # call agent + 3 judge chains for one PR
│   │   └── aggregate_agent.py      # average pr_scores into aggregates
│   └── shared/
│       ├── aggregator.py           # merge EvalSubResults, compute cost
│       ├── threshold_check.py      # PASS/FAIL per metric against thresholds
│       └── reporter.py             # JSON result + jsonl history + markdown report
│
├── judges/
│   ├── schemas.py                  # BugCaughtResult, ValidConcernResult, CommentQualityResult
│   └── llm_judge.py                # three LangChain chains with structured output
│
├── models/
│   └── schemas.py                  # EvalSubResult, RagQuestionScore, AgentPRScore, EnrichedRagSample
│
├── datasets/                       # carried over unchanged from v1
│   ├── arxiv_rag_testset.json
│   └── pr_agent_testset.json
│
├── outputs/                        # generated at runtime
│   ├── results/                    # per-run JSON
│   ├── history/                    # metrics_log.jsonl (append-only)
│   └── reports/                    # latest_report.md
│
└── tests/
    ├── conftest.py
    ├── test_rag_nodes.py
    ├── test_agent_nodes.py
    ├── test_judges.py
    └── test_graphs.py
```

---

## Running Locally

**1. Configure environment**

```bash
cp .env.example .env
# add your OPENAI_API_KEY
```

`.env` should contain:
```
OPENAI_API_KEY=sk-...
LANGCHAIN_TRACING_V2=true           # set to false to disable LangSmith
LANGCHAIN_API_KEY=ls__...           # required if tracing enabled
LANGCHAIN_PROJECT=llm-eval-framework-lg
RAG_PROJECT_PATH=../arxiv-expert-rag
AGENT_PROJECT_PATH=../pr_review_agent/src
```

**2. Install dependencies**

```bash
uv sync
# or: pip install -e .
```

**3. Run all evaluations**

```bash
python cli.py run
```

**4. Run a specific target**

```bash
python cli.py run --target rag      # RAG metrics only
python cli.py run --target agent    # Agent metrics only
```

**5. View history**

```bash
python cli.py history --last 10
```

---

## v1 vs v2 — What Changes, What Stays

| | Stays | Changes |
|---|---|---|
| `eval_config.yaml` | ✓ | — |
| `datasets/*.json` | ✓ | — |
| RAGAS for RAG scoring | ✓ | Wrapped in `ragas_scorer_node` |
| Judge prompts | ✓ | Wrapped in `ChatPromptTemplate` |
| CLI interface | ✓ | Calls graph instead of evaluators directly |
| Output format | ✓ | Same JSON / jsonl / markdown |
| Raw `openai.OpenAI()` | — | Replaced by `ChatOpenAI + with_structured_output()` |
| Sequential evaluation | — | Parallel via `Send()` at two levels |
| No observability | — | LangSmith traces every judge call |
| Imperative orchestration | — | LangGraph `StateGraph` with sub-graphs |
| pip | — | uv |
