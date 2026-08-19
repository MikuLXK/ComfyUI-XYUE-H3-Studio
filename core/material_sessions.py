"""In-memory material selections for embedded aggregate Studio instances."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any


_LOCK = Lock()
_SESSIONS: dict[str, list[dict[str, Any]]] = {}


def save_material_session(studio_id: str, overrides: list[dict[str, Any]]) -> None:
    key = str(studio_id or "").strip()
    if not key:
        raise ValueError("studio_id 不能为空")
    clean = [dict(item) for item in overrides if isinstance(item, dict)]
    with _LOCK:
        _SESSIONS[key] = deepcopy(clean)


def load_material_session(studio_id: str) -> list[dict[str, Any]]:
    key = str(studio_id or "").strip()
    if not key:
        return []
    with _LOCK:
        return deepcopy(_SESSIONS.get(key, []))
