"""Build the five-lane continuation workflow from the maintained multi-stage seed."""

from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "workflows" / "XYUE_H3_多段循环工作流.json"
USER_COPY = ROOT.parents[1] / "user" / "default" / "workflows" / SOURCE.name
USER_WORKFLOW_DIR = ROOT.parents[1] / "user" / "default" / "workflows"
MAX_STAGES = 5
STAGE_AUTO_STATE = "xyue_h3_auto_mode_state"

STAGE_MARKERS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")
STAGE_TYPES = {
    "XYUE_H3_PromptEditor",
    "XYUE_H3_PromptEnhancer",
    "XYUE_H3_ModeModelSelector",
    "XYUE_H3_StageGenerationProfile",
    "XYUE_H3_LoRASelector",
    "TESpeedMiniMaxH3",
    "MiniMaxChunkFeedForward",
    "MiniMaxH3MemoryEfficientSageAttentionPatch",
    "SolAttnPatch",
    "XYUE_H3_Generator",
    "XYUE_H3_StageCheckpointSave",
    "XYUE_H3_StageResume",
    "XYUE_H3_LastFrameExtractor",
    "XYUE_H3_AccelerationController",
    "XYUE_H3_ContinuationReference",
    "MiniMaxLowVRAMAttention",
    "UniBlockSwap",
    "ModelPatchTorchSettings",
}


def _node(data: dict, node_id: int) -> dict:
    return next(node for node in data["nodes"] if node["id"] == node_id)


def _stage_ids(data: dict, low: float, high: float) -> set[int]:
    return {
        node["id"]
        for node in data["nodes"]
        if node.get("type") in STAGE_TYPES
        and low <= float(node.get("pos", [0, 0])[1]) <= high
    }


def _stage_name(index: int) -> str:
    return f"第{STAGE_MARKERS[index - 1]}阶段"


def _clear_links(node: dict) -> None:
    for item in node.get("inputs", []):
        item["link"] = None
    for output in node.get("outputs", []):
        output["links"] = []


def _append_link(data: dict, link: list) -> None:
    data["links"].append(link)
    source = _node(data, link[1])
    target = _node(data, link[3])
    source["outputs"][link[2]].setdefault("links", []).append(link[0])
    target["inputs"][link[4]]["link"] = link[0]


def _ensure_multistage_config(data: dict) -> None:
    """Add one runtime config node and connect every multi-stage consumer."""

    targets = {
        "XYUE_H3_PromptEditor",
        "XYUE_H3_PromptEnhancer",
        "XYUE_H3_StageGenerationProfile",
        "XYUE_H3_StudioController",
        "XYUE_H3_GlobalAccelerationManager",
    }
    existing = next((node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_MultiStageConfig"), None)
    if existing is None:
        config_id = max((int(node["id"]) for node in data["nodes"]), default=0) + 1
        existing = {
            "id": config_id,
            "type": "XYUE_H3_MultiStageConfig",
            "title": "多段云端配置｜粘贴 JSON",
            "pos": [-620, -3550],
            "size": [620, 520],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {"name": "多段配置", "type": "XYUE_H3_MULTI_STAGE_CONFIG", "links": [], "slot_index": 0},
                {"name": "配置报告", "type": "STRING", "links": [], "slot_index": 1},
            ],
            "properties": {"Node name for S&R": "XYUE_H3_MultiStageConfig", "xyue_title_contrast": "soft", "xyue_ui_title_color": "#e5e7eb"},
            "widgets_values": [""],
            "color": "#40566d",
            "bgcolor": "#202b36",
        }
        data["nodes"].append(existing)
    config_id = int(existing["id"])
    existing["widgets_values"] = [""]

    stage_nodes = {
        node_type: sorted(
            (node for node in data["nodes"] if node.get("type") == node_type),
            key=lambda node: float(node.get("pos", [0, 0])[1]),
        )
        for node_type in targets
    }
    for index, node in enumerate(stage_nodes["XYUE_H3_PromptEditor"], start=1):
        values = node.setdefault("widgets_values", [])
        while len(values) <= 3:
            values.append(None)
        values[3] = index
    for index, node in enumerate(stage_nodes["XYUE_H3_PromptEnhancer"], start=1):
        values = node.setdefault("widgets_values", [])
        while len(values) <= 4:
            values.append(None)
        values[3] = False
        values[4] = index

    next_link = max((int(link[0]) for link in data.get("links", [])), default=0) + 1
    existing["outputs"][0]["links"] = list(dict.fromkeys(existing["outputs"][0].get("links", [])))
    for node_type in targets:
        for node in stage_nodes[node_type]:
            config_input = next((item for item in node.setdefault("inputs", []) if item.get("name") == "multi_stage_config"), None)
            if config_input is None:
                config_input = {"name": "multi_stage_config", "type": "XYUE_H3_MULTI_STAGE_CONFIG", "link": None}
                node["inputs"].append(config_input)
            if config_input.get("link") is not None:
                if config_input["link"] not in existing["outputs"][0]["links"]:
                    existing["outputs"][0]["links"].append(config_input["link"])
                continue
            target_slot = node["inputs"].index(config_input)
            _append_link(data, [next_link, config_id, 0, int(node["id"]), target_slot, "XYUE_H3_MULTI_STAGE_CONFIG"])
            next_link += 1
    data.setdefault("extra", {})["xyue_h3_multi_stage_config"] = {"node_id": config_id, "stage_count": len(stage_nodes["XYUE_H3_PromptEditor"])}
    data["last_node_id"] = max(int(node["id"]) for node in data["nodes"])
    data["last_link_id"] = max((int(link[0]) for link in data.get("links", [])), default=0)


def _ensure_video_board(data: dict) -> None:
    existing = next((node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_VideoBoard"), None)
    resume_nodes = sorted(
        (node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_StageResume"),
        key=lambda node: float(node.get("pos", [0, 0])[1]),
    )[:MAX_STAGES]
    controller = next((node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_StudioController"), None)
    if len(resume_nodes) != MAX_STAGES or controller is None:
        return
    old_concat = next((node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_VideoConcat"), None)
    if old_concat is not None:
        old_id = int(old_concat["id"])
        data["nodes"] = [node for node in data["nodes"] if int(node["id"]) != old_id]
        data["links"] = [link for link in data.get("links", []) if link[1] != old_id and link[3] != old_id]
    old_finish = next((node for node in data.get("nodes", []) if node.get("type") == "XYUE_H3_StageFinish"), None)
    if old_finish is not None:
        old_id = int(old_finish["id"])
        data["nodes"] = [node for node in data["nodes"] if int(node["id"]) != old_id]
        data["links"] = [link for link in data.get("links", []) if link[1] != old_id and link[3] != old_id]
    link_ids = {int(link[0]) for link in data.get("links", [])}
    for node in data["nodes"]:
        for item in node.get("inputs", []):
            if item.get("link") not in link_ids:
                item["link"] = None
        for output in node.get("outputs", []):
            output["links"] = [link for link in output.get("links", []) if link in link_ids]

    board = existing
    if board is None:
        board_id = max((int(node["id"]) for node in data["nodes"]), default=0) + 1
        board = {
            "id": board_id,
            "type": "XYUE_H3_VideoBoard",
            "title": "XYUE_五段视频完成面板｜上3下3",
            "pos": [7100, -2350],
            "size": [920, 800],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {"name": "最终合成视频", "type": "VIDEO", "links": [], "slot_index": 0},
                {"name": "面板报告", "type": "STRING", "links": [], "slot_index": 1},
            ],
            "properties": {"Node name for S&R": "XYUE_H3_VideoBoard", "xyue_video_board_layout": "3x2"},
            "widgets_values": ["xyue_h3/多段/最终合成", "mp4", "h264"],
            "color": "#4e666c",
            "bgcolor": "#202b36",
        }
        data["nodes"].append(board)
    else:
        board_id = int(board["id"])
        board["widgets_values"] = ["xyue_h3/多段/最终合成", "mp4", "h264"]
        board["inputs"] = []
        board["outputs"] = [
            {"name": "最终合成视频", "type": "VIDEO", "links": [], "slot_index": 0},
            {"name": "面板报告", "type": "STRING", "links": [], "slot_index": 1},
        ]
    data["links"] = [link for link in data.get("links", []) if link[1] != board_id and link[3] != board_id]
    next_link = max((int(link[0]) for link in data.get("links", [])), default=0) + 1
    board["inputs"] = [
        {"name": f"stage{index}_video", "type": "VIDEO", "link": None}
        for index in range(1, MAX_STAGES + 1)
    ] + [
        {"name": f"stage{index}_report", "type": "STRING", "link": None}
        for index in range(1, MAX_STAGES + 1)
    ] + [{"name": "studio_control", "type": "XYUE_H3_STUDIO_CONTROL", "link": None}]
    for index, resume in enumerate(resume_nodes):
        _append_link(data, [next_link, int(resume["id"]), 0, board_id, index, "VIDEO"])
        next_link += 1
        _append_link(data, [next_link, int(resume["id"]), 1, board_id, MAX_STAGES + index, "STRING"])
        next_link += 1
    _append_link(data, [next_link, int(controller["id"]), 0, board_id, MAX_STAGES * 2, "XYUE_H3_STUDIO_CONTROL"])
    data.setdefault("extra", {})["xyue_h3_video_board"] = {"node_id": board_id, "layout": "3x2", "stage_count": MAX_STAGES}
    data["last_node_id"] = board_id
    data["last_link_id"] = next_link


def _set_group_metadata(group: dict, *, stage_index: int | None = None, role: str | None = None) -> None:
    properties = group.setdefault("properties", {})
    if stage_index is not None:
        properties["xyue_stage_index"] = stage_index
    if role is not None:
        properties["xyue_group_role"] = role


def _reflow_layout(data: dict) -> None:
    """Place materials/output at the top and all five stage lanes below them."""

    groups = data.get("groups") or []
    _assign_stage_metadata(data)
    editors_by_stage = {}
    for node in data.get("nodes", []):
        if node.get("type") == "XYUE_H3_PromptEditor":
            stage = node.get("properties", {}).get("xyue_stage_index")
            if stage is not None:
                editors_by_stage[int(stage)] = node
    for stage_index in range(1, MAX_STAGES + 1):
        anchor = editors_by_stage.get(stage_index)
        if anchor is None:
            continue
        current_y = float(anchor.get("pos", [0, 0])[1])
        delta_y = 350 + (stage_index - 1) * 1500 - current_y
        for node in data.get("nodes", []):
            if node.get("properties", {}).get("xyue_stage_index") == stage_index:
                node["pos"][1] = float(node["pos"][1]) + delta_y
        target_y = 350 + (stage_index - 1) * 1500
        for node in data.get("nodes", []):
            if node.get("properties", {}).get("xyue_stage_index") != stage_index:
                continue
            y = float(node["pos"][1])
            if y < target_y:
                node["pos"][1] = target_y
            elif y > target_y + 1200:
                node["pos"][1] = target_y + 1000

    for node in data.get("nodes", []):
        node_type = node.get("type")
        if node_type == "XYUE_H3_MultiStageConfig":
            node["pos"] = [-56.01483306328036, -3481.487893595087]
        elif node_type == "XYUE_H3_StudioController":
            node["pos"] = [661.3548538248697, -3393.2717042883296]
        elif node_type == "XYUE_H3_GlobalLoRAManager":
            node["pos"] = [1138.4498724905986, -3393.8570745981906]
        elif node_type == "XYUE_H3_GlobalAccelerationManager":
            node["pos"] = [1141.235448410034, -2978.5485669693085]
        elif node_type == "XYUE_H3_VideoBoard":
            node["pos"] = [3250.287797033234, -2064.3761913927883]

    materials = groups[0]
    global_group = groups[1]
    output_group = next((group for group in groups if group.get("properties", {}).get("xyue_group_role") == "output"), groups[-1])
    flow_group = {
        "title": "④ 五段底部流程",
        "bounding": [-100, 250, 7200, 8000],
        "color": "#586174",
        "font_size": 26,
        "flags": {},
        "properties": {"xyue_group_role": "stage_flow", "xyue_stage_count": MAX_STAGES},
    }
    materials["title"] = "① 左侧素材区域｜图片 / 视频 / 音频"
    materials["bounding"] = [-116.403934157505, -2296.79461785398, 2840, 2220]
    global_group["title"] = "② 顶部全局配置与加速"
    global_group["bounding"] = [-119.202241980658, -3783.00129000731, 1784.00674977146, 1209.12300229336]
    output_group["title"] = "③ 右侧完成面板｜上3下3"
    output_group["bounding"] = [3130.28779703323, -2284.37619139279, 3960.97213879142, 2204.93971879142]
    data["groups"] = [materials, global_group, flow_group, output_group]


def _stage_from_title(title: str) -> int | None:
    markers = ("一", "二", "三", "四", "五")
    for index, marker in enumerate(markers, start=1):
        if f"第{marker}段" in title or f"第{marker}阶段" in title:
            return index
    for index in range(1, MAX_STAGES + 1):
        if f"阶段{index}" in title or f"阶段 {index}" in title or f"第{index}段" in title:
            return index
    return None


def _assign_stage_metadata(data: dict) -> None:
    nodes = {int(node["id"]): node for node in data.get("nodes", [])}
    incoming: dict[int, set[int]] = {node_id: set() for node_id in nodes}
    outgoing: dict[int, set[int]] = {node_id: set() for node_id in nodes}
    for link in data.get("links", []):
        source_id, target_id = int(link[1]), int(link[3])
        if source_id in nodes and target_id in nodes:
            incoming[target_id].add(source_id)
            outgoing[source_id].add(target_id)

    for node in nodes.values():
        properties = node.setdefault("properties", {})
        state = properties.pop(STAGE_AUTO_STATE, None)
        if isinstance(state, dict) and state.get("original_mode") is not None:
            node["mode"] = int(state["original_mode"])
        if node.get("type") in STAGE_TYPES:
            properties.pop("xyue_stage_index", None)

    editors = [node for node in nodes.values() if node.get("type") == "XYUE_H3_PromptEditor"]
    anchors: dict[int, float] = {}
    for node in editors:
        stage = _stage_from_title(str(node.get("title", "")))
        if stage is not None:
            anchors[stage] = float(node.get("pos", [0, 0])[1])
    if len(anchors) < MAX_STAGES:
        for stage, node in enumerate(sorted(editors, key=lambda item: float(item.get("pos", [0, 0])[1])), start=1):
            anchors.setdefault(stage, float(node.get("pos", [0, 0])[1]))

    generator_stages: dict[int, int] = {}
    for generator in (node for node in nodes.values() if node.get("type") == "XYUE_H3_Generator"):
        explicit = _stage_from_title(str(generator.get("title", "")))
        found: set[int] = {explicit} if explicit is not None else set()
        visited: set[int] = set()
        pending = [int(generator["id"])]
        while pending and not found:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            source = nodes[node_id]
            stage = _stage_from_title(str(source.get("title", "")))
            if stage is not None:
                found.add(stage)
                continue
            if source.get("type") == "XYUE_H3_ContinuationReference":
                continue
            pending.extend(
                source_id for source_id in incoming[node_id]
                if nodes[source_id].get("type") in STAGE_TYPES
            )
        if len(found) == 1:
            generator_stages[int(generator["id"])] = found.pop()

    owners: dict[int, set[int]] = {node_id: set() for node_id in nodes}
    for generator_id, stage in generator_stages.items():
        pending = [generator_id]
        visited: set[int] = set()
        while pending:
            node_id = pending.pop()
            if node_id in visited or nodes[node_id].get("type") not in STAGE_TYPES:
                continue
            visited.add(node_id)
            owners[node_id].add(stage)
            if nodes[node_id].get("type") == "XYUE_H3_ContinuationReference":
                continue
            pending.extend(incoming[node_id])

        pending = [generator_id]
        visited.clear()
        while pending:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            owners[node_id].add(stage)
            for target_id in outgoing[node_id]:
                target = nodes[target_id]
                if target.get("type") in STAGE_TYPES and target.get("type") != "XYUE_H3_ContinuationReference":
                    pending.append(target_id)

    for node_id, node in nodes.items():
        if node.get("type") not in STAGE_TYPES:
            continue
        stages = owners[node_id]
        stage = next(iter(stages)) if len(stages) == 1 else _stage_from_title(str(node.get("title", "")))
        if stage is None and anchors:
            y = float(node.get("pos", [0, 0])[1])
            stage = min(anchors, key=lambda index: abs(anchors[index] - y))
        if stage is not None:
            node["properties"]["xyue_stage_index"] = stage


def _annotate_acceleration_modes(data: dict) -> None:
    """Mark branch-only nodes so the frontend can mute unused acceleration paths."""

    branch_inputs = {
        "模式1": "accelerated_model",
        "模式2": "hq_model",
        "模式3": "experimental_model",
    }
    nodes = {int(node["id"]): node for node in data.get("nodes", [])}
    links = {int(link[0]): link for link in data.get("links", [])}
    for node in nodes.values():
        properties = node.get("properties")
        if properties is not None:
            properties.pop("xyue_acceleration_modes", None)

    for controller in (node for node in nodes.values() if node.get("type") == "XYUE_H3_AccelerationController"):
        branches: dict[str, set[int]] = {}
        for mode, input_name in branch_inputs.items():
            input_spec = next((item for item in controller.get("inputs", []) if item.get("name") == input_name), None)
            link = links.get(int(input_spec["link"])) if input_spec and input_spec.get("link") is not None else None
            if link is None:
                continue
            visited: set[int] = set()
            pending = [int(link[1])]
            while pending:
                node_id = pending.pop()
                if node_id in visited or node_id == int(controller["id"]):
                    continue
                visited.add(node_id)
                source = nodes.get(node_id)
                if source is None:
                    continue
                for item in source.get("inputs", []):
                    if item.get("link") is not None and int(item["link"]) in links:
                        pending.append(int(links[int(item["link"])][1]))
            branches[mode] = visited

        for mode, branch in branches.items():
            shared = set().union(*(other for other_mode, other in branches.items() if other_mode != mode))
            for node_id in branch - shared:
                properties = nodes[node_id].setdefault("properties", {})
                modes = set(properties.get("xyue_acceleration_modes") or [])
                modes.add(mode)
                properties["xyue_acceleration_modes"] = sorted(modes)

    for node in nodes.values():
        if "模式3" in str(node.get("title", "")) and not node.get("properties", {}).get("xyue_acceleration_modes"):
            node.setdefault("properties", {})["xyue_acceleration_modes"] = ["模式3"]


def _set_stage_group_metadata(data: dict) -> None:
    groups = data.get("groups") or []
    roles = ("materials", "global", "stage_flow", "output")
    for group, role in zip(groups, roles):
        _set_group_metadata(group, role=role)


def _clone_stage(
    data: dict,
    source_ids: set[int],
    mapping: dict[int, int],
    external_sources: dict[int, int],
    external_targets: dict[int, tuple[int, int]],
    stage: int,
    *,
    clone_nodes: bool = True,
    write_links: bool = True,
    update_metadata: bool = True,
) -> None:
    source_nodes = [node for node in data["nodes"] if node["id"] in source_ids]
    if clone_nodes:
        for source in source_nodes:
            clone = copy.deepcopy(source)
            clone["id"] = mapping[source["id"]]
            clone["pos"] = [clone["pos"][0], clone["pos"][1] + (3000 + (stage - 4) * 1250 if stage < MAX_STAGES else 5000)]
            _clear_links(clone)
            data["nodes"].append(clone)

    if update_metadata:
        marker = _stage_name(stage)
        for source in source_nodes:
            clone = _node(data, mapping[source["id"]])
            clone.setdefault("properties", {})["xyue_stage_index"] = stage
            node_type = clone["type"]
            if node_type == "XYUE_H3_PromptEditor":
                clone["title"] = f"提示词编辑器｜首帧生视频模式｜第{STAGE_MARKERS[stage - 1]}段"
                clone["widgets_values"][0] = "首帧生视频模式"
                clone["widgets_values"][2] = f"请填写第{STAGE_MARKERS[stage - 1]}阶段 H3 提示词。\n\n上一阶段尾帧为硬首帧，保持连续性。"
            elif node_type == "XYUE_H3_PromptEnhancer":
                clone["title"] = f"提示词强化器｜第{STAGE_MARKERS[stage - 1]}段"
                values = clone.setdefault("widgets_values", [])
                while len(values) <= 4:
                    values.append(None)
                values[3] = False
                values[4] = stage
            elif node_type == "XYUE_H3_ModeModelSelector":
                clone["title"] = f"模式与模型选择｜首帧生视频模式｜第{STAGE_MARKERS[stage - 1]}段"
                clone["widgets_values"][0] = "首帧生视频模式"
            elif node_type == "XYUE_H3_StageGenerationProfile":
                clone["title"] = f"阶段{stage}｜独立生成参数（由全局开关决定）"
            elif node_type == "XYUE_H3_StageCheckpointSave":
                clone["title"] = f"{marker}｜保存视频检查点"
                clone["widgets_values"][0] = marker
                clone["widgets_values"][1] = f"xyue_h3/多段循环/{marker}"
            elif node_type == "XYUE_H3_StageResume":
                clone["title"] = f"{marker}｜运行或从保存视频续接｜启用续跑"
                clone["widgets_values"][2] = marker
            elif node_type == "XYUE_H3_LastFrameExtractor":
                clone["title"] = f"尾帧截取器｜第{STAGE_MARKERS[stage - 1]}段"
            elif node_type in {"XYUE_H3_Generator", "TESpeedMiniMaxH3", "XYUE_H3_LoRASelector"}:
                clone["title"] = f"{clone.get('title', node_type)}｜第{STAGE_MARKERS[stage - 1]}段"

    if not write_links:
        return
    next_link = max((int(link[0]) for link in data["links"]), default=0) + 1
    for link in list(data["links"]):
        source_id, target_id = link[1], link[3]
        if target_id not in source_ids and source_id not in source_ids:
            continue
        if target_id in source_ids:
            new_target = mapping[target_id]
            target_slot = link[4]
        else:
            target_info = external_targets.get(target_id)
            if target_info is None:
                continue
            new_target, target_slot = target_info
        new_source = mapping.get(source_id, external_sources.get(source_id, source_id))
        new_link = [next_link, new_source, link[2], new_target, target_slot, link[5]]
        next_link += 1
        _append_link(data, new_link)


def _add_optional_inputs(data: dict, concat_id: int, resume_ids: list[int]) -> None:
    concat = _node(data, concat_id)
    original_inputs = list(concat.get("inputs", []))
    stage_inputs = [
        item for item in original_inputs
        if str(item.get("name", "")).startswith("stage")
        and str(item.get("name", "")).endswith("_video")
        and 1 <= int(str(item["name"])[5:-6]) <= MAX_STAGES
    ]
    stage_names = {item.get("name") for item in stage_inputs}
    stage_inputs.extend(
        {"name": f"stage{index}_video", "type": "VIDEO", "link": None}
        for index in range(1, MAX_STAGES + 1)
        if f"stage{index}_video" not in stage_names
    )
    stage_inputs.sort(key=lambda item: int(str(item["name"])[5:-6]))
    tail_inputs = [
        item for item in original_inputs
        if item not in stage_inputs and not (str(item.get("name", "")).startswith("stage") and str(item.get("name", "")).endswith("_video"))
    ]
    old_slots = {index: item for index, item in enumerate(original_inputs)}
    kept_slots = [index for index, item in old_slots.items() if item in stage_inputs or item in tail_inputs]
    slot_map = {old: new for new, old in enumerate(kept_slots)}
    concat["inputs"] = stage_inputs + tail_inputs
    for link in list(data["links"]):
        if link[3] != concat_id:
            continue
        if link[4] not in slot_map:
            data["links"].remove(link)
            continue
        link[4] = slot_map[link[4]]
    if not resume_ids:
        return
    next_link = max((int(link[0]) for link in data["links"]), default=0) + 1
    for index, resume_id in enumerate(resume_ids, start=4):
        if concat["inputs"][index - 1].get("link") is not None:
            continue
        link = [next_link, resume_id, 0, concat_id, index - 1, "VIDEO"]
        next_link += 1
        _append_link(data, link)


def _update_layout(data: dict) -> None:
    groups = data["groups"]
    groups[1]["title"] = "② 全局控制｜HQ 双段采样与 LoRA 管理"
    groups[1]["bounding"] = [-670, -2570, 620, 1040]
    for node in data["nodes"]:
        if node.get("type") == "XYUE_H3_StudioController":
            node["title"] = "全局生成控制器｜1-5阶段共享"
        elif node.get("type") == "XYUE_H3_GlobalLoRAManager":
            node["title"] = "全局 LoRA 管理｜1-5阶段统一"
        elif node.get("type") == "XYUE_H3_VideoConcat":
            node["title"] = "五段视频合成｜保存并预览最终成品"
            node["size"] = [1040, 760]
        elif node.get("type") == "XYUE_H3_StageFinish":
            node["title"] = "第五阶段｜流程完成"
    note = next((node for node in data["nodes"] if node.get("id") == 39), None)
    if note is not None:
        text = "每个阶段均为独立横向轨道，上一阶段尾帧作为下一阶段硬首帧；启用阶段数控制前 N 段，未启用阶段由续接节点惰性跳过。多段云端配置节点可统一覆盖提示词、阶段参数和全局加速。"
        note["properties"]["text"] = text
        note["widgets_values"][0] = text
    _reflow_layout(data)
    _set_stage_group_metadata(data)


def _normalize_workflow_layout(data: dict) -> None:
    """Keep one visual language without changing node wiring or widget values."""
    groups = data.get("groups") or []
    has_stage_lanes = any(node.get("type") == "XYUE_H3_StudioController" for node in data.get("nodes", []))
    if has_stage_lanes and len(groups) >= 2:
        groups[1]["title"] = "② 全局控制｜HQ 双段采样与 LoRA 管理"
        groups[1]["bounding"] = [-670, -2570, 620, 1040]
        _reflow_layout(data)
        _set_stage_group_metadata(data)
        return
    if len(groups) >= 4:
        groups[0]["title"] = "① 左侧素材与参考输入"
        groups[1]["title"] = "② 提示词横向编辑列"
        groups[2]["title"] = "③ 全局控制｜HQ 双段采样与 TE 加速"
        groups[2]["bounding"] = [-670, 430, 5240, 1010]
        groups[3]["title"] = "④ 右侧输出｜生成、保存与预览"


def _trim_workflow_to_stage_limit(data: dict) -> None:
    groups = data.get("groups") or []
    remove_group_indexes = {
        index for index, group in enumerate(groups)
        if group.get("properties", {}).get("xyue_group_role") == "stage"
        and int(group.get("properties", {}).get("xyue_stage_index", 0)) > MAX_STAGES
    }
    if not remove_group_indexes:
        return
    remove_ids: set[int] = set()
    for index in remove_group_indexes:
        group = groups[index]
        x, y, width, height = [float(value) for value in group.get("bounding", [0, 0, 0, 0])]
        for node in data.get("nodes", []):
            nx, ny = [float(value) for value in node.get("pos", [0, 0])[:2]]
            if x <= nx <= x + width and y <= ny <= y + height:
                remove_ids.add(int(node["id"]))

    data["nodes"] = [node for node in data["nodes"] if int(node["id"]) not in remove_ids]
    data["links"] = [link for link in data.get("links", []) if link[1] not in remove_ids and link[3] not in remove_ids]
    groups[:] = [group for index, group in enumerate(groups) if index not in remove_group_indexes]

    concat = next((node for node in data["nodes"] if node.get("type") == "XYUE_H3_VideoConcat"), None)
    if concat is not None:
        old_inputs = list(concat.get("inputs", []))
        keep_inputs = [item for item in old_inputs if not str(item.get("name", "")).startswith("stage") or int(str(item["name"])[5:-6]) <= MAX_STAGES]
        slot_map = {old: new for new, old in enumerate(index for index, item in enumerate(old_inputs) if item in keep_inputs)}
        concat["inputs"] = keep_inputs
        filtered_links = []
        for link in data["links"]:
            if link[3] == concat["id"]:
                if link[4] not in slot_map:
                    continue
                link = list(link)
                link[4] = slot_map[link[4]]
            filtered_links.append(link)
        data["links"] = filtered_links

    link_ids = {int(link[0]) for link in data["links"]}
    nodes = {int(node["id"]): node for node in data["nodes"]}
    for node in nodes.values():
        for item in node.get("inputs", []):
            if item.get("link") not in link_ids:
                item["link"] = None
        for output in node.get("outputs", []):
            output["links"] = [link for link in output.get("links", []) if link in link_ids]
    data.setdefault("extra", {})["xyue_h3_stage_slots"] = MAX_STAGES
    data["last_node_id"] = max((int(node["id"]) for node in data["nodes"]), default=0)
    data["last_link_id"] = max(link_ids, default=0)


def build() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    # Always rebuild from the checked-in multi-stage seed, so repeated runs do not
    # accumulate optional lanes.
    data["nodes"] = [node for node in data["nodes"] if int(node["id"]) <= 106]
    data["links"] = [link for link in data["links"] if int(link[0]) <= 129]
    data["groups"] = data["groups"][:6]
    link_ids = {link[0] for link in data["links"]}
    for node in data["nodes"]:
        for input_spec in node.get("inputs", []):
            if input_spec.get("link") not in link_ids:
                input_spec["link"] = None
        for output in node.get("outputs", []):
            output["links"] = [link for link in output.get("links", []) if link in link_ids]
    _assign_stage_metadata(data)
    stage2_ids = {
        int(node["id"]) for node in data["nodes"]
        if node.get("properties", {}).get("xyue_stage_index") == 2
    }
    stage3_ids = {
        int(node["id"]) for node in data["nodes"]
        if node.get("properties", {}).get("xyue_stage_index") == 3
    }
    if not stage2_ids:
        stage2_ids = _stage_ids(data, -700, -100)
    if not stage3_ids:
        stage3_ids = _stage_ids(data, 1000, 1700)
    next_node = max(int(node["id"]) for node in data["nodes"]) + 1
    stage3_extractor_id = next_node
    stage3_extractor = copy.deepcopy(_node(data, 27))
    stage3_extractor["id"] = stage3_extractor_id
    stage3_extractor["pos"] = [6400, 1600]
    stage3_extractor["title"] = "尾帧截取器｜第三阶段"
    _clear_links(stage3_extractor)
    data["nodes"].append(stage3_extractor)
    _append_link(data, [max(int(link[0]) for link in data["links"]) + 1, 51, 0, stage3_extractor_id, 0, "VIDEO"])
    next_node += 1
    mappings: dict[int, dict[int, int]] = {}
    stage_arguments = []
    for stage in range(4, MAX_STAGES + 1):
        source_ids = stage3_ids if stage == MAX_STAGES else stage2_ids
        mappings[stage] = {source_id: next_node + offset for offset, source_id in enumerate(sorted(source_ids))}
        next_node += len(source_ids)

    original_stage2 = {"generator": 26, "extractor": 27, "resume": 50}
    for stage in range(4, MAX_STAGES + 1):
        source_ids = stage3_ids if stage == MAX_STAGES else stage2_ids
        previous = 3 if stage == 4 else stage - 1
        previous_extractor = stage3_extractor_id if previous == 3 else mappings[previous][original_stage2["extractor"]]
        previous_resume = 51 if previous == 3 else mappings[previous][original_stage2["resume"]]
        stage_arguments.append((stage, source_ids, mappings[stage],
                                {19: previous_extractor, 27: previous_extractor, 48: previous_resume, 50: previous_resume},
                                {}))

    for stage, source_ids, mapping, external_sources, external_targets in stage_arguments:
        _clone_stage(data, source_ids, mapping, external_sources, external_targets, stage, write_links=False)
    for stage, source_ids, mapping, external_sources, external_targets in stage_arguments:
        _clone_stage(data, source_ids, mapping, external_sources, external_targets, stage, clone_nodes=False, update_metadata=False)

    _ensure_multistage_config(data)
    _update_layout(data)
    _ensure_video_board(data)
    _annotate_acceleration_modes(data)
    data["last_node_id"] = max(int(node["id"]) for node in data["nodes"])
    data["last_link_id"] = max(int(link[0]) for link in data["links"])
    data.setdefault("extra", {})["xyue_h3_stage_slots"] = MAX_STAGES
    output = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    SOURCE.write_text(output, encoding="utf-8")
    USER_COPY.write_text(output, encoding="utf-8")
    for path in sorted((ROOT / "workflows").glob("*.json")):
        if path == SOURCE:
            continue
        workflow = json.loads(path.read_text(encoding="utf-8-sig"))
        if sum(node.get("type") == "XYUE_H3_PromptEditor" for node in workflow.get("nodes", [])) > MAX_STAGES:
            _trim_workflow_to_stage_limit(workflow)
        _normalize_workflow_layout(workflow)
        if sum(node.get("type") == "XYUE_H3_PromptEditor" for node in workflow.get("nodes", [])) > 1:
            _ensure_multistage_config(workflow)
            _ensure_video_board(workflow)
            _set_stage_group_metadata(workflow)
            _annotate_acceleration_modes(workflow)
        serialized = json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"
        path.write_text(serialized, encoding="utf-8")
        (USER_WORKFLOW_DIR / path.name).write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    build()
