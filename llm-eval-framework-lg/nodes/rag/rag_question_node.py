"""RAG sub-graph node: call the live arxiv-expert-rag pipeline for one question.

Invoked in parallel via Send() — one node call per question in the testset.
The state dict received here is NOT the full RagEvalState; it is the dict
passed by the Send() call: {"config": cfg, "sample": RagSample}.

Returns {"enriched": [EnrichedRagSample]} which the Annotated[list, add]
reducer in RagEvalState accumulates as each parallel call completes.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path

from config import settings
from eval_models.schemas import EnrichedRagSample, RagSample

logger = logging.getLogger(__name__)

# LangGraph runs parallel Send() nodes in a ThreadPoolExecutor.
# Guard the one-time import with a lock so only one thread does the
# importlib dance; all others wait and reuse the cached result.
_import_lock = threading.Lock()
_run_query_pipeline = None


def _import_rag_pipeline(rag_project_path: str):
    """Dynamically import arxiv-expert-rag without colliding with this project's packages.

    Uses double-checked locking: fast path (no lock) when already imported,
    slow path (locked) for the one-time importlib setup.
    """
    global _run_query_pipeline
    if _run_query_pipeline is not None:
        return _run_query_pipeline

    with _import_lock:
        # Re-check inside the lock — another thread may have finished while we waited.
        if _run_query_pipeline is not None:
            return _run_query_pipeline

        rag_src_dir = Path(rag_project_path) / "src"
        pkg = "rag_src"
        submodules = ["config", "embed", "ingest", "retriever", "generator", "pipeline"]

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

        pipeline_mod = sys.modules[f"{pkg}.pipeline"]

        # Warm up the ChromaDB retriever singleton inside the lock, before any
        # parallel thread can reach it. chromadb.PersistentClient is not safe to
        # initialise concurrently — calling _get_retriever() here guarantees the
        # singleton is fully built before the lock is released and the fan-out
        # threads start querying.
        logger.info("Warming up ChromaDB retriever (one-time, inside lock) …")
        pipeline_mod._get_retriever()

        _run_query_pipeline = pipeline_mod.run_query_pipeline_with_context
        return _run_query_pipeline


def rag_question_node(state: dict) -> dict:
    """Call the live RAG pipeline for one question and return the enriched sample.

    state keys expected: config, sample (RagSample)
    """
    cfg = state["config"]
    sample: RagSample = state["sample"]

    logger.info("RAG query: %s", sample.question[:80])

    run_query = _import_rag_pipeline(settings.rag_project_path)
    answer, chunks = run_query(sample.question)

    enriched = EnrichedRagSample(
        question=sample.question,
        ground_truth=sample.ground_truth,
        answer=answer.text,
        contexts=[c.text for c in chunks],
        tokens_used=answer.tokens_used,
    )

    return {"enriched": [enriched]}
