"""Project-scoped output naming for Studio executions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import os

import folder_paths
from comfy_api.latest import Types

try:
    from ..services.video_checkpoints import SavedCheckpoint, save_stage_video
except ImportError:  # direct unit-test import
    from services.video_checkpoints import SavedCheckpoint, save_stage_video


_UNSAFE = re.compile(r"[^\w\u3400-\u9fff.()\- ]+", re.UNICODE)

COLLISION_MODES = {
    "increment": "increment",
    "overwrite": "overwrite",
    "block": "block",
    "自动递增": "increment",
    "覆盖": "overwrite",
    "阻止": "block",
}


def normalize_collision(value: Any) -> str:
    return COLLISION_MODES.get(str(value or "自动递增").strip(), "increment")


def safe_component(value: Any, fallback: str) -> str:
    text = _UNSAFE.sub("_", str(value or "")).strip(" ._")
    return text or fallback


def output_prefix(policy: dict[str, Any] | None, *, kind: str, index: int, stage: str, seed: int) -> str:
    settings = dict(policy or {})
    name = safe_component(settings.get("project_name") or settings.get("name"), "当前项目")
    folder = safe_component(settings.get("project_folder"), name)
    if "/" in str(settings.get("project_folder") or ""):
        parts = [part for part in str(settings["project_folder"]).replace("\\", "/").split("/") if part]
        if parts and parts[0].lower() == "xyue_h3":
            parts = parts[1:]
        folder = "/".join(safe_component(part, "项目") for part in parts) or name
    now = datetime.now()
    variables = {
        "name": name,
        "index": int(index),
        "stage": safe_component(stage, f"镜头{index:02d}"),
        "seed": int(seed),
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
    }
    default_pattern = "{name}_{index:02d}" if kind == "stage" else "{name}_最终"
    pattern = str(settings.get("stage_pattern" if kind == "stage" else "final_pattern") or default_pattern)
    try:
        filename = pattern.format(**variables)
    except (KeyError, ValueError):
        filename = default_pattern.format(**variables)
    return f"xyue_h3/{folder}/{safe_component(filename, name)}"


def save_video_with_policy(video: Any, prefix: str, *, container: str = "mp4", codec: str = "h264", collision: str = "increment") -> SavedCheckpoint:
    collision = normalize_collision(collision)
    if collision == "increment":
        return save_stage_video(video, prefix, container, codec)
    extension = Types.VideoContainer.get_extension(container)
    root = os.path.abspath(folder_paths.get_output_directory())
    relative = f"{prefix}.{extension}".replace("\\", "/").lstrip("/")
    target = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath((root, target)) != root:
        raise ValueError("保存路径必须位于 ComfyUI/output 内")
    if os.path.exists(target) and collision == "block":
        raise FileExistsError(f"输出文件已存在：{target}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    video.save_to(target, format=Types.VideoContainer(container), codec=Types.VideoCodec(codec))
    return SavedCheckpoint(
        file=os.path.basename(target),
        subfolder=os.path.relpath(os.path.dirname(target), root).replace("\\", "/"),
        full_path=target,
    )
