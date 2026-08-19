"""Adapter for the optional MiniMax H3 learned latent upscaler."""

from __future__ import annotations

import importlib
from typing import Any


def _upscaler_components():
    try:
        resolution_module = importlib.import_module(
            "Comfyui_Minimax_h3_latent_Upscaler.nodes.H3_latent_upscaler_resolution"
        )
        sync_module = importlib.import_module(
            "Comfyui_Minimax_h3_latent_Upscaler.nodes.H3_latent_upscaler_3d_v3"
        )
    except Exception as exc:
        raise RuntimeError(
            "已启用 H3 latent 精修，但未加载 Comfyui_Minimax_h3_latent_Upscaler 插件"
        ) from exc
    return resolution_module.H3LatentUpscalerNodeResolution, sync_module.H3LatentUpscalerNode3DV3


def _model_precision(model_name: str) -> str:
    name = str(model_name).lower()
    if "bf16" in name:
        return "bf16"
    if "fp32" in name or name.endswith(".pth"):
        return "fp32"
    return "fp16"


def refine_av_latent(
    latent: dict[str, Any],
    positive: Any,
    negative: Any,
    *,
    model_name: str,
    target_width: int,
    target_height: int,
    device: str = "cuda",
    precision: str = "auto",
    align: int = 2,
) -> tuple[dict[str, Any], Any, Any]:
    """Upscale the video stream, preserve audio, and resize H3 conditions."""

    resolution_node, sync_node = _upscaler_components()
    if not model_name or model_name.startswith("("):
        raise ValueError("H3 latent 精修需要选择 latent_upscale_models 中的模型")

    selected_precision = _model_precision(model_name) if precision == "auto" else str(precision)
    upscaled = resolution_node().run(
        latent,
        model_name,
        int(target_width),
        int(target_height),
        int(align),
        str(device),
        selected_precision,
    )[0]
    synced_latent, synced_positive, synced_negative = sync_node().run(
        upscaled,
        positive,
        negative,
    )
    return synced_latent, synced_positive, synced_negative
