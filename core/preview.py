"""Optional live-preview model wrapper used by the local H3 generator."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any


def attach_preview(
    model: Any,
    *,
    tiny_vae: str = "none",
    unique_id: str | None = None,
    preview_frames: int = 12,
    preview_fps: int = 12,
) -> Any:
    """Attach the KJ preview wrapper without changing the generation model weights."""

    module = next(
        (value for name, value in sys.modules.items() if name.endswith(".preview_override_node")),
        None,
    )
    try:
        if module is None:
            module = importlib.import_module("nodes.preview_override_node")
    except Exception:
        module = None
    if module is None:
        module_path = Path(__file__).resolve().parents[1].parent / "ComfyUI-KJNodes" / "nodes" / "preview_override_node.py"
        spec = importlib.util.spec_from_file_location("xyue_kj_preview_override", module_path)
        module = importlib.util.module_from_spec(spec) if spec and spec.loader else None
        if module is not None:
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
    if module is None and tiny_vae not in {"", "none"}:
        raise RuntimeError("已选择 tiny_vae，但 ComfyUI-KJNodes 未加载")
    if module is None:
        return model

    import comfy.patcher_extension

    wrapped = model.clone()
    wrapper = module._PreviewOverrideWrapper(
        1024,
        unique_id,
        80,
        True,
        max(1, int(preview_frames)),
        max(1, int(preview_fps)),
        None,
        str(tiny_vae),
    )
    wrapped.add_wrapper_with_key(
        comfy.patcher_extension.WrappersMP.OUTER_SAMPLE,
        "xyue_tiny_vae_preview",
        wrapper,
    )
    return wrapped
