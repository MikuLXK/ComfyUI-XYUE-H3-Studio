"""Exact MiniMax H3 video-latent scale adapter used between two sigma passes."""

from __future__ import annotations

import importlib
from typing import Any

from comfy_extras.nodes_lt import LTXVConcatAVLatent, LTXVSeparateAVLatent


def _scale_node():
    try:
        module = importlib.import_module(
            "Comfyui_Minimax_h3_latent_Upscaler.nodes.minimax_h3_latent_upscaler_3d"
        )
    except Exception as exc:
        raise RuntimeError(
            "已启用 H3 潜空间放大，但未加载 Comfyui_Minimax_h3_latent_Upscaler 插件"
        ) from exc
    return module.MinimaxH3LatentUpscalerNode3D


def _sync_node():
    try:
        module = importlib.import_module(
            "Comfyui_Minimax_h3_latent_Upscaler.nodes.H3_latent_upscaler_3d_v3"
        )
    except Exception as exc:
        raise RuntimeError(
            "H3 二次采样条件同步节点未加载，请更新 Comfyui_Minimax_h3_latent_Upscaler"
        ) from exc
    return module.H3LatentUpscalerNode3DV3


def upscale_video_latent(
    latent: dict[str, Any],
    *,
    model_name: str,
    scale: float,
    device: str = "cuda",
    precision: str = "fp16",
) -> dict[str, Any]:
    """Separate AV, scale only the video latent, then attach untouched audio."""

    if not model_name or model_name.startswith("("):
        raise ValueError("H3 潜空间放大需要选择 latent_upscale_models 中的模型")
    video_latent, audio_latent = LTXVSeparateAVLatent.execute(latent)
    upscaled_video = _scale_node()().run(
        video_latent,
        str(model_name),
        max(1.0, float(scale)),
        str(device),
        str(precision),
    )[0]
    return LTXVConcatAVLatent.execute(upscaled_video, audio_latent)[0]


def refine_av_latent(
    latent: dict[str, Any],
    positive: Any,
    negative: Any,
    *,
    model_name: str,
    scale: float,
    device: str = "cuda",
    precision: str = "fp16",
) -> tuple[dict[str, Any], Any, Any]:
    """Upscale video latent, preserve audio, then align image conditions."""

    upscaled = upscale_video_latent(
        latent,
        model_name=model_name,
        scale=scale,
        device=device,
        precision=precision,
    )
    synced_latent, synced_positive, synced_negative = _sync_node()().run(
        upscaled,
        positive,
        negative,
    )
    return synced_latent, synced_positive, synced_negative
