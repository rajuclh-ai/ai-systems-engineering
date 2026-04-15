"""Tests for src/retriever.py"""

from unittest.mock import MagicMock, patch

import pytest

from src.retriever import Chunk, Retriever


def _make_retriever(mock_collection):
    import numpy as np
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.array([[0.1] * 384])

    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    with patch("src.retriever.SentenceTransformer", return_value=mock_embedder), \
         patch("src.retriever.chromadb.PersistentClient", return_value=mock_client):
        retriever = Retriever()

    retriever._embedder = mock_embedder
    return retriever


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def test_search_returns_chunks(mock_collection):
    retriever = _make_retriever(mock_collection)
    chunks = retriever.search("What is a Transformer?")
    assert len(chunks) == 2
    assert all(isinstance(c, Chunk) for c in chunks)


def test_search_chunk_fields_populated(mock_collection):
    retriever = _make_retriever(mock_collection)
    chunks = retriever.search("attention mechanisms")
    c = chunks[0]
    assert c.title == "Attention Is All You Need"
    assert c.category == "cs.AI"
    assert c.url == "https://arxiv.org/abs/1706.03762"
    assert isinstance(c.text, str)
    assert len(c.text) > 0


def test_search_respects_top_k(mock_collection):
    mock_collection.query.return_value = {
        "documents": [["chunk1"]],
        "metadatas": [[{
            "title": "T", "authors": "A", "date": "2024",
            "category": "cs.AI", "url": "https://x.com", "chunk": 0
        }]],
    }
    retriever = _make_retriever(mock_collection)
    retriever.search("question", top_k=1)
    call_kwargs = mock_collection.query.call_args.kwargs
    assert call_kwargs["n_results"] == 1


# ---------------------------------------------------------------------------
# chunk_count
# ---------------------------------------------------------------------------

def test_chunk_count(mock_collection):
    retriever = _make_retriever(mock_collection)
    assert retriever.chunk_count == 42
