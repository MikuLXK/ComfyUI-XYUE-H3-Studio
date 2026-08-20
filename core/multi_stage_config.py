"""Parse and validate portable multi-stage cloud configuration text."""

from __future__ import annotations

import json
import re
from typing import Any

from .contracts import MAX_STAGES, MULTI_STAGE_CONFIG_SCHEMA


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    match = _JSON_BLOCK.search(text)
    if match:
        text = match.group(1).strip()
    if not text:
        return {}
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"多段配置不是有效 JSON：第 {exc.lineno} 行，第 {exc.colno} 列") from exc
    if not isinstance(decoded, dict):
        raise ValueError("多段配置顶层必须是 JSON 对象")
    return decoded


def _stage_index(value: Any, stage_count: int) -> int:
    index = int(value)
    if index < 1:
        raise ValueError("阶段编号必须从 1 开始")
    return index


def parse_multi_stage_config(value: Any) -> dict[str, Any]:
    data = _decode(value)
    if data.get("schema") != MULTI_STAGE_CONFIG_SCHEMA:
        raise ValueError(f"配置 schema 必须是 {MULTI_STAGE_CONFIG_SCHEMA}")

    forbidden = {"model", "models", "lora", "loras"}
    present = sorted(key for key in forbidden if key in data)
    acceleration = data.get("acceleration") or {}
    if isinstance(acceleration, dict):
        present.extend(sorted(key for key in ("model", "models", "lora", "loras", "stages") if key in acceleration))
    if present:
        raise ValueError("云端多段配置不得包含模型或 LoRA 字段：" + ", ".join(dict.fromkeys(present)))

    try:
        stage_count = int(data["stage_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"stage_count 必须是 1–{MAX_STAGES} 的整数") from exc
    if not 1 <= stage_count <= MAX_STAGES:
        raise ValueError(f"stage_count 必须在 1–{MAX_STAGES} 之间")

    prompts = data.get("prompts")
    if not isinstance(prompts, list) or len(prompts) != stage_count:
        raise ValueError("prompts 数量必须与 stage_count 相同")
    if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
        raise ValueError("每个阶段都必须提供非空提示词")

    generation = data.get("generation") or {}
    if not isinstance(generation, dict):
        raise ValueError("generation 必须是 JSON 对象")
    global_values = generation.get("global") or {}
    if not isinstance(global_values, dict):
        raise ValueError("generation.global 必须是 JSON 对象")
    stage_values = generation.get("stages")
    if stage_values is None:
        stage_values = [{} for _ in range(stage_count)]
    if not isinstance(stage_values, list) or len(stage_values) != stage_count:
        raise ValueError("generation.stages 数量必须与 stage_count 相同")

    stages: list[dict[str, Any]] = []
    for index, item in enumerate(stage_values, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 段 generation 配置必须是 JSON 对象")
        stage = dict(global_values)
        stage.update(item)
        if "duration" not in stage:
            raise ValueError(f"第 {index} 段缺少 duration")
        try:
            duration = int(stage["duration"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 段 duration 必须是整数") from exc
        if not 1 <= duration <= 15:
            raise ValueError(f"第 {index} 段 duration 必须在 1–15 秒之间")
        stage["duration"] = duration
        stages.append(stage)

    if not isinstance(acceleration, dict):
        raise ValueError("acceleration 必须是 JSON 对象")
    acceleration_enabled = bool(acceleration.get("enabled", False))

    return {
        "schema": MULTI_STAGE_CONFIG_SCHEMA,
        "workflow": str(data.get("workflow", "continuation")),
        "stage_count": stage_count,
        "prompts": list(prompts),
        "generation": {
            "global_enabled": bool(generation.get("global_enabled", False)),
            "global": dict(global_values),
            "stages": stages,
        },
        "acceleration": {"enabled": acceleration_enabled},
        "project_name": str(data.get("project_name", "")),
    }


def stage_values(config: dict[str, Any] | None, stage_index: int) -> tuple[str | None, dict[str, Any] | None]:
    if not config or config.get("schema") != MULTI_STAGE_CONFIG_SCHEMA:
        return None, None
    count = int(config.get("stage_count", 0))
    index = _stage_index(stage_index, count)
    if index > count:
        return None, None
    return str(config["prompts"][index - 1]), dict(config["generation"]["stages"][index - 1])
