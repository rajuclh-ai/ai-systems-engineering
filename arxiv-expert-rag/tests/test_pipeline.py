"""End-to-end pipeline tests — all external calls mocked."""

from unittest.mock import MagicMock, patch

import pytest

from src.generator import Answer, Source
from src.retriever import Chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_chunks():
    return [
        Chunk(
            text="The Transformer uses self-attention.",
            title="Attention Is All You Need",
            authors="Vaswani et al.",
            date="2017-06-12",
            category="cs.AI",
            url="https://arxiv.org/abs/1706.03762",
            chunk_index=0,
        )
    ]


# ---------------------------------------------------------------------------
# run_query_pipeline
# ---------------------------------------------------------------------------

def test_run_query_pipeline_returns_answer():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = _sample_chunks()

    mock_answer = Answer(
        question="What is a Transformer?",
        text="The Transformer uses self-attention mechanisms.",
        sources=[Source(title="Attention Is All You Need",
                        url="https://arxiv.org/abs/1706.03762",
                        category="cs.AI")],
        tokens_used=80,
    )

    with patch("src.pipeline._get_retriever", return_value=mock_retriever), \
         patch("src.pipeline.generate_answer", return_value=mock_answer):
        from src.pipeline import run_query_pipeline
        answer = run_query_pipeline("What is a Transformer?")

    assert isinstance(answer, Answer)
    assert answer.tokens_used == 80
    assert len(answer.sources) == 1


def test_run_query_pipeline_passes_top_k():
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = _sample_chunks()
    mock_answer = Answer(question="Q", text="A", sources=[], tokens_used=10)

    with patch("src.pipeline._get_retriever", return_value=mock_retriever), \
         patch("src.pipeline.generate_answer", return_value=mock_answer):
        from src.pipeline import run_query_pipeline
        run_query_pipeline("Some question", top_k=3)

    mock_retriever.search.assert_called_once_with("Some question", top_k=3)


# ---------------------------------------------------------------------------
# run_ingest_pipeline
# ---------------------------------------------------------------------------

def test_run_ingest_pipeline_skips_embed_when_no_new_papers():
    with patch("src.pipeline.run_ingest", return_value=0) as mock_ingest, \
         patch("src.pipeline.embed_papers") as mock_embed:
        from src.pipeline import run_ingest_pipeline
        result = run_ingest_pipeline()

    assert result["new_papers"] == 0
    assert result["chunks_added"] == 0
    mock_embed.assert_not_called()


def test_run_ingest_pipeline_embeds_when_new_papers():
    with patch("src.pipeline.run_ingest", return_value=5), \
         patch("src.pipeline.embed_papers", return_value=40) as mock_embed:
        from src.pipeline import run_ingest_pipeline
        result = run_ingest_pipeline()

    assert result["new_papers"] == 5
    assert result["chunks_added"] == 40
    mock_embed.assert_called_once()


# ---------------------------------------------------------------------------
# generate_answer — prompt and response shape
# ---------------------------------------------------------------------------

def test_generate_answer_returns_answer_with_sources(mock_openai_response):
    chunks = _sample_chunks()

    with patch("src.generator.openai.OpenAI") as mock_openai_cls, \
         patch("src.generator.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_max_tokens = 600

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_openai_cls.return_value = mock_client

        from src.generator import generate_answer
        answer = generate_answer("What is attention?", chunks)

    assert isinstance(answer, Answer)
    assert answer.text == "The Transformer uses self-attention mechanisms."
    assert answer.tokens_used == 120
    assert len(answer.sources) == 1
    assert answer.sources[0].title == "Attention Is All You Need"


def test_generate_answer_deduplicates_sources(mock_openai_response):
    chunks = _sample_chunks() + _sample_chunks()  # same paper twice

    with patch("src.generator.openai.OpenAI") as mock_openai_cls, \
         patch("src.generator.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_max_tokens = 600

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_openai_cls.return_value = mock_client

        from src.generator import generate_answer
        answer = generate_answer("What is attention?", chunks)

    assert len(answer.sources) == 1
