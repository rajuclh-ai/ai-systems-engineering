"""RAG sub-graph state.

enriched uses Annotated[list, add] so each parallel rag_question_node
invocation can append its EnrichedRagSample independently.
ragas_scorer_node reads the full enriched list once all questions complete.

eval_results mirrors the parent EvalState key — the sub-graph's final node
writes here, and LangGraph propagates it back to the parent via key-name matching.
"""

from __future__ import annotations

from operator import add
from typing import Annotated

from typing_extensions import TypedDict

from eval_models.schemas import EnrichedRagSample, EvalSubResult, RagQuestionScore, RagSample


class RagEvalState(TypedDict):
    config: object                                            # EvalConfig
    samples: list[RagSample]
    enriched: Annotated[list[EnrichedRagSample], add]        # reducer — one per question
    scores: list[RagQuestionScore]
    aggregates: dict[str, float]
    eval_results: Annotated[list[EvalSubResult], add]        # written at end → propagates to parent
