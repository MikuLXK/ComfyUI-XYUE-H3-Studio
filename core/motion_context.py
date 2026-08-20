"""Optional adapter for H3 motion-and-audio continuation between stages."""

from __future__ import annotations

from typing import Any

import nodes as comfy_nodes


MOTION_NODE = "MiniMaxH3MotionContext"
TRIM_NODE = "MiniMaxH3MotionContextTrim"


def _node(node_name: str):
    node_class = (getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", {}) or {}).get(node_name)
    if node_class is None:
        raise RuntimeError(
            "已选择动作音频续接，但未安装 ComfyUI-H3-Motion-Context"
        )
    return node_class()


def apply_motion_context(
    conditioning: Any,
    video_vae: Any,
    audio_vae: Any,
    latent: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    context_length: int = 22,
    audio_context_length: int = 24,
) -> tuple[Any, int]:
    """Carry the previous delivered motion and audio into the current clip."""

    context = dict(previous or {})
    context_latent = context.get("final_latent")
    context_frames = context.get("frames")
    context_audio = context.get("audio")
    current_width = int(latent["samples"].shape[-1]) * 16
    current_height = int(latent["samples"].shape[-2]) * 16
    same_latent_canvas = (
        context_latent is not None
        and int(context.get("width") or 0) == current_width
        and int(context.get("height") or 0) == current_height
    )

    kwargs = {"audio_context_length": int(audio_context_length)}
    if same_latent_canvas:
        kwargs["context_latent"] = context_latent
    else:
        if context_frames is None:
            raise ValueError("动作音频续接缺少上一镜画面")
        kwargs["context_frames"] = context_frames
        if context_audio is not None:
            kwargs["audio_vae"] = audio_vae
            kwargs["context_audio"] = context_audio

    return _node(MOTION_NODE).apply(
        conditioning,
        video_vae,
        latent,
        str(int(context_length)),
        **kwargs,
    )


def trim_motion_context(images: Any, audio: Any, trim_frames: int) -> tuple[Any, Any]:
    """Remove the duplicated pinned head while keeping audio sample-aligned."""

    if int(trim_frames) <= 0:
        return images, audio
    return _node(TRIM_NODE).trim(
        images,
        int(trim_frames),
        audio=audio,
        fps=24.0,
        match_tail=True,
    )
