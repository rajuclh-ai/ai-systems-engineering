"""Chunking and embedding — load paper files, chunk text, upsert into ChromaDB."""

import logging
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from .config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + settings.chunk_size
        chunks.append(" ".join(words[start:end]))
        start += settings.chunk_size - settings.chunk_overlap
    return chunks


def _parse_paper_file(filepath: Path) -> tuple[dict, str]:
    """Parse a paper .txt file into (metadata, content)."""
    lines = filepath.read_text(encoding="utf-8").split("\n")
    metadata = {
        "title":    lines[0].replace("Title: ", "").strip(),
        "authors":  lines[1].replace("Authors: ", "").strip()[:200],
        "date":     lines[2].replace("Date: ", "").strip(),
        "category": lines[3].replace("Category: ", "").strip(),
        "url":      lines[4].replace("URL: ", "").strip(),
        "source":   filepath.name,
    }
    content = "\n".join(lines[6:])
    return metadata, content


def embed_papers(paper_files: list[Path] | None = None) -> int:
    """
    Embed paper files and upsert into ChromaDB.

    Args:
        paper_files: list of .txt paths to embed; defaults to all files in papers_dir.

    Returns:
        Total number of chunks upserted.
    """
    if paper_files is None:
        paper_files = sorted(settings.papers_dir.glob("*.txt"))

    if not paper_files:
        logger.warning("No paper files found to embed")
        return 0

    logger.info(f"Loading embedding model: {settings.embedding_model}")
    embedder = SentenceTransformer(settings.embedding_model)

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks: list[str] = []
    all_metadata: list[dict] = []
    all_ids: list[str] = []

    for filepath in paper_files:
        metadata, content = _parse_paper_file(filepath)
        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{filepath.stem}_chunk_{i}"
            all_chunks.append(chunk)
            all_metadata.append({**metadata, "chunk": i})
            all_ids.append(chunk_id)

    logger.info(f"Embedding {len(all_chunks)} chunks from {len(paper_files)} papers")

    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch_chunks = all_chunks[i: i + BATCH_SIZE]
        batch_meta = all_metadata[i: i + BATCH_SIZE]
        batch_ids = all_ids[i: i + BATCH_SIZE]
        embeddings = embedder.encode(batch_chunks).tolist()

        collection.upsert(
            documents=batch_chunks,
            embeddings=embeddings,
            metadatas=batch_meta,
            ids=batch_ids,
        )
        logger.debug(f"Upserted chunks {i} → {i + len(batch_chunks)}")

    logger.info(f"Embedding complete — {len(all_chunks)} chunks in ChromaDB")
    return len(all_chunks)
