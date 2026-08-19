"""Optional live-preview model wrapper used by the local H3 generator."""

from __future__ import annotations

import importlib
from typing import Any


def attach_preview(model: Any, *, tiny_vae: str = "none", unique_id: str | None = None) -> Any:
    """Attach the KJ preview wrapper without changing the generation model weights."""

    if not tiny_vae or tiny_vae == "none":
        return model
    try:
        module = importlib.import_module("ComfyUI-KJNodes.nodes.preview_override_node")
    except Exception as exc:
        raise RuntimeError("已选择 tiny_vae，但 ComfyUI-KJNodes 未加载") from exc

    import comfy.patcher_extension

    wrapped = model.clone()
    wrapper = module._PreviewOverrideWrapper(
        1024,
        unique_id,
        80,
        True,
        1,
        12,
        None,
        str(tiny_vae),
    )
    wrapped.add_wrapper_with_key(
        comfy.patcher_extension.WrappersMP.OUTER_SAMPLE,
        "xyue_tiny_vae_preview",
        wrapper,
    )
    return wrapped
