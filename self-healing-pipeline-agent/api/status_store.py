"""
In-memory incident status store.
Keyed by thread_id — written by background tasks, read by GET /incidents/{thread_id}/status.
"""
from typing import Any

_store: dict[str, dict[str, Any]] = {}


def set_status(thread_id: str, data: dict[str, Any]) -> None:
    _store[thread_id] = data


def get_status(thread_id: str) -> dict[str, Any] | None:
    return _store.get(thread_id)
