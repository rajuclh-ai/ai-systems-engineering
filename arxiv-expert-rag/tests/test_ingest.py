"""Tests for src/ingest.py"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingest import Paper, _load_seen, _save_seen, fetch_papers, save_paper


# ---------------------------------------------------------------------------
# _load_seen / _save_seen
# ---------------------------------------------------------------------------

def test_load_seen_returns_empty_set_when_no_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("src.ingest.settings.seen_manifest", tmp_path / "seen.json")
    result = _load_seen()
    assert result == set()


def test_save_and_load_seen_roundtrip(tmp_path, monkeypatch):
    manifest = tmp_path / "papers" / "seen.json"
    monkeypatch.setattr("src.ingest.settings.seen_manifest", manifest)
    monkeypatch.setattr("src.ingest.settings.papers_dir", tmp_path / "papers")

    urls = {"https://arxiv.org/abs/1", "https://arxiv.org/abs/2"}
    _save_seen(urls)
    assert _load_seen() == urls


# ---------------------------------------------------------------------------
# save_paper
# ---------------------------------------------------------------------------

def test_save_paper_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.ingest.settings.papers_dir", tmp_path)
    paper = Paper(
        title="Test Paper",
        authors="Alice, Bob",
        date="2024-01-01",
        category="cs.AI",
        url="https://arxiv.org/abs/0000.00001",
        abstract="This is a test abstract.",
    )
    filepath = save_paper(paper, index=1)
    assert filepath.exists()
    content = filepath.read_text()
    assert "Test Paper" in content
    assert "Alice, Bob" in content
    assert "This is a test abstract." in content


def test_save_paper_safe_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("src.ingest.settings.papers_dir", tmp_path)
    paper = Paper(
        title="Paper: With / Special! Chars?",
        authors="N/A",
        date="2024-01-01",
        category="cs.LG",
        url="https://arxiv.org/abs/0000.00002",
        abstract="Abstract.",
    )
    filepath = save_paper(paper, index=2)
    assert "/" not in filepath.name
    assert "?" not in filepath.name


# ---------------------------------------------------------------------------
# fetch_papers
# ---------------------------------------------------------------------------

def _make_mock_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def test_fetch_papers_returns_papers(monkeypatch):
    entry = MagicMock()
    entry.title = "Transformer Paper"
    entry.summary = "<p>Abstract text here.</p>"
    entry.link = "https://arxiv.org/abs/1706.03762"
    entry.authors = [{"name": "Vaswani"}]
    entry.published = "2024-01-15T00:00:00Z"
    entry.get = lambda key, default=None: {
        "authors": [{"name": "Vaswani"}],
        "published": "2024-01-15T00:00:00Z",
    }.get(key, default)

    mock_feed = MagicMock()
    mock_feed.entries = [entry]

    monkeypatch.setattr("src.ingest.settings.max_papers_per_feed", 15)
    with patch("src.ingest.feedparser.parse", return_value=mock_feed):
        papers = fetch_papers("cs.AI", "https://arxiv.org/rss/cs.AI")

    assert len(papers) == 1
    assert papers[0].title == "Transformer Paper"
    assert papers[0].category == "cs.AI"
    assert papers[0].url == "https://arxiv.org/abs/1706.03762"


def test_fetch_papers_strips_html_from_abstract(monkeypatch):
    entry = MagicMock()
    entry.title = "Test"
    entry.summary = "<p>Clean <b>abstract</b> text.</p>"
    entry.link = "https://arxiv.org/abs/test"
    entry.authors = []
    entry.published = "2024-01-01"
    entry.get = lambda key, default=None: {"authors": [], "published": "2024-01-01"}.get(key, default)

    mock_feed = MagicMock()
    mock_feed.entries = [entry]

    monkeypatch.setattr("src.ingest.settings.max_papers_per_feed", 15)
    with patch("src.ingest.feedparser.parse", return_value=mock_feed):
        papers = fetch_papers("cs.AI", "https://arxiv.org/rss/cs.AI")

    assert "<p>" not in papers[0].abstract
    assert "<b>" not in papers[0].abstract


# ---------------------------------------------------------------------------
# run_ingest — incremental skip logic
# ---------------------------------------------------------------------------

def test_run_ingest_skips_seen_papers(tmp_path, monkeypatch):
    existing_url = "https://arxiv.org/abs/already-seen"
    manifest = tmp_path / "papers" / "seen.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps([existing_url]))

    monkeypatch.setattr("src.ingest.settings.papers_dir", tmp_path / "papers")
    monkeypatch.setattr("src.ingest.settings.seen_manifest", manifest)
    monkeypatch.setattr("src.ingest.settings.rss_categories", {"cs.AI": "https://arxiv.org/rss/cs.AI"})

    paper = Paper(
        title="Already Seen",
        authors="N/A",
        date="2024-01-01",
        category="cs.AI",
        url=existing_url,
        abstract="Old abstract.",
    )

    with patch("src.ingest.fetch_papers", return_value=[paper]):
        from src.ingest import run_ingest
        count = run_ingest()

    assert count == 0
