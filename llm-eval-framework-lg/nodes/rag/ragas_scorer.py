"""RAG sub-graph node: score all enriched samples with RAGAS and emit EvalSubResult.

This is an LLM node — RAGAS calls an LLM internally to compute the four
semantic metrics. See README "Where LLMs Are Used" section for rationale.

Runs once after all parallel rag_question_node calls have completed and the
enriched reducer list is fully populated.

Also writes eval_results so the result propagates back to the top-level
EvalState via key-name matching between sub-graph and parent state.
"""

from __future__ import annotations

import logging

from config import settings
from eval_models.schemas import EnrichedRagSample, EvalSubResult, RagQuestionScore
from state.rag_state import RagEvalState

logger = logging.getLogger(__name__)

METRIC_KEYS = ["faithfulness", "answer_relevance", "context_recall", "context_precision"]


def ragas_scorer_node(state: RagEvalState) -> dict:
    """Run ragas.evaluate() over all enriched samples; return scores + EvalSubResult."""
    cfg = state["config"]
    enriched: list[EnrichedRagSample] = state["enriched"]

    logger.info("Scoring %d samples with RAGAS", len(enriched))
    scores = _score_with_ragas(enriched, cfg)

    aggregates = {}
    for key in METRIC_KEYS:
        values = [getattr(s, key) for s in scores]
        aggregates[key] = round(sum(values) / len(values), 4) if values else 0.0

    tokens_used = sum(s.tokens_used for s in enriched)
    sub_result = EvalSubResult(target="rag", aggregates=aggregates, tokens_used=tokens_used)

    logger.info("RAG aggregates: %s", aggregates)
    return {
        "scores": scores,
        "aggregates": aggregates,
        "eval_results": [sub_result],
    }


def _score_with_ragas(enriched: list[EnrichedRagSample], cfg) -> list[RagQuestionScore]:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_recall,
        context_precision,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    data = {
        "user_input":         [s.question for s in enriched],
        "response":           [s.answer for s in enriched],
        "retrieved_contexts": [s.contexts for s in enriched],
        "reference":          [s.ground_truth for s in enriched],
    }
    dataset = Dataset.from_dict(data)

    llm = LangchainLLMWrapper(ChatOpenAI(
        model=cfg.model, temperature=cfg.temperature, api_key=settings.openai_api_key
    ))
    emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(api_key=settings.openai_api_key))

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_recall, context_precision],
        llm=llm,
        embeddings=emb,
    )

    df = result.to_pandas()
    scores = []
    for _, row in df.iterrows():
        scores.append(RagQuestionScore(
            question=str(row.get("user_input", "")),
            faithfulness=float(row.get("faithfulness", 0.0) or 0.0),
            answer_relevance=float(row.get("answer_relevancy", 0.0) or 0.0),
            context_recall=float(row.get("context_recall", 0.0) or 0.0),
            context_precision=float(row.get("context_precision", 0.0) or 0.0),
        ))
    return scores
