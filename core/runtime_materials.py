"""Load Studio material overrides without requiring material graph nodes."""

from __future__ import annotations

from typing import Any

from ..nodes.assets import (
    XYUEH3AudioAsset,
    XYUEH3AudioManager,
    XYUEH3ImageAsset,
    XYUEH3ImageManager,
    XYUEH3MaterialManager,
    XYUEH3VideoAsset,
    XYUEH3VideoManager,
)


def load_material_pack(overrides: list[dict[str, Any]] | None) -> dict[str, Any]:
    grouped = {"image": [], "video": [], "audio": []}
    for item in overrides or []:
        if not isinstance(item, dict) or not item.get("enabled") or not item.get("file"):
            continue
        kind = str(item.get("kind") or "")
        if kind in grouped:
            grouped[kind].append(dict(item))

    images = []
    for item in grouped["image"][:9]:
        images.append(XYUEH3ImageAsset.execute(
            str(item["file"]), True, str(item.get("alias_mode") or "@图片N"), str(item.get("role") or "未指定"), str(item.get("fit_mode") or "保持原图")
        )[0])
    videos = []
    for item in grouped["video"][:3]:
        videos.append(XYUEH3VideoAsset.execute(
            str(item["file"]), True, str(item.get("alias_mode") or "@视频N"), str(item.get("role") or "动作节奏样片"), float(item.get("start_seconds", 0)), float(item.get("duration_seconds", 0)), bool(item.get("include_audio", False))
        )[0])
    audios = []
    for item in grouped["audio"][:3]:
        audios.append(XYUEH3AudioAsset.execute(
            str(item["file"]), True, str(item.get("alias_mode") or "@音频N"), str(item.get("role") or "角色声纹锚点"), str(item.get("voice_anchor") or "声音"), float(item.get("start_seconds", 0)), float(item.get("duration_seconds", 0)), float(item.get("gain_db", 0)), bool(item.get("normalize_peak", False))
        )[0])

    image_pack = XYUEH3ImageManager.execute(**{f"image_{index}": item for index, item in enumerate(images, 1)})[0]
    video_pack = XYUEH3VideoManager.execute(**{f"video_{index}": item for index, item in enumerate(videos, 1)})[0]
    audio_pack = XYUEH3AudioManager.execute(**{f"audio_{index}": item for index, item in enumerate(audios, 1)})[0]
    return XYUEH3MaterialManager.execute(image_pack, video_pack, audio_pack)[0]
