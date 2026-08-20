"""Canonical Studio project-config constants and small normalization helpers."""

from __future__ import annotations

import json
from typing import Any


STUDIO_CONFIG_SCHEMA = "xyue-h3/studio-config-v3"


def decode_config(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        result = json.loads(str(value or ""))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Studio 配置不是有效 JSON：第 {exc.lineno} 行，第 {exc.colno} 列") from exc
    if not isinstance(result, dict):
        raise ValueError("Studio 配置顶层必须是 JSON 对象")
    return result
