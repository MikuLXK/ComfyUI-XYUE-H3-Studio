"""Build the hidden canonical workflow used by the Studio aggregate node."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import GLOBAL_ACCELERATION_MODES, MAX_STAGES


PLUGIN_ROOT = Path(__file__).parents[1]
AGGREGATE_CONFIG_SCHEMA = "xyue-h3/aggregate-workflow-config-v2"
WORKFLOW_FILES = {
    "全程多参考短剧": "XYUE_H3_全程多参考短剧工作流.json",
    "多段循环": "XYUE_H3_多段循环工作流.json",
}
EXTERNAL_NODE_PACKAGES = {
    "TESpeedMiniMaxH3": "TE-Speed-MiniMaxH3",
    "MiniMaxChunkFeedForward": "ComfyUI-KJNodes",
    "MiniMaxH3MemoryEfficientSageAttentionPatch": "ComfyUI-KJNodes",
    "MiniMaxLowVRAMAttention": "ComfyUI-KJNodes",
    "ModelPatchTorchSettings": "ComfyUI-KJNodes",
    "SolAttnPatch": "ComfyUI-SolAttn_triton",
    "UniBlockSwap": "ComfyUI_UniBlockSwap",
}
EXTERNAL_NODE_DIRECTORIES = {
    "TE-Speed-MiniMaxH3": "TE-Speed-MiniMaxH3",
    "ComfyUI-KJNodes": "ComfyUI-KJNodes",
    "ComfyUI-SolAttn_triton": "ComfyUI-SolAttn_triton",
    "ComfyUI_UniBlockSwap": "ComfyUI_UniBlockSwap",
}


def _workflow_path(name: str) -> Path:
    try:
        filename = WORKFLOW_FILES[str(name)]
    except KeyError as exc:
        raise ValueError(f"不支持的聚合工作流：{name}") from exc
    return PLUGIN_ROOT / "workflows" / filename


def load_workflow(name: str = "全程多参考短剧") -> dict[str, Any]:
    return json.loads(_workflow_path(name).read_text(encoding="utf-8-sig"))


def dependency_report(workflow: dict[str, Any]) -> dict[str, Any]:
    node_types = sorted({str(node.get("type")) for node in workflow.get("nodes", []) if node.get("type")})
    required = [
        {"node": node_type, "package": EXTERNAL_NODE_PACKAGES[node_type]}
        for node_type in node_types
        if node_type in EXTERNAL_NODE_PACKAGES
    ]
    mappings = {}
    try:
        import nodes as comfy_nodes

        mappings = getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", {}) or {}
    except Exception:
        pass
    custom_nodes_root = PLUGIN_ROOT.parent
    for item in required:
        directory = EXTERNAL_NODE_DIRECTORIES.get(item["package"])
        item["installed"] = item["node"] in mappings or bool(directory and (custom_nodes_root / directory).is_dir())
    missing = [item for item in required if not item["installed"]]
    return {"required": required, "missing": missing, "status": "ready" if not missing else "missing_dependencies"}


def _validate_plan(plan: dict[str, Any]) -> tuple[list[str], list[int], int, list[str], list[str]]:
    if plan.get("schema") != AGGREGATE_CONFIG_SCHEMA:
        raise ValueError("聚合配置 schema 不匹配")
    try:
        stage_count = int(plan.get("stage_count", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"stage_count 必须是 1-{MAX_STAGES} 的整数") from exc
    if not 1 <= stage_count <= MAX_STAGES:
        raise ValueError(f"stage_count 必须在 1-{MAX_STAGES} 之间")

    stage_titles = plan.get("stage_titles")
    prompts = plan.get("prompts")
    durations = plan.get("durations")
    transitions = plan.get("transitions")
    acceleration_modes = plan.get("acceleration_modes")
    models = plan.get("models")
    generation = dict(plan.get("generation") or {})
    generation_stages = generation.get("stages")
    for name, values in {
        "prompts": prompts,
        "durations": durations,
        "transitions": transitions,
        "acceleration_modes": acceleration_modes,
        "models": models,
        "generation.stages": generation_stages,
    }.items():
        if not isinstance(values, list) or len(values) != stage_count:
            raise ValueError(f"{name} 数量必须与 stage_count 相同")
    if any(not isinstance(value, dict) for value in generation_stages):
        raise ValueError("每个 generation.stages 项都必须是 JSON 对象")

    if stage_titles is not None:
        if not isinstance(stage_titles, list) or len(stage_titles) != stage_count:
            raise ValueError("stage_titles 数量必须与 stage_count 相同")
        clean_titles = [str(value).strip() for value in stage_titles]
        if any(not value or len(value) > 40 for value in clean_titles):
            raise ValueError("镜头名称必须为 1-40 个字符")

    clean_prompts = [str(value).strip() for value in prompts]
    if any(not value for value in clean_prompts):
        raise ValueError("每个镜头都必须提供非空提示词")
    clean_durations = []
    for index, value in enumerate(durations, start=1):
        if isinstance(value, bool):
            raise ValueError(f"第 {index} 镜时长必须是 1-15 秒整数")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 镜时长必须是 1-15 秒整数") from exc
        if not numeric.is_integer() or not 1 <= int(numeric) <= 15:
            raise ValueError(f"第 {index} 镜时长必须是 1-15 秒整数")
        clean_durations.append(int(numeric))

    clean_modes = [str(value) for value in acceleration_modes]
    if any(value not in GLOBAL_ACCELERATION_MODES for value in clean_modes):
        raise ValueError(f"镜头加速模式必须是：{'、'.join(GLOBAL_ACCELERATION_MODES)}")
    clean_transitions = [str(value) for value in transitions]
    if clean_transitions[0] != "cut" or any(value not in {"cut", "tail"} for value in clean_transitions):
        raise ValueError("第一镜必须为独立起始，其余本镜衔接只能是 cut 或 tail")
    for index, (model, transition) in enumerate(zip(models, clean_transitions), start=1):
        if not isinstance(model, dict):
            raise ValueError(f"第 {index} 镜模型配置无效")
        if transition == "tail" and model.get("mode") not in {"首帧生视频模式", "多参考模式"}:
            raise ValueError(
                f"第 {index} 镜承接上一镜尾帧时只能选择首帧生视频模式或多参考模式"
            )
    return clean_prompts, clean_durations, stage_count, clean_modes, clean_transitions


def _stage_nodes(workflow: dict[str, Any], node_type: str) -> dict[int, dict[str, Any]]:
    result = {}
    for node in workflow.get("nodes", []):
        if node.get("type") != node_type:
            continue
        stage = int((node.get("properties") or {}).get("xyue_stage_index") or 0)
        if stage and stage not in result:
            result[stage] = node
    return result


def _tail_extractors_by_target_stage(workflow: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Resolve each tail extractor from its actual previous-stage video link."""

    nodes = {str(node.get("id")): node for node in workflow.get("nodes", [])}
    links = {int(link[0]): link for link in workflow.get("links", [])}
    result: dict[int, dict[str, Any]] = {}
    for extractor in workflow.get("nodes", []):
        if extractor.get("type") != "XYUE_H3_LastFrameExtractor":
            continue
        video_input = next((item for item in extractor.get("inputs", []) if item.get("name") == "video"), None)
        link = links.get(int(video_input["link"])) if video_input and video_input.get("link") is not None else None
        source = nodes.get(str(link[1])) if link else None
        source_stage = int((source or {}).get("properties", {}).get("xyue_stage_index") or 0)
        if source_stage <= 0:
            continue
        target_stage = source_stage + 1
        if target_stage in result:
            raise ValueError(f"上一镜尾帧来源重复：第 {target_stage} 镜")
        result[target_stage] = extractor
    return result


def _remove_input_link(workflow: dict[str, Any], node: dict[str, Any], name: str) -> None:
    target = next((item for item in node.get("inputs", []) if item.get("name") == name), None)
    if target is None or target.get("link") is None:
        return
    link_id = int(target["link"])
    target["link"] = None
    workflow["links"] = [link for link in workflow.get("links", []) if int(link[0]) != link_id]
    for source in workflow.get("nodes", []):
        for output in source.get("outputs", []):
            if isinstance(output.get("links"), list):
                output["links"] = [value for value in output["links"] if int(value) != link_id]


def _add_link(workflow: dict[str, Any], source: dict[str, Any], source_slot: int, target: dict[str, Any], input_name: str, link_type: str) -> None:
    _remove_input_link(workflow, target, input_name)
    target_slot = next(index for index, item in enumerate(target.get("inputs", [])) if item.get("name") == input_name)
    link_id = int(workflow.get("last_link_id", 0)) + 1
    workflow["last_link_id"] = link_id
    workflow.setdefault("links", []).append([link_id, source["id"], source_slot, target["id"], target_slot, link_type])
    target["inputs"][target_slot]["link"] = link_id
    outputs = source.setdefault("outputs", [])
    while len(outputs) <= source_slot:
        outputs.append({"name": "本阶段加速控制", "type": link_type, "links": []})
    outputs[source_slot].setdefault("links", []).append(link_id)


def _wire_stage_acceleration(workflow: dict[str, Any], modes: list[str]) -> None:
    controllers = _stage_nodes(workflow, "XYUE_H3_AccelerationController")
    generators = _stage_nodes(workflow, "XYUE_H3_Generator")
    for stage, mode in enumerate(modes, start=1):
        controller = controllers.get(stage)
        generator = generators.get(stage)
        if controller is None or generator is None:
            raise ValueError(f"标准工作流缺少第 {stage} 镜加速控制链")
        controller["widgets_values"] = [mode]
        mode_input = next((item for item in controller.get("inputs", []) if item.get("name") in {"enabled", "mode"}), None)
        if mode_input is None:
            raise ValueError(f"第 {stage} 镜加速控制器缺少模式输入")
        mode_input.update({"name": "mode", "localized_name": "本阶段加速模式", "type": "COMBO", "widget": {"name": "mode"}, "link": None})
        _remove_input_link(workflow, controller, "global_acceleration")
        _remove_input_link(workflow, generator, "global_acceleration")
        outputs = controller.setdefault("outputs", [])
        if len(outputs) < 3:
            outputs.append({"localized_name": "本阶段加速控制", "name": "本阶段加速控制", "type": "XYUE_H3_GLOBAL_ACCELERATION_CONTROL", "slot_index": 2, "links": []})
        _add_link(workflow, controller, 2, generator, "global_acceleration", "XYUE_H3_GLOBAL_ACCELERATION_CONTROL")


def _wire_stage_inputs(workflow: dict[str, Any], transitions: list[str], models: list[dict[str, Any]]) -> None:
    generators = _stage_nodes(workflow, "XYUE_H3_Generator")
    prompt_editors = _stage_nodes(workflow, "XYUE_H3_PromptEditor")
    prompt_enhancers = _stage_nodes(workflow, "XYUE_H3_PromptEnhancer")
    continuation_refs = _stage_nodes(workflow, "XYUE_H3_ContinuationReference")
    material_manager = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_MaterialManager"),
        None,
    )
    if material_manager is None:
        raise ValueError("标准工作流缺少集中素材管理节点")
    extractor_for_stage = _tail_extractors_by_target_stage(workflow)
    for stage, (transition, model) in enumerate(zip(transitions, models), start=1):
        generator = generators.get(stage)
        if generator is None:
            raise ValueError(f"标准工作流缺少第 {stage} 镜生成器")
        mode = str(model.get("mode") or "")
        if mode != "多参考模式":
            _remove_input_link(workflow, generator, "material_pack")
        if mode not in {"首帧生视频模式", "首尾帧生视频模式"}:
            _remove_input_link(workflow, generator, "first_frame")
        if mode not in {"尾帧续写模式", "首尾帧生视频模式"}:
            _remove_input_link(workflow, generator, "last_frame")
        prompt_nodes = [node for node in (prompt_editors.get(stage), prompt_enhancers.get(stage)) if node]
        registry_source = None
        if stage > 1 and mode == "多参考模式":
            continuation = continuation_refs.get(stage)
            if transition == "tail":
                extractor = extractor_for_stage.get(stage)
                if extractor is None:
                    raise ValueError(f"标准工作流缺少第 {stage} 镜的上一镜尾帧来源")
                if continuation is None:
                    raise ValueError(f"标准工作流缺少第 {stage} 镜续接引用节点")
                continuation_values = list(continuation.get("widgets_values") or [])
                continuation_values.extend([None] * (2 - len(continuation_values)))
                continuation_values[1] = "尾帧"
                continuation["widgets_values"] = continuation_values
                _add_link(workflow, extractor, 0, continuation, "continuation_frame", "IMAGE")
                _add_link(workflow, continuation, 0, generator, "material_pack", "XYUE_H3_MATERIAL_PACK")
                registry_source = continuation
            else:
                if continuation is not None:
                    _remove_input_link(workflow, continuation, "continuation_frame")
                _add_link(workflow, material_manager, 0, generator, "material_pack", "XYUE_H3_MATERIAL_PACK")
                registry_source = material_manager
        elif mode == "多参考模式":
            registry_source = material_manager
        elif stage > 1 and continuation_refs.get(stage) is not None:
            _remove_input_link(workflow, continuation_refs[stage], "continuation_frame")
        for prompt_node in prompt_nodes:
            if registry_source is None:
                _remove_input_link(workflow, prompt_node, "mention_registry")
            else:
                _add_link(
                    workflow,
                    registry_source,
                    1,
                    prompt_node,
                    "mention_registry",
                    "XYUE_H3_MENTION_REGISTRY",
                )
        if transition == "tail":
            extractor = extractor_for_stage.get(stage)
            if extractor is None:
                raise ValueError(f"标准工作流缺少第 {stage} 镜的上一镜尾帧来源")
            if mode == "首帧生视频模式":
                _add_link(workflow, extractor, 0, generator, "first_frame", "IMAGE")


def _remove_multi_stage_config(workflow: dict[str, Any]) -> None:
    removed_ids = {
        str(node["id"])
        for node in workflow.get("nodes", [])
        if node.get("type") == "XYUE_H3_MultiStageConfig"
    }
    if not removed_ids:
        return
    removed_links = {
        int(link[0])
        for link in workflow.get("links", [])
        if str(link[1]) in removed_ids or str(link[3]) in removed_ids
    }
    workflow["nodes"] = [node for node in workflow.get("nodes", []) if str(node.get("id")) not in removed_ids]
    workflow["links"] = [link for link in workflow.get("links", []) if int(link[0]) not in removed_links]
    for node in workflow["nodes"]:
        for input_item in node.get("inputs", []):
            if input_item.get("link") is not None and int(input_item["link"]) in removed_links:
                input_item["link"] = None
        for output in node.get("outputs", []):
            if isinstance(output.get("links"), list):
                output["links"] = [link_id for link_id in output["links"] if int(link_id) not in removed_links]
    workflow.setdefault("extra", {}).pop("xyue_h3_multi_stage_config", None)


def build_aggregate_workflow(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    prompts, durations, stage_count, modes, transitions = _validate_plan(plan)
    workflow_name = str(plan.get("workflow") or "全程多参考短剧")
    workflow = load_workflow(workflow_name)
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    from tools.configure_multi_stage_workflow import configure_workflow

    generation = copy.deepcopy(dict(plan["generation"]))
    for index, duration in enumerate(durations):
        generation["stages"][index]["duration"] = duration

    configured = configure_workflow(
        copy.deepcopy(workflow),
        prompts,
        durations,
        generation=generation,
        acceleration={"global_mode": "不启用"},
        models=list(plan["models"]),
        stage_count=stage_count,
    )
    _remove_multi_stage_config(configured)
    _wire_stage_acceleration(configured, modes)
    _wire_stage_inputs(configured, transitions, list(plan["models"]))
    dependencies = dependency_report(configured)
    report = {
        "schema": "xyue-h3/aggregate-workflow-report-v2",
        "workflow": workflow_name,
        "stage_count": stage_count,
        "durations": durations,
        "transitions": transitions,
        "acceleration_modes": modes,
        "dependencies": dependencies,
        "execution": "canonical_workflow_template",
    }
    return configured, report


def config_from_text(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        data = dict(value)
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("聚合配置不能为空")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"聚合配置不是有效 JSON：第 {exc.lineno} 行，第 {exc.colno} 列") from exc
    if not isinstance(data, dict):
        raise ValueError("聚合配置顶层必须是 JSON 对象")
    if data.get("schema") != AGGREGATE_CONFIG_SCHEMA:
        raise ValueError("聚合配置 schema 不匹配")
    return data
