"""Top-level EvalGraph state.

eval_results uses Annotated[list, add] so both sub-graphs can write their
EvalSubResult independently — LangGraph merges via the add reducer as each
parallel branch completes. No explicit synchronisation needed.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Optional

from typing_extensions import TypedDict

from eval_models.schemas import EvalSubResult


class EvalState(TypedDict):
    config: object                                      # EvalConfig (avoid circular import)
    target: str                                         # "all" | "rag" | "agent"
    run_id: str
    eval_results: Annotated[list[EvalSubResult], add]  # reducer — one entry per sub-graph
    overall: Optional[str]                              # "PASS" | "FAIL"
    total_tokens: int
    cost_usd: float
