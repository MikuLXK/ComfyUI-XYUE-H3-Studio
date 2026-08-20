"""Apply the selected LoRA and attention backend to an H3 model."""

from __future__ import annotations

from typing import Any

import comfy.ldm.modules.attention
import nodes as comfy_nodes
from comfy_extras.nodes_model_advanced import ModelAttentionBackend


NO_LORA = "不使用 LoRA"
ATTENTION_OPTIONS = ("MiniMax H3 Kitchen Attention", "Patch Sol-Attn")


def apply_lora(model: Any, *, enabled: bool, name: str, strength: float) -> Any:
    if not enabled:
        return model
    selected = str(name or NO_LORA)
    if selected == NO_LORA:
        raise ValueError("已启用 LoRA，但没有选择 LoRA 模型")
    return comfy_nodes.LoraLoaderModelOnly().load_lora_model_only(
        model,
        selected,
        float(strength),
    )[0]


def apply_attention(model: Any, mode: str) -> Any:
    selected = str(mode)
    if selected == ATTENTION_OPTIONS[0]:
        if not comfy.ldm.modules.attention.COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE:
            raise RuntimeError("MiniMax H3 Kitchen Attention 在当前 ComfyUI 环境中不可用")
        return ModelAttentionBackend().patch(model, "comfy kitchen attention")[0]
    if selected == ATTENTION_OPTIONS[1]:
        node_class = (getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", {}) or {}).get("SolAttnPatch")
        if node_class is None:
            raise RuntimeError("已选择 Patch Sol-Attn，但未安装 ComfyUI-SolAttn_triton")
        return node_class.execute(
            model=model,
            tau=1.3,
            start_percent=0.2,
            end_percent=0.9,
            min_tokens=4096,
            int8_qk=True,
            sink_conditioning="exact_kv_and_rows",
            morton=False,
            morton_curve="2d_frame",
            int8_pv=True,
            verbose=False,
            use_tma=False,
            dense_blocks="0-5",
        )[0]
    raise ValueError(f"不支持的注意力模式：{selected}")
