"""In-memory status store — keyed by thread_id."""
from typing import Any

_store: dict[str, dict[str, Any]] = {}


def set_status(thread_id: str, data: dict[str, Any]) -> None:
    _store[thread_id] = data


def get_status(thread_id: str) -> dict[str, Any] | None:
    return _store.get(thread_id)
