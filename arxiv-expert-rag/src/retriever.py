"""Semantic retrieval — embed a question and search ChromaDB for relevant chunks."""

import logging
from dataclasses import dataclass

import chromadb
from sentence_transformers import SentenceTransformer

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    title: str
    authors: str
    date: str
    category: str
    url: str
    chunk_index: int


class Retriever:
    def __init__(self) -> None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        self._embedder = SentenceTransformer(settings.embedding_model)
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self._collection = client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Retriever ready — {self._collection.count()} chunks in DB")

    def search(self, question: str, top_k: int | None = None) -> list[Chunk]:
        """Return the top-k most relevant chunks for a question."""
        k = top_k or settings.top_k
        embedding = self._embedder.encode([question]).tolist()
        results = self._collection.query(query_embeddings=embedding, n_results=k)

        chunks = []
        for text, meta in zip(results["documents"][0], results["metadatas"][0]):
            chunks.append(Chunk(
                text=text,
                title=meta.get("title", ""),
                authors=meta.get("authors", ""),
                date=meta.get("date", ""),
                category=meta.get("category", ""),
                url=meta.get("url", ""),
                chunk_index=meta.get("chunk", 0),
            ))

        logger.debug(f"Retrieved {len(chunks)} chunks for: {question[:60]}")
        return chunks

    @property
    def chunk_count(self) -> int:
        return self._collection.count()
