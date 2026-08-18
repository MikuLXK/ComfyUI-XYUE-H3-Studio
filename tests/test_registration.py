import json
from pathlib import Path


def test_workflows_are_valid_and_node_ids_are_unique():
    root = Path(__file__).parents[1]
    workflows = list((root / "workflows").glob("*.json"))
    assert len(workflows) == 8
    for path in workflows:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        node_types = [node["type"] for node in data["nodes"]]
        assert all(isinstance(node.get("mode"), int) for node in data["nodes"])
        assert len([node["id"] for node in data["nodes"]]) == len(set(node["id"] for node in data["nodes"]))
        link_ids = {link[0] for link in data["links"]}
        assert all(link_id in link_ids for node in data["nodes"] for output in node.get("outputs", []) for link_id in (output.get("links") or []))
        links = {link[0]: link for link in data["links"]}
        nodes = {node["id"]: node for node in data["nodes"]}
        for link_id, link in links.items():
            assert len(link) == 6
            source = nodes[link[1]]
            target = nodes[link[3]]
            assert link_id in (source["outputs"][link[2]].get("links") or [])
            assert target["inputs"][link[4]].get("link") == link_id
        for node in data["nodes"]:
            for slot, input_spec in enumerate(node.get("inputs", [])):
                link_id = input_spec.get("link")
                if link_id is None:
                    continue
                link = links[link_id]
                assert link[3] == node["id"]
                assert link[4] == slot
        allowed_external_nodes = {
            "SaveVideo", "TESpeedMiniMaxH3", "MiniMaxChunkFeedForward", "UniBlockSwap",
            "MiniMaxH3MemoryEfficientSageAttentionPatch", "MiniMaxLowVRAMAttention",
            "SolAttnPatch", "ModelPatchTorchSettings", "Note",
        }
        assert all(node_type.startswith("XYUE_H3_") or node_type in allowed_external_nodes for node_type in node_types)
        if "XYUE_H3_StudioController" in node_types:
            flow_groups = [
                group for group in data.get("groups", [])
                if group.get("properties", {}).get("xyue_group_role") == "stage_flow"
            ]
            assert len(flow_groups) == 1
            stage_indexes = {
                node.get("properties", {}).get("xyue_stage_index")
                for node in data["nodes"]
                if node.get("properties", {}).get("xyue_stage_index") is not None
            }
            assert stage_indexes == set(range(1, 6))
            acceleration_annotations = {
                mode
                for node in data["nodes"]
                for mode in node.get("properties", {}).get("xyue_acceleration_modes", [])
            }
            assert {"模式1", "模式2", "模式3"} <= acceleration_annotations
        assert "TESpeedMiniMaxH3" in node_types
        assert node_types.count("MiniMaxChunkFeedForward") == node_types.count("XYUE_H3_Generator") * 2
        expected_sage = node_types.count("XYUE_H3_Generator")
        if "XYUE_H3_GlobalAccelerationManager" in node_types:
            expected_sage *= 3
        assert node_types.count("MiniMaxH3MemoryEfficientSageAttentionPatch") == expected_sage
        assert node_types.count("MiniMaxLowVRAMAttention") == node_types.count("XYUE_H3_Generator") * 2
        assert node_types.count("SolAttnPatch") == node_types.count("XYUE_H3_Generator")
        if "XYUE_H3_GlobalAccelerationManager" in node_types:
            assert node_types.count("UniBlockSwap") == node_types.count("XYUE_H3_Generator")
        assert node_types.count("XYUE_H3_LoRASelector") == node_types.count("XYUE_H3_Generator") * 2
        assert node_types.count("XYUE_H3_AccelerationController") == node_types.count("XYUE_H3_Generator")
        assert node_types.count("ModelPatchTorchSettings") == node_types.count("XYUE_H3_Generator")
        assert len(data.get("groups", [])) >= 4
        if path.name == "XYUE_H3_多段循环工作流.json":
            assert node_types.count("XYUE_H3_ImageAsset") == 9
            assert node_types.count("XYUE_H3_VideoAsset") == 3
            assert node_types.count("XYUE_H3_AudioAsset") == 3
            assert node_types.count("XYUE_H3_Generator") == 5
            assert node_types.count("XYUE_H3_LastFrameExtractor") == 4
            assert node_types.count("XYUE_H3_StudioController") == 1
            assert node_types.count("XYUE_H3_GlobalLoRAManager") == 1
            assert node_types.count("XYUE_H3_GlobalAccelerationManager") == 1
            assert node_types.count("XYUE_H3_MultiStageConfig") == 1
            controller = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_StudioController")
            assert controller["widgets_values"][3:10] == [
                5, 12, 12, "简单稳定（推荐）", 0, "randomize", "适配生成画布（省显存）"
            ]
            assert len(controller["outputs"][0]["links"]) >= 3
            assert controller["widgets_values"][16] == 3
            global_lora = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_GlobalLoRAManager")
            assert global_lora["pos"][1] > controller["pos"][1]
            assert global_lora["widgets_values"][2:] == [1.0, False]
            assert len(global_lora["outputs"][0]["links"]) >= 5
            global_acceleration = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_GlobalAccelerationManager")
            assert global_acceleration["pos"][1] > global_lora["pos"][1]
            assert global_acceleration["widgets_values"] == ["不启用"]
            assert len(global_acceleration["outputs"][0]["links"]) == 10
            for controller in (node for node in data["nodes"] if node["type"] == "XYUE_H3_AccelerationController"):
                control_input = next(item for item in controller["inputs"] if item["name"] == "global_acceleration")
                assert control_input["link"] is not None
            assert node_types.count("XYUE_H3_StageCheckpointSave") == 5
            assert node_types.count("XYUE_H3_StageResume") == 5
            assert node_types.count("XYUE_H3_StageFinish") == 0
            assert node_types.count("XYUE_H3_VideoConcat") == 0
            assert node_types.count("XYUE_H3_VideoBoard") == 1
            audio_assets = [node for node in data["nodes"] if node["type"] == "XYUE_H3_AudioAsset"]
            assert all(node["widgets_values"][0] == "未选择音频" for node in audio_assets)
            assert [node["widgets_values"][4] for node in audio_assets] == ["角色A", "角色B", "旁白"]
        if path.name == "XYUE_H3_全程多参考短剧工作流.json":
            assert node_types.count("XYUE_H3_ImageAsset") == 9
            assert node_types.count("XYUE_H3_VideoAsset") == 3
            assert node_types.count("XYUE_H3_AudioAsset") == 3
            assert node_types.count("XYUE_H3_ContinuationReference") == 4
            assert node_types.count("XYUE_H3_Generator") == 5
            assert node_types.count("XYUE_H3_LastFrameExtractor") == 5
            assert node_types.count("XYUE_H3_StudioController") == 1
            assert node_types.count("XYUE_H3_GlobalLoRAManager") == 1
            assert node_types.count("XYUE_H3_GlobalAccelerationManager") == 1
            assert node_types.count("XYUE_H3_MultiStageConfig") == 1
            controller = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_StudioController")
            assert controller["widgets_values"][3:10] == [
                5, 12, 12, "简单稳定（推荐）", 0, "randomize", "适配生成画布（省显存）"
            ]
            assert len(controller["outputs"][0]["links"]) >= 3
            assert controller["widgets_values"][11] == 3
            global_lora = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_GlobalLoRAManager")
            assert global_lora["pos"][1] > controller["pos"][1]
            assert global_lora["widgets_values"][2:] == [1.0, True]
            assert len(global_lora["outputs"][0]["links"]) >= 3
            global_acceleration = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_GlobalAccelerationManager")
            assert global_acceleration["pos"][1] > global_lora["pos"][1]
            assert global_acceleration["widgets_values"] == ["不启用"]
            assert len(global_acceleration["outputs"][0]["links"]) == 10
            for controller in (node for node in data["nodes"] if node["type"] == "XYUE_H3_AccelerationController"):
                control_input = next(item for item in controller["inputs"] if item["name"] == "global_acceleration")
                assert control_input["link"] is not None
            assert node_types.count("XYUE_H3_StageCheckpointSave") == 5
            assert node_types.count("XYUE_H3_StageResume") == 5
            assert node_types.count("XYUE_H3_StageFinish") == 0
            assert node_types.count("XYUE_H3_VideoConcat") == 0
            assert node_types.count("XYUE_H3_VideoBoard") == 1
            selectors = [node for node in data["nodes"] if node["type"] == "XYUE_H3_ModeModelSelector"]
            assert all(node["widgets_values"][0] == "多参考模式" for node in selectors)
            continuation_nodes = [node for node in data["nodes"] if node["type"] == "XYUE_H3_ContinuationReference"]
            assert all(node["widgets_values"][0] == "自动追加，9 图时替换最后启用图片（推荐）" for node in continuation_nodes)
            audio_assets = [node for node in data["nodes"] if node["type"] == "XYUE_H3_AudioAsset"]
            assert all(node["widgets_values"][0] == "未选择音频" for node in audio_assets)
            notes = "\n".join(node["widgets_values"][0] for node in data["nodes"] if node["type"] == "Note")
            assert "物理槽位 1、3、6" in notes
            assert "尾帧追加为 <Picture 4>，不会替换槽位 6" in notes
            assert "1 张原图时占 <Picture 2>，8 张原图时占 <Picture 9>" in notes
        for selector in (node for node in data["nodes"] if node["type"] == "XYUE_H3_ModeModelSelector"):
            assert all(selector["widgets_values"][index] for index in range(1, 6))
        for image_asset in (node for node in data["nodes"] if node["type"] == "XYUE_H3_ImageAsset"):
            assert image_asset["widgets_values"][0] == "未选择图片"
            assert image_asset["widgets_values"][3] == "未指定"
        for video_asset in (node for node in data["nodes"] if node["type"] == "XYUE_H3_VideoAsset"):
            assert video_asset["widgets_values"][0] == "未选择视频"
        for profile in (node for node in data["nodes"] if node["type"] == "XYUE_H3_GenerationProfile"):
            assert profile["widgets_values"][1].startswith("768p")
            assert profile["widgets_values"][2:9] == [
                5, 12, 12, "简单稳定（推荐）", 0, "randomize", "适配生成画布（省显存）"
            ]
            assert len(profile["widgets_values"]) == 15
            assert profile["widgets_values"][9:15] == ["快速单次（推荐）", "单次采样", 2, 1.0, False, 0]
        for profile in (node for node in data["nodes"] if node["type"] == "XYUE_H3_StageGenerationProfile"):
            assert profile["widgets_values"][2:9] == [
                5, 12, 12, "简单稳定（推荐）", 0, "randomize", "适配生成画布（省显存）"
            ]
            if len(profile["widgets_values"]) == 16:
                assert profile["widgets_values"][15] in (
                    "第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段",
                    "第六阶段", "第七阶段", "第八阶段", "第九阶段", "第十阶段",
                )
            else:
                assert len(profile["widgets_values"]) == 11
                assert profile["widgets_values"][10] in (
                "第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段",
                "第六阶段", "第七阶段", "第八阶段", "第九阶段", "第十阶段",
                )
        for controller in (node for node in data["nodes"] if node["type"] == "XYUE_H3_StudioController"):
            if len(controller["widgets_values"]) == 17:
                assert controller["widgets_values"][16] == 3
            else:
                assert len(controller["widgets_values"]) == 12
                assert controller["widgets_values"][10:12] == ["快速单次（推荐）", 3]
        for lora in (node for node in data["nodes"] if node["type"] == "XYUE_H3_LoRASelector"):
            assert lora["widgets_values"] in [
                    [r"minimax_h3\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 1.0],
                    [r"minimax_h3\minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors", 1.0],
                    ["不使用 LoRA", 1.0],
            ]
        for speed in (node for node in data["nodes"] if node["type"] == "TESpeedMiniMaxH3"):
            assert speed["widgets_values"][:5] == [0.08, 0.1, 0.9, 2, "auto"]
            assert speed["widgets_values"][5] in ("8-step LoRA", "4-step LoRA", "standard")
        for chunk in (node for node in data["nodes"] if node["type"] == "MiniMaxChunkFeedForward"):
            assert chunk["widgets_values"] in ([2, 4096], [4, 4096])
        for low_vram in (node for node in data["nodes"] if node["type"] == "MiniMaxLowVRAMAttention"):
            assert low_vram["widgets_values"] in ([4], [10])
        assert all(node["size"][0] >= 700 for node in data["nodes"] if node["type"] == "XYUE_H3_ModeModelSelector")
        for generator in (node for node in data["nodes"] if node["type"] == "XYUE_H3_Generator"):
            accelerated = next(item for item in generator["inputs"] if item["name"] == "accelerated_model")
            controller_link = links[accelerated["link"]]
            acceleration = nodes[controller_link[1]]
            assert acceleration["type"] == "XYUE_H3_AccelerationController"
            assert acceleration["widgets_values"] == [False]
            if "XYUE_H3_GlobalAccelerationManager" in node_types:
                hq = next(item for item in acceleration["inputs"] if item["name"] == "hq_model")
                assert nodes[links[hq["link"]][1]]["type"] == "UniBlockSwap"
            original = next(item for item in acceleration["inputs"] if item["name"] == "original_model")
            accelerated_branch = next(item for item in acceleration["inputs"] if item["name"] == "accelerated_model")
            assert nodes[links[original["link"]][1]]["type"] == "XYUE_H3_ModeModelSelector"
            assert nodes[links[accelerated_branch["link"]][1]]["type"] == "SolAttnPatch"
        if "短剧" in path.name:
            saves = {node["title"].split("｜", 1)[0]: node for node in data["nodes"] if node["type"] == "XYUE_H3_StageCheckpointSave"}
            assert saves["第一阶段"]["pos"][1] < saves["第二阶段"]["pos"][1] < saves["第三阶段"]["pos"][1]
            board = next(node for node in data["nodes"] if node["type"] == "XYUE_H3_VideoBoard")
            assert board["pos"][0] >= 7000
            assert board["properties"]["xyue_video_board_layout"] == "3x2"
        for editor in (node for node in data["nodes"] if node["type"] == "XYUE_H3_PromptEditor"):
            prompt = editor["widgets_values"][2]
            assert "\\n" not in prompt
            assert "\n\n" in prompt
        editors = sorted((node for node in data["nodes"] if node["type"] == "XYUE_H3_PromptEditor"), key=lambda node: node["pos"][1])
        enhancers = sorted((node for node in data["nodes"] if node["type"] == "XYUE_H3_PromptEnhancer"), key=lambda node: node["pos"][1])
        if len(editors) > 1:
            assert [node["widgets_values"][3] for node in editors] == list(range(1, len(editors) + 1))
            assert [node["widgets_values"][4] for node in enhancers] == list(range(1, len(enhancers) + 1))
        assert "api_key" not in path.read_text(encoding="utf-8-sig").lower()


def test_full_reference_drama_stage_chains_are_consistent():
    path = Path(__file__).parents[1] / "workflows" / "XYUE_H3_全程多参考短剧工作流.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    links = {link[0]: link for link in data["links"]}
    nodes = {node["id"]: node for node in data["nodes"]}
    generators = sorted(
        (node for node in data["nodes"] if node["type"] == "XYUE_H3_Generator"),
        key=lambda node: node["properties"]["xyue_stage_index"],
    )

    assert [node["properties"]["xyue_stage_index"] for node in generators] == list(range(1, 6))
    assert not any(
        "xyue_h3_auto_mode_state" in node.get("properties", {})
        for node in data["nodes"]
    )
    for generator in generators:
        stage = generator["properties"]["xyue_stage_index"]
        for input_name in ("model_profile", "generation_profile", "prompt", "accelerated_model"):
            input_spec = next(item for item in generator["inputs"] if item["name"] == input_name)
            source = nodes[links[input_spec["link"]][1]]
            assert source["properties"]["xyue_stage_index"] == stage


def test_plugin_registers_upload_controller_and_checkpoint_nodes():
    import asyncio
    import importlib.util
    import sys

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("xyue_h3_registration", root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    extension = asyncio.run(module.comfy_entrypoint())
    classes = asyncio.run(extension.get_node_list())
    schemas = {node.GET_SCHEMA().node_id: node.GET_SCHEMA() for node in classes}

    required = {
        "XYUE_H3_AudioAsset",
        "XYUE_H3_LoRASelector",
        "XYUE_H3_GlobalLoRAManager",
        "XYUE_H3_GlobalAccelerationManager",
        "XYUE_H3_AccelerationController",
        "XYUE_H3_StudioController",
        "XYUE_H3_StageGenerationProfile",
        "XYUE_H3_StageCheckpointSave",
        "XYUE_H3_StageResume",
        "XYUE_H3_StageFinish",
        "XYUE_H3_MultiStageConfig",
        "XYUE_H3_VideoBoard",
    }
    assert required <= schemas.keys()
    acceleration = schemas["XYUE_H3_AccelerationController"]
    assert acceleration.inputs[0].id == "enabled"
    assert acceleration.inputs[0].default is False
    assert acceleration.inputs[1].lazy is True
    assert acceleration.inputs[1].optional is True
    assert acceleration.inputs[2].lazy is True
    assert acceleration.inputs[2].optional is True
    assert acceleration.inputs[3].id == "hq_model"
    assert acceleration.inputs[3].lazy is True
    assert acceleration.inputs[3].optional is True
    assert acceleration.inputs[4].id == "experimental_model"
    assert acceleration.inputs[4].lazy is True
    assert acceleration.inputs[4].optional is True
    assert acceleration.inputs[5].id == "global_acceleration"
    assert acceleration.inputs[5].optional is True
    global_acceleration = schemas["XYUE_H3_GlobalAccelerationManager"]
    assert global_acceleration.inputs[0].id == "mode"
    assert global_acceleration.inputs[0].default == "不启用"
    multi_stage = schemas["XYUE_H3_MultiStageConfig"]
    assert multi_stage.inputs[0].id == "config_text"
    global_lora = schemas["XYUE_H3_GlobalLoRAManager"]
    assert global_lora.inputs[0].id == "enabled"
    assert global_lora.inputs[1].id == "lora_name"
    assert global_lora.inputs[2].default == 1.0
    assert global_lora.inputs[3].default is False
    audio = schemas["XYUE_H3_AudioAsset"].inputs[0]
    assert audio.id == "audio"
    assert audio.upload.value == "audio_upload"

    controller = schemas["XYUE_H3_StudioController"]
    assert controller.inputs[0].id == "global_enabled"
    assert controller.inputs[0].default is True
    stage = schemas["XYUE_H3_StageGenerationProfile"]
    assert stage.inputs[0].id == "studio_control"
    prompt_editor = schemas["XYUE_H3_PromptEditor"]
    assert next(item for item in prompt_editor.inputs if item.id == "stage_index").default == 1
    generation = schemas["XYUE_H3_GenerationProfile"]
    generation_inputs = {input_spec.id: input_spec for input_spec in generation.inputs}
    assert generation_inputs["duration"].default == 5
    assert generation_inputs["steps"].default == 12
    assert generation_inputs["steps"].io_type == "INT"
    assert generation_inputs["audio_steps"].default == 12
    assert generation_inputs["seed"].default == 0
    assert generation_inputs["seed"].control_after_generate is True
    assert generation_inputs["sampling_preset"].default == "快速单次（推荐）"
    assert not {"sampling_mode", "coarse_steps", "upscale_factor", "refine_pass", "extend_sigmas"} & generation_inputs.keys()
    studio_inputs = {input_spec.id: input_spec for input_spec in controller.inputs}
    assert studio_inputs["sampling_preset"].default == "快速单次（推荐）"
    assert not {"sampling_mode", "coarse_steps", "upscale_factor", "refine_pass", "extend_sigmas"} & studio_inputs.keys()
    stage_inputs = {input_spec.id: input_spec for input_spec in stage.inputs}
    assert not {"sampling_mode", "coarse_steps", "upscale_factor", "refine_pass", "extend_sigmas"} & stage_inputs.keys()

    assets = sys.modules[f"{spec.name}.nodes.assets"]
    assert assets.XYUEH3ImageAsset.validate_inputs(
        assets.NO_IMAGE_SELECTED, False, "@文件名", "未指定", "保持原图"
    ) is True
    assert assets.XYUEH3VideoAsset.validate_inputs(
        assets.NO_VIDEO_SELECTED, False, "@文件名", "动作节奏样片", 0, 0, False
    ) is True
    assert assets.XYUEH3AudioAsset.validate_inputs(
        assets.NO_AUDIO_SELECTED, False, "@文件名", "角色声纹锚点", "角色A", 0, 0, 0, False
    ) is True
