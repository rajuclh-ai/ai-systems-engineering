"""RAG evaluator — generates testset if needed, runs RAGAS metrics, returns scores."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from src.config import EvalConfig, settings
from src.datasets.loader import RagSample, load_rag_dataset

logger = logging.getLogger(__name__)


@dataclass
class RagQuestionScore:
    question: str
    faithfulness: float
    answer_relevance: float
    context_recall: float
    context_precision: float


@dataclass
class RagEvalResult:
    scores: list[RagQuestionScore]
    aggregates: dict[str, float]
    tokens_used: int = 0


def _import_rag_pipeline(rag_project_path: str):
    """Dynamically import the arxiv-expert-rag pipeline without name-colliding with
    the eval framework's own `src` package.

    arxiv-expert-rag/src/ uses relative imports, so its modules must all be registered
    under the same parent package name. We use `rag_src` as that name.
    """
    import importlib.util

    rag_src_dir = Path(rag_project_path) / "src"
    pkg = "rag_src"

    # Sub-modules needed by pipeline.py (import order matters for dependencies)
    submodules = ["config", "embed", "ingest", "retriever", "generator", "pipeline"]

    # Register the package root first
    if pkg not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            pkg,
            str(rag_src_dir / "__init__.py"),
            submodule_search_locations=[str(rag_src_dir)],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[pkg] = mod
        spec.loader.exec_module(mod)

    for name in submodules:
        full_name = f"{pkg}.{name}"
        if full_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                full_name,
                str(rag_src_dir / f"{name}.py"),
                submodule_search_locations=[str(rag_src_dir)],
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[full_name] = mod
            spec.loader.exec_module(mod)

    return sys.modules[f"{pkg}.pipeline"].run_query_pipeline_with_context


def _generate_testset(cfg: EvalConfig) -> list[RagSample]:
    """
    Use RAGAS TestsetGenerator to synthesise Q&A pairs from the arxiv papers.
    Saves the result to cfg.rag_dataset so subsequent runs reuse it.
    """
    from ragas.testset import TestsetGenerator
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    logger.info(f"Generating {cfg.rag_generate_n} Q&A pairs with RAGAS TestsetGenerator")

    papers_dir = Path(cfg.rag_thresholds.get("_papers_dir", "")) or \
                 Path(settings.rag_project_path) / "papers"

    # Load documents from paper text files
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    loader = DirectoryLoader(
        str(Path(settings.rag_project_path) / "papers"),
        glob="*.txt",
        loader_cls=TextLoader,
    )
    docs = loader.load()
    logger.info(f"Loaded {len(docs)} paper documents for testset generation")

    generator_llm = LangchainLLMWrapper(ChatOpenAI(
        model=cfg.model, temperature=cfg.temperature, api_key=settings.openai_api_key
    ))
    critic_llm = LangchainLLMWrapper(ChatOpenAI(
        model=cfg.model, temperature=cfg.temperature, api_key=settings.openai_api_key
    ))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(api_key=settings.openai_api_key))

    generator = TestsetGenerator(llm=generator_llm, embedding_model=embeddings)
    testset = generator.generate_with_langchain_docs(docs, testset_size=cfg.rag_generate_n)
    df = testset.to_pandas()

    samples = []
    records = []
    for _, row in df.iterrows():
        sample = RagSample(
            question=str(row.get("user_input", row.get("question", ""))),
            ground_truth=str(row.get("reference", row.get("ground_truth", ""))),
        )
        samples.append(sample)
        records.append({"question": sample.question, "ground_truth": sample.ground_truth})

    cfg.rag_dataset.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.rag_dataset, "w") as f:
        json.dump(records, f, indent=2)
    logger.info(f"Testset saved to {cfg.rag_dataset}")
    return samples


def _run_live(samples: list[RagSample], cfg: EvalConfig) -> tuple[list[RagSample], int]:
    """Call the live RAG pipeline to fill in answer + contexts for each sample."""
    run_query = _import_rag_pipeline(settings.rag_project_path)
    total_tokens = 0
    enriched = []
    for s in samples:
        answer, chunks = run_query(s.question)
        total_tokens += answer.tokens_used
        enriched.append(RagSample(
            question=s.question,
            ground_truth=s.ground_truth,
            answer=answer.text,
            contexts=[c.text for c in chunks],
        ))
    return enriched, total_tokens


def _score_with_ragas(samples: list[RagSample], cfg: EvalConfig) -> list[RagQuestionScore]:
    """Run RAGAS metrics against the enriched samples."""
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_recall,
        context_precision,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    data = {
        "user_input": [s.question for s in samples],
        "response": [s.answer for s in samples],
        "retrieved_contexts": [s.contexts for s in samples],
        "reference": [s.ground_truth for s in samples],
    }
    dataset = Dataset.from_dict(data)

    llm = LangchainLLMWrapper(ChatOpenAI(
        model=cfg.model, temperature=cfg.temperature, api_key=settings.openai_api_key
    ))
    emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(api_key=settings.openai_api_key))

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_recall, context_precision],
        llm=llm,
        embeddings=emb,
    )

    df = result.to_pandas()
    scores = []
    for _, row in df.iterrows():
        scores.append(RagQuestionScore(
            question=str(row.get("user_input", "")),
            faithfulness=float(row.get("faithfulness", 0.0) or 0.0),
            answer_relevance=float(row.get("answer_relevancy", 0.0) or 0.0),
            context_recall=float(row.get("context_recall", 0.0) or 0.0),
            context_precision=float(row.get("context_precision", 0.0) or 0.0),
        ))
    return scores


def run_rag_eval(cfg: EvalConfig) -> RagEvalResult:
    """
    Full RAG evaluation run.

    1. If dataset file is missing → generate with RAGAS TestsetGenerator.
    2. Call the live RAG pipeline to get answers + contexts.
    3. Score with RAGAS metrics.
    4. Return per-question scores and aggregates.
    """
    samples = load_rag_dataset(cfg.rag_dataset)
    if not samples:
        logger.info("RAG testset not found — generating with RAGAS")
        samples = _generate_testset(cfg)

    logger.info(f"Running RAG pipeline on {len(samples)} questions")
    samples, tokens_used = _run_live(samples, cfg)

    logger.info("Scoring with RAGAS metrics")
    scores = _score_with_ragas(samples, cfg)

    metric_keys = ["faithfulness", "answer_relevance", "context_recall", "context_precision"]
    aggregates = {}
    for key in metric_keys:
        values = [getattr(s, key) for s in scores]
        aggregates[key] = round(sum(values) / len(values), 4) if values else 0.0

    return RagEvalResult(scores=scores, aggregates=aggregates, tokens_used=tokens_used)
