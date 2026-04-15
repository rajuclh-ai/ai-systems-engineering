"""Answer generation — build a prompt from retrieved chunks and call GPT-4o-mini."""

import logging
from dataclasses import dataclass, field

import openai

from .config import settings
from .retriever import Chunk

logger = logging.getLogger(__name__)


@dataclass
class Source:
    title: str
    url: str
    category: str


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Source] = field(default_factory=list)
    tokens_used: int = 0


def _build_context(chunks: list[Chunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(
            f"[Paper {i + 1}: {chunk.title}]\n"
            f"Authors: {chunk.authors}\n"
            f"Date: {chunk.date} | Category: {chunk.category}\n\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


def _dedupe_sources(chunks: list[Chunk]) -> list[Source]:
    seen: set[str] = set()
    sources = []
    for chunk in chunks:
        if chunk.title not in seen:
            sources.append(Source(title=chunk.title, url=chunk.url, category=chunk.category))
            seen.add(chunk.title)
    return sources


def generate_answer(question: str, chunks: list[Chunk]) -> Answer:
    """
    Generate a grounded answer from retrieved paper chunks.

    Args:
        question: The user's research question.
        chunks:   Retrieved paper chunks from the Retriever.

    Returns:
        Answer dataclass with text, sources, and token count.
    """
    client = openai.OpenAI(api_key=settings.openai_api_key)
    context = _build_context(chunks)

    prompt = f"""You are an expert AI research assistant with deep knowledge of machine learning and artificial intelligence.

Your job is to answer questions about recent ArXiv research papers using ONLY the provided paper excerpts below.

Rules:
- Answer based strictly on the provided excerpts
- Cite the paper title when referencing specific findings
- If the answer is not in the excerpts, say "This topic wasn't covered in the retrieved papers."
- Be concise and technical — the audience is engineers and researchers

PAPER EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""

    logger.info(f"Calling {settings.openai_model} for: {question[:60]}")
    response = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    answer_text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    logger.info(f"Generated answer — {tokens} tokens used")

    return Answer(
        question=question,
        text=answer_text,
        sources=_dedupe_sources(chunks),
        tokens_used=tokens,
    )
