from core.aggregate_workflow import (
    _tail_extractors_by_target_stage,
    _validate_plan,
    _wire_stage_inputs,
    build_aggregate_workflow,
    load_workflow,
)


def test_aggregate_tail_extractors_follow_previous_stage_video():
    workflow = load_workflow("全程多参考短剧")
    extractors = _tail_extractors_by_target_stage(workflow)
    nodes = {str(node["id"]): node for node in workflow["nodes"]}
    links = {int(link[0]): link for link in workflow["links"]}

    assert set(extractors) >= {2, 3, 4, 5}
    for target_stage in range(2, 6):
        extractor = extractors[target_stage]
        video_input = next(item for item in extractor["inputs"] if item["name"] == "video")
        source = nodes[str(links[int(video_input["link"])][1])]
        assert int(source["properties"]["xyue_stage_index"]) == target_stage - 1


def test_aggregate_accepts_one_second_stage():
    plan = {
        "schema": "xyue-h3/aggregate-workflow-config-v2",
        "stage_count": 1,
        "prompts": ["prompt"],
        "durations": [1],
        "transitions": ["cut"],
        "acceleration_modes": ["不启用"],
        "models": [{"mode": "文生视频模式"}],
        "generation": {"stages": [{}]},
    }
    assert _validate_plan(plan)[1] == [1]


def test_aggregate_tail_inputs_are_previous_stage_video_tails():
    workflow = load_workflow("全程多参考短剧")
    models = [{"mode": "文生视频模式"}] + [{"mode": "首帧生视频模式"}] * 4
    _wire_stage_inputs(workflow, ["cut", "tail", "tail", "tail", "tail"], models)

    nodes = {str(node["id"]): node for node in workflow["nodes"]}
    links = {int(link[0]): link for link in workflow["links"]}
    generators = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_Generator"
    }
    prompt_editors = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_PromptEditor"
    }
    for target_stage in range(2, 6):
        first_frame = next(item for item in generators[target_stage]["inputs"] if item["name"] == "first_frame")
        source = nodes[str(links[int(first_frame["link"])][1])]
        source_video = next(item for item in source["inputs"] if item["name"] == "video")
        previous = nodes[str(links[int(source_video["link"])][1])]
        assert int(previous["properties"]["xyue_stage_index"]) == target_stage - 1
        mention_registry = next(
            item for item in prompt_editors[target_stage]["inputs"] if item["name"] == "mention_registry"
        )
        assert mention_registry.get("link") is None


def test_aggregate_tail_ref2va_uses_previous_tail_as_material_reference():
    workflow = load_workflow("全程多参考短剧")
    models = [{"mode": "多参考模式"}] * 5
    _wire_stage_inputs(workflow, ["cut", "tail", "tail", "tail", "tail"], models)

    nodes = {str(node["id"]): node for node in workflow["nodes"]}
    links = {int(link[0]): link for link in workflow["links"]}
    generators = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_Generator"
    }
    continuations = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_ContinuationReference"
    }
    prompt_editors = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_PromptEditor"
    }
    for target_stage in range(2, 6):
        continuation_frame = next(
            item for item in continuations[target_stage]["inputs"] if item["name"] == "continuation_frame"
        )
        extractor = nodes[str(links[int(continuation_frame["link"])][1])]
        source_video = next(item for item in extractor["inputs"] if item["name"] == "video")
        previous = nodes[str(links[int(source_video["link"])][1])]
        assert int(previous["properties"]["xyue_stage_index"]) == target_stage - 1
        assert continuations[target_stage]["widgets_values"][1] == "尾帧"
        mention_registry = next(
            item for item in prompt_editors[target_stage]["inputs"] if item["name"] == "mention_registry"
        )
        registry_source = nodes[str(links[int(mention_registry["link"])][1])]
        assert registry_source["id"] == continuations[target_stage]["id"]
        first_frame = next(item for item in generators[target_stage]["inputs"] if item["name"] == "first_frame")
        assert first_frame.get("link") is None


def test_aggregate_cut_ref2va_does_not_use_continuation_reference():
    workflow = load_workflow("全程多参考短剧")
    _wire_stage_inputs(workflow, ["cut"] * 5, [{"mode": "多参考模式"}] * 5)
    generators = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_Generator"
    }
    links = {int(link[0]): link for link in workflow["links"]}
    nodes = {str(node["id"]): node for node in workflow["nodes"]}
    prompt_editors = {
        int(node["properties"]["xyue_stage_index"]): node
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_PromptEditor"
    }
    for stage in range(2, 6):
        material = next(item for item in generators[stage]["inputs"] if item["name"] == "material_pack")
        source = nodes[str(links[int(material["link"])][1])]
        assert source["type"] == "XYUE_H3_MaterialManager"
        mention_registry = next(
            item for item in prompt_editors[stage]["inputs"] if item["name"] == "mention_registry"
        )
        registry_source = nodes[str(links[int(mention_registry["link"])][1])]
        assert registry_source["type"] == "XYUE_H3_MaterialManager"


def test_aggregate_build_removes_cloud_config_node(monkeypatch):
    from tools import configure_multi_stage_workflow

    monkeypatch.setattr(configure_multi_stage_workflow, "validate_model_files", lambda models: [])
    prompt = (
        "integrated_multimodal_description: [Shot 1] A sword cultivator raises her blade.\n\n"
        "overall_soundscape: Wind crosses the stone platform.\n\n"
        "non_diegetic_music: Sparse guqin notes."
    )
    plan = {
        "schema": "xyue-h3/aggregate-workflow-config-v2",
        "workflow": "全程多参考短剧",
        "stage_count": 1,
        "stage_titles": ["云海问剑"],
        "prompts": [prompt],
        "durations": [5],
        "transitions": ["cut"],
        "acceleration_modes": ["模式2"],
        "models": [{
            "mode": "文生视频模式",
            "base_model": "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "reference_model": "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors",
            "language_model": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "video_vae": "minimax_h3_video_vae_fp16.safetensors",
            "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
            "latent_upscale_model": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "tiny_vae": "none",
        }],
        "generation": {
            "global_enabled": False,
            "stages": [{
                "aspect": "16:9",
                "resolution": "480p（864×480）",
                "duration": 9,
                "steps": 12,
                "audio_steps": 12,
                "scheduler": "简单稳定（推荐）",
                "seed": 0,
                "seed_control": "randomize",
                "reference_size": "适配生成画布（省显存）",
                "sampling": {"sampling_preset": "快速单次（推荐）"},
            }],
        },
    }

    workflow, _ = build_aggregate_workflow(plan)
    assert all(node["type"] != "XYUE_H3_MultiStageConfig" for node in workflow["nodes"])
    assert all(
        input_item.get("link") is None
        for node in workflow["nodes"]
        for input_item in node.get("inputs", [])
        if input_item.get("name") == "multi_stage_config"
    )
    profile = next(
        node for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_StageGenerationProfile"
        and int((node.get("properties") or {}).get("xyue_stage_index") or 0) == 1
    )
    assert profile["widgets_values"][2] == 5
    selector = next(
        node for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_ModeModelSelector"
        and int((node.get("properties") or {}).get("xyue_stage_index") or 0) == 1
    )
    assert selector["widgets_values"][6:8] == [
        "minimax_h3_latent_upscaler_3d_fp16.safetensors",
        "none",
    ]
