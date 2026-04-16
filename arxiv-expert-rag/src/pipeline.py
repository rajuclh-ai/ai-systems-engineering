"""Pipeline — wires ingest, embed, retrieve, and generate into two entry points."""

import logging

from .embed import embed_papers
from .generator import Answer, generate_answer
from .ingest import run_ingest
from .retriever import Chunk, Retriever

logger = logging.getLogger(__name__)

_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def run_ingest_pipeline() -> dict:
    """
    Fetch new ArXiv papers and embed them into ChromaDB.

    Returns:
        dict with 'new_papers' and 'chunks_added' counts.
    """
    logger.info("Starting ingest pipeline")
    new_papers = run_ingest()

    chunks_added = 0
    if new_papers > 0:
        chunks_added = embed_papers()
    else:
        logger.info("No new papers — skipping embedding step")

    return {"new_papers": new_papers, "chunks_added": chunks_added}


def run_query_pipeline_with_context(question: str, top_k: int | None = None) -> tuple[Answer, list[Chunk]]:
    """
    Answer a research question and return retrieved chunks alongside the answer.
    Used by the eval framework — RAGAS needs both the answer and the source contexts.

    Returns:
        (Answer, list[Chunk]) — answer dataclass + raw retrieved chunks.
    """
    logger.info(f"Query pipeline (with context): {question[:80]}")
    retriever = _get_retriever()
    chunks = retriever.search(question, top_k=top_k)
    answer = generate_answer(question, chunks)
    return answer, chunks


def run_query_pipeline(question: str, top_k: int | None = None) -> Answer:
    """
    Answer a research question using the RAG pipeline.

    Args:
        question: Natural language question about AI/ML research.
        top_k:    Number of chunks to retrieve (defaults to settings.top_k).

    Returns:
        Answer dataclass with text, sources, and token count.
    """
    logger.info(f"Query pipeline: {question[:80]}")
    retriever = _get_retriever()
    chunks = retriever.search(question, top_k=top_k)
    return generate_answer(question, chunks)


def get_stats() -> dict:
    """Return database statistics."""
    retriever = _get_retriever()
    from .config import settings

    paper_files = list(settings.papers_dir.glob("*.txt"))
    categories: dict[str, int] = {}
    for f in paper_files:
        cat = f.stem.split("_")[0] if "_" in f.stem else "unknown"
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "papers": len(paper_files),
        "chunks": retriever.chunk_count,
        "categories": categories,
    }
