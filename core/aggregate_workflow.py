"""Dynamic Studio execution graph and project-config validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import MAX_STAGES
from .studio_config import STUDIO_CONFIG_SCHEMA, decode_config


PLUGIN_ROOT = Path(__file__).parents[1]
AGGREGATE_CONFIG_SCHEMA = STUDIO_CONFIG_SCHEMA


EXTERNAL_NODE_PACKAGES = {
    "SolAttnPatch": "ComfyUI-SolAttn_triton",
    "MinimaxH3LatentUpscalerNode3D": "Comfyui_Minimax_h3_latent_Upscaler",
    "MiniMaxH3MotionContext": "ComfyUI-H3-Motion-Context",
}
EXTERNAL_NODE_DIRECTORIES = {
    "ComfyUI-SolAttn_triton": "ComfyUI-SolAttn_triton",
    "Comfyui_Minimax_h3_latent_Upscaler": "Comfyui_Minimax_h3_latent_Upscaler",
    "ComfyUI-H3-Motion-Context": "ComfyUI-H3-Motion-Context",
}


def dependency_report(workflow: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    node_types = sorted({str(node.get("type")) for node in workflow.get("nodes", []) if node.get("type")})
    required = [
        {"node": node_type, "package": EXTERNAL_NODE_PACKAGES[node_type]}
        for node_type in node_types
        if node_type in EXTERNAL_NODE_PACKAGES
    ]
    # These are selected dynamically inside the executor rather than visible
    # graph nodes, so report them explicitly for the Studio dependency panel.
    plan = dict(plan or {})
    attention_modes = [str(item.get("attention_mode")) for item in plan.get("models", []) if isinstance(item, dict)]
    transitions = [str(value) for value in plan.get("transitions", [])]
    selected_nodes = {"MinimaxH3LatentUpscalerNode3D"}
    if "Patch Sol-Attn" in attention_modes:
        selected_nodes.add("SolAttnPatch")
    if "motion" in transitions:
        selected_nodes.add("MiniMaxH3MotionContext")
    for node_type, package in EXTERNAL_NODE_PACKAGES.items():
        if node_type not in selected_nodes:
            continue
        if node_type not in {item["node"] for item in required}:
            required.append({"node": node_type, "package": package})
    try:
        import nodes as comfy_nodes

        mappings = getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", {}) or {}
    except Exception:
        mappings = {}
    custom_nodes_root = PLUGIN_ROOT.parent
    for item in required:
        directory = EXTERNAL_NODE_DIRECTORIES.get(item["package"])
        item["installed"] = item["node"] in mappings or bool(directory and (custom_nodes_root / directory).is_dir())
    missing = [item for item in required if not item["installed"]]
    optional = [{
        "node": "KJ Preview Override",
        "package": "ComfyUI-KJNodes",
        "installed": bool((custom_nodes_root / "ComfyUI-KJNodes").is_dir()),
    }]
    return {"required": required, "optional": optional, "missing": missing, "status": "ready" if not missing else "missing_dependencies"}


def _stage_name(index: int) -> str:
    return f"第{('一', '二', '三', '四', '五')[index - 1]}阶段"


def _validate_plan(plan: dict[str, Any]) -> tuple[list[str], list[int], int, list[str], list[dict[str, Any]]]:
    if plan.get("schema") != AGGREGATE_CONFIG_SCHEMA:
        raise ValueError("Studio 配置 schema 不匹配")
    try:
        stage_count = int(plan.get("stage_count", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"镜头数量必须是 1-{MAX_STAGES} 的整数") from exc
    if not 1 <= stage_count <= MAX_STAGES:
        raise ValueError(f"镜头数量必须在 1-{MAX_STAGES} 之间")
    prompts = plan.get("prompts")
    durations = plan.get("durations")
    transitions = plan.get("transitions")
    models = plan.get("models")
    generation = dict(plan.get("generation") or {})
    generation_stages = generation.get("stages")
    for name, values in {"prompts": prompts, "durations": durations, "transitions": transitions, "models": models, "generation.stages": generation_stages}.items():
        if not isinstance(values, list) or len(values) != stage_count:
            raise ValueError(f"{name} 数量必须与镜头数量相同")
    clean_prompts = [str(value).strip() for value in prompts]
    if any(not value for value in clean_prompts):
        raise ValueError("每个镜头都必须提供非空提示词")
    clean_durations: list[int] = []
    for index, value in enumerate(durations, start=1):
        try:
            duration = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 镜时长必须是 1-15 秒整数") from exc
        if not 1 <= duration <= 15:
            raise ValueError(f"第 {index} 镜时长必须是 1-15 秒整数")
        clean_durations.append(duration)
    clean_transitions = [str(value) for value in transitions]
    if clean_transitions[0] != "cut" or any(value not in {"cut", "tail", "motion"} for value in clean_transitions):
        raise ValueError("第一镜必须是 cut，其余镜头只能使用 cut、tail 或 motion")
    clean_models: list[dict[str, Any]] = []
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict):
            raise ValueError(f"第 {index} 镜模型配置无效")
        attention = str(model.get("attention_mode") or "MiniMax H3 Kitchen Attention")
        if attention not in {"MiniMax H3 Kitchen Attention", "Patch Sol-Attn"}:
            raise ValueError(f"第 {index} 镜注意力模式无效")
        if bool(model.get("lora_enabled", True)) and not str(model.get("lora_name") or "").strip():
            raise ValueError(f"第 {index} 镜已启用 LoRA，但没有选择 LoRA 模型")
        clean_models.append(dict(model))
    for index, transition in enumerate(clean_transitions[1:], start=1):
        if transition != "motion":
            continue
        previous = generation_stages[index - 1]
        current = generation_stages[index]
        if previous.get("aspect") != current.get("aspect") or previous.get("resolution") != current.get("resolution"):
            raise ValueError(f"第 {index + 1} 镜 Motion Context 必须与前镜使用相同初始比例和分辨率")
    target = int(plan.get("run_stage") or stage_count)
    if not 1 <= target <= stage_count:
        raise ValueError("当前目标镜头编号无效")
    return clean_prompts, clean_durations, stage_count, clean_transitions, clean_models


def build_aggregate_workflow(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a one-node prompt that executes the current Studio project directly."""

    prompts, durations, stage_count, transitions, models = _validate_plan(plan)
    target = max(1, min(stage_count, int(plan.get("run_stage") or stage_count)))
    execution_plan = dict(plan)
    execution_plan["schema"] = AGGREGATE_CONFIG_SCHEMA
    execution_plan["prompts"] = prompts
    execution_plan["durations"] = durations
    execution_plan["models"] = models
    execution_plan["transitions"] = transitions
    execution_plan["stage_count"] = stage_count
    execution_plan["run_stage"] = target
    payload = json.dumps(execution_plan, ensure_ascii=False, separators=(",", ":"))
    workflow = {
        "last_node_id": 1,
        "last_link_id": 0,
        "nodes": [{
            "id": 1,
            "type": "XYUE_H3_StudioExecutor",
            "title": f"当前目标镜头｜{_stage_name(target)}",
            "pos": [0, 0],
            "size": [420, 180],
            "flags": {},
            "mode": 0,
            "inputs": [{"name": "config_text", "localized_name": "Studio 配置", "type": "STRING", "link": None}],
            "outputs": [{"name": "当前镜头视频", "type": "VIDEO", "links": []}, {"name": "执行报告", "type": "STRING", "links": []}],
            "widgets_values": [payload],
            "properties": {"xyue_stage_index": target, "xyue_executor": True},
        }],
        "links": [],
        "groups": [],
        "extra": {"xyue_h3_execution_graph": {"source": "studio-config-v3", "target_stage": target}},
    }
    dependencies = dependency_report(workflow, execution_plan)
    report = {
        "schema": "xyue-h3/studio-execution-report-v3",
        "workflow": "XYUE H3 Studio",
        "stage_count": target,
        "planned_stage_count": stage_count,
        "run_stage": target,
        "execution_stages": list(plan.get("execution_stages") or [target]),
        "durations": durations,
        "transitions": transitions,
        "lora_enabled": [bool(model.get("lora_enabled", True)) for model in models],
        "attention_modes": [str(model.get("attention_mode") or "MiniMax H3 Kitchen Attention") for model in models],
        "dependencies": dependencies,
        "execution": "direct_studio_executor",
        "composition": dict(plan.get("composition") or {}),
    }
    return workflow, report


def config_from_text(value: Any) -> dict[str, Any]:
    data = decode_config(value)
    if data.get("schema") != AGGREGATE_CONFIG_SCHEMA:
        raise ValueError("Studio 配置 schema 不匹配")
    return data
