"""RAG sub-graph node: load testset from disk, generate with RAGAS if missing."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from config import settings
from eval_models.schemas import RagSample
from state.rag_state import RagEvalState

logger = logging.getLogger(__name__)


def load_testset_node(state: RagEvalState) -> dict:
    """Load arxiv_rag_testset.json; if absent, generate with RAGAS TestsetGenerator."""
    cfg = state["config"]
    path = Path(cfg.rag_dataset)

    if path.exists():
        samples = _load_from_disk(path)
        logger.info("Loaded %d RAG samples from %s", len(samples), path)
    else:
        logger.info("RAG testset not found — generating %d Q&A pairs with RAGAS", cfg.rag_generate_n)
        samples = _generate_testset(cfg)

    return {"samples": samples}


def _load_from_disk(path: Path) -> list[RagSample]:
    with open(path) as f:
        records = json.load(f)
    return [
        RagSample(question=r["question"], ground_truth=r["ground_truth"])
        for r in records
    ]


def _generate_testset(cfg) -> list[RagSample]:
    from ragas.testset import TestsetGenerator
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from langchain_community.document_loaders import DirectoryLoader, TextLoader

    papers_dir = Path(settings.rag_project_path) / "papers"
    loader = DirectoryLoader(str(papers_dir), glob="*.txt", loader_cls=TextLoader)
    docs = loader.load()
    logger.info("Loaded %d paper documents for testset generation", len(docs))

    llm = LangchainLLMWrapper(ChatOpenAI(
        model=cfg.model, temperature=cfg.temperature, api_key=settings.openai_api_key
    ))
    emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(api_key=settings.openai_api_key))

    generator = TestsetGenerator(llm=llm, embedding_model=emb)
    testset = generator.generate_with_langchain_docs(docs, testset_size=cfg.rag_generate_n)
    df = testset.to_pandas()

    samples = []
    records = []
    for _, row in df.iterrows():
        s = RagSample(
            question=str(row.get("user_input", row.get("question", ""))),
            ground_truth=str(row.get("reference", row.get("ground_truth", ""))),
        )
        samples.append(s)
        records.append({"question": s.question, "ground_truth": s.ground_truth})

    path = Path(cfg.rag_dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    logger.info("Generated testset saved to %s", path)

    return samples
