"""Tests for src/embed.py"""

from unittest.mock import MagicMock, patch

import pytest

from src.embed import chunk_text, _parse_paper_file


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_text_basic():
    text = " ".join([f"word{i}" for i in range(100)])
    chunks = chunk_text(text)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)


def test_chunk_text_overlap(monkeypatch):
    monkeypatch.setattr("src.embed.settings.chunk_size", 10)
    monkeypatch.setattr("src.embed.settings.chunk_overlap", 3)
    words = [f"w{i}" for i in range(25)]
    text = " ".join(words)
    chunks = chunk_text(text)
    # With size=10, overlap=3, step=7: chunks starting at 0, 7, 14, 21
    assert len(chunks) == 4


def test_chunk_text_short_text_is_single_chunk(monkeypatch):
    monkeypatch.setattr("src.embed.settings.chunk_size", 300)
    monkeypatch.setattr("src.embed.settings.chunk_overlap", 30)
    text = "short text with only a few words"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_empty_returns_empty():
    chunks = chunk_text("")
    assert chunks == []


# ---------------------------------------------------------------------------
# _parse_paper_file
# ---------------------------------------------------------------------------

def test_parse_paper_file(sample_paper_file):
    metadata, content = _parse_paper_file(sample_paper_file)
    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["authors"] == "Vaswani et al."
    assert metadata["category"] == "cs.AI"
    assert metadata["url"] == "https://arxiv.org/abs/1706.03762"
    assert "ABSTRACT" in content


def test_parse_paper_file_authors_truncated_to_200(tmp_path):
    long_authors = "A" * 300
    content = (
        f"Title: Test\n"
        f"Authors: {long_authors}\n"
        f"Date: 2024-01-01\n"
        f"Category: cs.AI\n"
        f"URL: https://example.com\n"
        f"{'=' * 60}\n\n"
        f"ABSTRACT:\nSome content.\n"
    )
    filepath = tmp_path / "test.txt"
    filepath.write_text(content)
    metadata, _ = _parse_paper_file(filepath)
    assert len(metadata["authors"]) <= 200


# ---------------------------------------------------------------------------
# embed_papers — upsert called correctly
# ---------------------------------------------------------------------------

def test_embed_papers_calls_upsert(sample_paper_file, monkeypatch):
    import numpy as np
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.array([[0.1] * 384])

    mock_col = MagicMock()
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_col

    with patch("src.embed.SentenceTransformer", return_value=mock_embedder), \
         patch("src.embed.chromadb.PersistentClient", return_value=mock_client):
        from src.embed import embed_papers
        total = embed_papers([sample_paper_file])

    assert total > 0
    assert mock_col.upsert.called


def test_embed_papers_returns_zero_for_empty_list():
    from src.embed import embed_papers
    result = embed_papers([])
    assert result == 0
