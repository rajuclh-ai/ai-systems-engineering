"""Shared pytest fixtures."""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PAPER_TEXT = textwrap.dedent("""\
    Title: Attention Is All You Need
    Authors: Vaswani et al.
    Date: 2017-06-12
    Category: cs.AI
    URL: https://arxiv.org/abs/1706.03762
    ============================================================

    ABSTRACT:
    The dominant sequence transduction models are based on complex recurrent or
    convolutional neural networks. We propose a new simple network architecture,
    the Transformer, based solely on attention mechanisms.
""")

SAMPLE_RSS_ENTRY = {
    "title": "Test Paper on Transformers",
    "summary": "<p>An abstract about transformers and attention mechanisms.</p>",
    "link": "https://arxiv.org/abs/0000.00001",
    "authors": [{"name": "Alice"}, {"name": "Bob"}],
    "published": "2024-01-15T00:00:00Z",
}


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_papers_dir(tmp_path: Path) -> Path:
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    return papers_dir


@pytest.fixture
def sample_paper_file(tmp_papers_dir: Path) -> Path:
    filepath = tmp_papers_dir / "cs.AI_001_Attention_Is_All_You_Need.txt"
    filepath.write_text(SAMPLE_PAPER_TEXT, encoding="utf-8")
    return filepath


@pytest.fixture
def seen_manifest(tmp_papers_dir: Path) -> Path:
    manifest = tmp_papers_dir / "seen.json"
    manifest.write_text(json.dumps([]), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# Mock ChromaDB collection
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_collection():
    col = MagicMock()
    col.count.return_value = 42
    col.query.return_value = {
        "documents": [[
            "The Transformer model uses attention mechanisms.",
            "Self-attention allows the model to process all positions simultaneously.",
        ]],
        "metadatas": [[
            {
                "title": "Attention Is All You Need",
                "authors": "Vaswani et al.",
                "date": "2017-06-12",
                "category": "cs.AI",
                "url": "https://arxiv.org/abs/1706.03762",
                "chunk": 0,
            },
            {
                "title": "Attention Is All You Need",
                "authors": "Vaswani et al.",
                "date": "2017-06-12",
                "category": "cs.AI",
                "url": "https://arxiv.org/abs/1706.03762",
                "chunk": 1,
            },
        ]],
    }
    return col


# ---------------------------------------------------------------------------
# Mock OpenAI response
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_openai_response():
    response = MagicMock()
    response.choices[0].message.content = "The Transformer uses self-attention mechanisms."
    response.usage.total_tokens = 120
    return response
