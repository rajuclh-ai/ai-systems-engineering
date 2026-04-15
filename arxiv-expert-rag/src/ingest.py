"""ArXiv paper ingestion — fetch from RSS, save to disk, track seen papers."""

import json
import logging
import re
import ssl
import time
from dataclasses import dataclass
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup

from .config import settings

logger = logging.getLogger(__name__)

# Monkey-patch SSL for environments with certificate issues (same as notebook)
ssl._create_default_https_context = ssl._create_unverified_context


@dataclass
class Paper:
    title: str
    authors: str
    date: str
    category: str
    url: str
    abstract: str


def _load_seen() -> set[str]:
    """Load the set of already-fetched paper URLs from the manifest."""
    if settings.seen_manifest.exists():
        return set(json.loads(settings.seen_manifest.read_text()))
    return set()


def _save_seen(seen: set[str]) -> None:
    settings.seen_manifest.parent.mkdir(parents=True, exist_ok=True)
    settings.seen_manifest.write_text(json.dumps(sorted(seen), indent=2))


def fetch_papers(category: str, rss_url: str) -> list[Paper]:
    """Fetch papers from an ArXiv RSS feed."""
    logger.info(f"Fetching {category} from {rss_url}")
    feed = feedparser.parse(rss_url)
    papers = []

    for entry in feed.entries[: settings.max_papers_per_feed]:
        title = entry.title.replace("\n", " ").strip()
        abstract = BeautifulSoup(entry.summary, "html.parser").get_text().replace("\n", " ").strip()
        url = entry.link
        authors = ", ".join(a.get("name", "") for a in entry.get("authors", []))
        date = entry.get("published", "")[:10]

        papers.append(Paper(
            title=title,
            authors=authors or "N/A",
            date=date,
            category=category,
            url=url,
            abstract=abstract,
        ))

    logger.info(f"Fetched {len(papers)} papers from {category}")
    return papers


def save_paper(paper: Paper, index: int) -> Path:
    """Write a paper to disk as a structured .txt file."""
    settings.papers_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", paper.title)[:60]
    filename = f"{paper.category}_{index:03d}_{safe_title}.txt"
    filepath = settings.papers_dir / filename

    filepath.write_text(
        f"Title: {paper.title}\n"
        f"Authors: {paper.authors}\n"
        f"Date: {paper.date}\n"
        f"Category: {paper.category}\n"
        f"URL: {paper.url}\n"
        f"{'=' * 60}\n\n"
        f"ABSTRACT:\n{paper.abstract}\n",
        encoding="utf-8",
    )
    return filepath


def run_ingest() -> int:
    """
    Fetch new papers from all configured RSS feeds and save them to disk.

    Returns:
        Number of new papers saved.
    """
    seen = _load_seen()
    new_count = 0

    for category, rss_url in settings.rss_categories.items():
        papers = fetch_papers(category, rss_url)
        for i, paper in enumerate(papers):
            if paper.url in seen:
                logger.debug(f"Skipping already-seen paper: {paper.url}")
                continue
            save_paper(paper, i + 1)
            seen.add(paper.url)
            new_count += 1
            time.sleep(0.1)

    _save_seen(seen)
    logger.info(f"Ingestion complete — {new_count} new papers saved")
    return new_count
