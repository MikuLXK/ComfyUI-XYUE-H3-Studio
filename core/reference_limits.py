"""MiniMax H3 Ref2VA reference-count limits."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import MAX_AUDIOS, MAX_PICTURES, MAX_REFERENCE_FILES, MAX_VIDEOS


def _pack_count(pack: Mapping[str, Any] | None) -> int:
    if not pack:
        return 0
    entries = pack.get("entries")
    if isinstance(entries, list):
        return len(entries)
    return int(pack.get("count", 0))


def reference_counts(
    image_pack: Mapping[str, Any] | None,
    video_pack: Mapping[str, Any] | None,
    audio_pack: Mapping[str, Any] | None,
) -> dict[str, int]:
    """Count input files; a video's embedded soundtrack is not another file."""

    pictures = _pack_count(image_pack)
    videos = _pack_count(video_pack)
    audios = _pack_count(audio_pack)
    return {
        "pictures": pictures,
        "videos": videos,
        "audios": audios,
        "mixed": pictures + videos + audios,
    }


def validate_reference_limits(
    image_pack: Mapping[str, Any] | None,
    video_pack: Mapping[str, Any] | None,
    audio_pack: Mapping[str, Any] | None,
    *,
    reserve: int = 0,
) -> dict[str, int]:
    counts = reference_counts(image_pack, video_pack, audio_pack)
    violations = []
    if counts["pictures"] > MAX_PICTURES:
        violations.append(f"图片 {counts['pictures']}/{MAX_PICTURES}")
    if counts["videos"] > MAX_VIDEOS:
        violations.append(f"视频 {counts['videos']}/{MAX_VIDEOS}")
    if counts["audios"] > MAX_AUDIOS:
        violations.append(f"音频 {counts['audios']}/{MAX_AUDIOS}")
    if counts["mixed"] + int(reserve) > MAX_REFERENCE_FILES:
        suffix = f"（另需预留 {reserve} 项）" if reserve else ""
        violations.append(f"混合素材 {counts['mixed']}/{MAX_REFERENCE_FILES}{suffix}")
    if violations:
        raise ValueError("Ref2VA 素材数量超限：" + "；".join(violations))
    return counts


def continuation_image_action(
    image_pack: Mapping[str, Any] | None,
    video_pack: Mapping[str, Any] | None,
    audio_pack: Mapping[str, Any] | None,
) -> str:
    """Append until Picture 9; only a full image pack reuses its final slot."""

    counts = validate_reference_limits(image_pack, video_pack, audio_pack)
    if counts["pictures"] >= MAX_PICTURES:
        return "replace_last_picture"
    validate_reference_limits(image_pack, video_pack, audio_pack, reserve=1)
    return "append_picture"
