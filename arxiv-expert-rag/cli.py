"""CLI entry point for the ArXiv Expert RAG system.

Usage:
    python cli.py ingest            # fetch new papers + embed them
    python cli.py query "..."       # ask a research question
    python cli.py stats             # show DB stats
"""

import logging
import os
import sys

import click

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
def cli() -> None:
    """ArXiv Expert RAG — query the latest AI/ML research papers."""


@cli.command()
def ingest() -> None:
    """Fetch new ArXiv papers and embed them into ChromaDB."""
    from src.pipeline import run_ingest_pipeline

    click.echo("Starting ingestion pipeline...")
    result = run_ingest_pipeline()

    if result["new_papers"] == 0:
        click.echo("No new papers found — database is up to date.")
    else:
        click.echo(f"Done. {result['new_papers']} new papers saved, "
                   f"{result['chunks_added']} chunks added to ChromaDB.")


@cli.command()
@click.argument("question")
@click.option("--top-k", default=None, type=int, help="Number of chunks to retrieve (default: 5)")
def query(question: str, top_k: int | None) -> None:
    """Ask a research question about recent AI/ML papers."""
    from src.pipeline import run_query_pipeline

    click.echo(f"\nQuestion: {question}\n{'=' * 60}")
    answer = run_query_pipeline(question, top_k=top_k)

    click.echo(f"\nAnswer:\n{answer.text}")
    click.echo(f"\nSources ({len(answer.sources)}):")
    for source in answer.sources:
        click.echo(f"  [{source.category}] {source.title}")
        click.echo(f"           {source.url}")
    click.echo(f"\nTokens used: {answer.tokens_used}")


@cli.command()
def stats() -> None:
    """Show database statistics: paper count, chunk count, categories."""
    from src.pipeline import get_stats

    data = get_stats()
    click.echo(f"\nArXiv Expert RAG — Database Stats")
    click.echo(f"{'=' * 35}")
    click.echo(f"  Papers on disk : {data['papers']}")
    click.echo(f"  Chunks in DB   : {data['chunks']}")
    click.echo(f"\n  By category:")
    for cat, count in sorted(data["categories"].items()):
        click.echo(f"    {cat:<12} {count} papers")


if __name__ == "__main__":
    cli()
