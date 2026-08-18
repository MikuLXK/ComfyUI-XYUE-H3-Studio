import json
from pathlib import Path

import pytest

from tools.configure_multi_stage_workflow import (
    _set_material_overrides,
    configure_api_prompt,
    configure_unified_workflow,
    configure_workflow,
    inspect_models,
    inspect_materials,
    inspect_sampling,
    lint_prompts,
    list_available_models,
    validate_lora_files,
    validate_model_files,
    validate_mode_plan,
)

from core.generation_options import resolve_sampling, sampler_for_acceleration
from core.contracts import normalize_acceleration_mode
from core.multi_stage_config import parse_multi_stage_config, stage_values


def test_multi_stage_prompts_and_durations_are_written_independently():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(workflow, ["prompt one", "prompt two", "prompt three"], [7, 4, 9])

    assert next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_StudioController")["widgets_values"][0] is False
    editors = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEditor"),
        key=lambda node: node["pos"][1],
    )[:3]
    profiles = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_StageGenerationProfile"),
        key=lambda node: node["pos"][1],
    )[:3]
    enhancers = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEnhancer"),
        key=lambda node: node["pos"][1],
    )[:3]
    assert [node["widgets_values"][1] for node in editors] == [7.0, 4.0, 9.0]
    assert [node["widgets_values"][2] for node in editors] == ["prompt one", "prompt two", "prompt three"]
    assert [node["widgets_values"][1] for node in enhancers] == [7.0, 4.0, 9.0]
    assert [node["widgets_values"][2] for node in profiles] == [7, 4, 9]


def test_multi_stage_duration_accepts_full_one_to_fifteen_range():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(workflow, ["one", "two", "three"], [1, 8, 15])
    editors = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEditor"),
        key=lambda node: node["pos"][1],
    )[:3]
    assert [node["widgets_values"][1] for node in editors] == [1.0, 8.0, 15.0]


def test_multi_stage_duration_reasons_are_preserved_as_metadata():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    reasons = ["建立场景", "快速反应", "完成收束"]
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [7, 4, 9],
        duration_reasons=reasons,
    )

    assert configured["extra"]["xyue_h3_multi_stage"]["duration_reasons"] == reasons


def test_multi_stage_resume_marks_previous_stages():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [5, 5, 5],
        start_stage=3,
        resume_files=["stage1.mp4", "stage2.mp4"],
    )
    order = {"第一阶段": 1, "第二阶段": 2, "第三阶段": 3}
    resumes = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_StageResume" and any(label in node["title"] for label in order)),
        key=lambda node: next(value for label, value in order.items() if label in node["title"]),
    )
    assert [node["widgets_values"][3] for node in resumes] == [True, True, False]
    assert [node["widgets_values"][1] for node in resumes[:2]] == ["stage1.mp4", "stage2.mp4"]


def test_stage_count_is_written_to_global_controller():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(workflow, ["one", "two", "three"], [5, 5, 5], stage_count=2)
    controller = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_StudioController")
    assert controller["widgets_values"][11] == 2
    assert configured["extra"]["xyue_h3_multi_stage"]["stage_count"] == 2


def test_five_stage_plan_configures_all_prebuilt_lanes():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    prompts = [f"stage {index}" for index in range(1, 6)]
    configured = configure_workflow(workflow, prompts, list(range(1, 6)), stage_count=5)

    controller = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_StudioController")
    editors = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEditor"),
        key=lambda node: node["pos"][1],
    )
    assert controller["widgets_values"][11] == 5
    assert [node["widgets_values"][2] for node in editors] == prompts
    assert len([node for node in configured["nodes"] if node["type"] == "XYUE_H3_StageResume"]) == 5


def test_workflow_material_inspection_distinguishes_selected_and_enabled():
    workflow = {
        "nodes": [
            {"id": 1, "type": "XYUE_H3_ImageAsset", "title": "图片 1", "widgets_values": ["hero.png", True]},
            {"id": 2, "type": "XYUE_H3_ImageAsset", "title": "图片 2", "widgets_values": ["scene.png", False]},
            {"id": 3, "type": "XYUE_H3_ImageAsset", "title": "图片 3", "widgets_values": ["未选择图片", True]},
        ]
    }
    report = inspect_materials(workflow)

    assert report["selected_counts"]["image"] == 2
    assert report["active_counts"]["image"] == 1
    assert report["entries"][0]["execution_index"] == 1
    assert report["entries"][1]["execution_index"] is None
    assert report["entries"][2]["imported"] is False


def test_material_override_imports_and_enables_selected_physical_slot():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [6, 6, 5],
        material_overrides=[{
            "kind": "image",
            "slot": 1,
            "file": "adult_reference.png",
            "enabled": True,
            "alias_mode": "@图片N",
            "role": "角色定妆图",
            "fit_mode": "保持原图",
        }],
    )
    first_image = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_ImageAsset")
    report = inspect_materials(configured)

    assert first_image["widgets_values"] == ["adult_reference.png", True, "@图片N", "角色定妆图", "保持原图"]
    assert report["active_counts"]["image"] == 1
    assert report["entries"][0]["execution_index"] == 1


def test_material_override_uses_manager_slot_order_not_array_order():
    workflow = {
        "nodes": [
            {"id": 3, "type": "XYUE_H3_ImageAsset", "widgets_values": ["未选择图片", False, "@文件名", "未指定", "保持原图"]},
            {"id": 1, "type": "XYUE_H3_ImageAsset", "widgets_values": ["未选择图片", False, "@文件名", "未指定", "保持原图"]},
            {"id": 2, "type": "XYUE_H3_ImageAsset", "widgets_values": ["未选择图片", False, "@文件名", "未指定", "保持原图"]},
            {"id": 9, "type": "XYUE_H3_ImageManager", "inputs": [
                {"name": "image_1", "link": 11},
                {"name": "image_2", "link": 12},
                {"name": "image_3", "link": 13},
            ]},
        ],
        "links": [
            [11, 1, 0, 9, 0, "XYUE_H3_IMAGE_ITEM"],
            [12, 2, 0, 9, 1, "XYUE_H3_IMAGE_ITEM"],
            [13, 3, 0, 9, 2, "XYUE_H3_IMAGE_ITEM"],
        ],
    }

    _set_material_overrides(
        workflow,
        [{"kind": "image", "slot": 1, "file": "hero.png", "enabled": True, "role": "角色定妆图"}],
    )

    by_id = {
        node["id"]: node["widgets_values"]
        for node in workflow["nodes"]
        if node["type"] == "XYUE_H3_ImageAsset"
    }
    assert by_id[1][0] == "hero.png"
    assert by_id[1][1] is True
    assert by_id[3][0] == "未选择图片"
    assert by_id[3][1] is False


def test_material_inspection_supports_all_nine_image_slots():
    workflow = {
        "nodes": [
            {
                "id": index,
                "type": "XYUE_H3_ImageAsset",
                "title": f"图片 {index}",
                "widgets_values": [f"image-{index}.png", True],
            }
            for index in range(1, 10)
        ]
    }

    report = inspect_materials(workflow)

    assert report["active_counts"]["image"] == 9
    assert [entry["execution_index"] for entry in report["entries"]] == list(range(1, 10))


def test_generation_and_acceleration_overrides_are_applied_explicitly():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [7, 4, 9],
        generation={
            "global_enabled": False,
            "stages": [
                {"steps": 8, "audio_steps": 10},
                {"steps": 12, "audio_steps": 12},
                {"steps": 16, "audio_steps": 14},
            ],
        },
        acceleration={
            "enabled": True,
            "global_mode": "模式1",
            "lora": {"enabled": True, "name": "minimax_h3\\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength": 0.75},
        },
    )
    profiles = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_StageGenerationProfile"),
        key=lambda node: node["pos"][1],
    )[:3]
    controllers = [node for node in configured["nodes"] if node["type"] == "XYUE_H3_AccelerationController"]
    lora = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_GlobalLoRAManager")
    manager = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_GlobalAccelerationManager")

    assert [(node["widgets_values"][3], node["widgets_values"][4]) for node in profiles] == [(8, 10), (12, 12), (16, 14)]
    assert all(node["widgets_values"] == [True] for node in controllers)
    assert lora["widgets_values"][:3] == [True, "minimax_h3\\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 0.75]
    assert manager["widgets_values"] == ["模式1"]


def test_te_settings_are_applied_to_all_stage_speed_nodes():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [5, 5, 5],
        acceleration={
            "enabled": True,
            "global_mode": "模式1",
            "te": {
                "processing_control_value": 0.05,
                "processing_percent_1": 0.2,
                "processing_percent_2": 0.85,
                "mcs": 3,
                "device": "auto",
                "mode": "4-step LoRA",
            },
        },
    )

    speed_nodes = [node for node in configured["nodes"] if node["type"] == "TESpeedMiniMaxH3"]
    assert len(speed_nodes) == 10
    assert all(node["widgets_values"] == [0.05, 0.2, 0.85, 3, "auto", "4-step LoRA"] for node in speed_nodes)


def test_stage_specific_lora_and_te_are_applied():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [5, 5, 5],
        acceleration={
            "enabled": True,
            "global_mode": "不启用",
            "stages": [
                {
                    "lora": {"name": r"minimax_h3\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors", "strength": 0.8},
                    "te": {"mode": "4-step LoRA", "mcs": 2},
                },
                {
                    "lora": {"name": r"minimax_h3\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength": 0.75},
                    "te": {"mode": "8-step LoRA", "mcs": 3},
                },
                {
                    "lora": {"name": "不使用 LoRA", "strength": 0.0},
                    "te": {"mode": "standard", "mcs": 1},
                },
            ],
        },
    )

    selectors = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_LoRASelector" and "模式3" not in node.get("title", "")),
        key=lambda node: node["pos"][1],
    )
    speed_nodes = sorted(
        (node for node in configured["nodes"] if node["type"] == "TESpeedMiniMaxH3" and "模式3" not in node.get("title", "")),
        key=lambda node: node["pos"][1],
    )
    manager = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_GlobalLoRAManager")

    selector_names = [node["widgets_values"][0] for node in selectors]
    assert r"minimax_h3\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" in selector_names
    assert r"minimax_h3\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" in selector_names
    assert "不使用 LoRA" in selector_names
    speed_modes = [node["widgets_values"][5] for node in speed_nodes]
    speed_mcs = [node["widgets_values"][3] for node in speed_nodes]
    assert all(speed_modes.count(mode) >= 1 for mode in ("4-step LoRA", "8-step LoRA", "standard"))
    assert all(speed_mcs.count(value) >= 1 for value in (1, 2, 3))
    assert manager["widgets_values"][0] is False

    api_prompt = {
        str(node["id"]): {"class_type": node["type"], "inputs": {}}
        for node in [*selectors, *speed_nodes]
    }
    result = configure_api_prompt(api_prompt, configured)
    lora_names = [item["inputs"]["lora_name"] for item in result.values() if item["class_type"] == "XYUE_H3_LoRASelector"]
    te_modes = [item["inputs"]["mode"] for item in result.values() if item["class_type"] == "TESpeedMiniMaxH3"]
    assert lora_names[0] == r"minimax_h3\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"
    assert all(te_modes.count(mode) >= 1 for mode in ("4-step LoRA", "8-step LoRA", "standard"))


def test_api_prompt_receives_configured_prompts_durations_and_acceleration():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [7, 4, 9],
        acceleration={
            "enabled": True,
            "global_mode": "不启用",
            "te": {"mode": "8-step LoRA", "mcs": 2},
        },
    )
    editors = [node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEditor"][:3]
    controllers = [node for node in configured["nodes"] if node["type"] == "XYUE_H3_AccelerationController"]
    manager = [node for node in configured["nodes"] if node["type"] == "XYUE_H3_GlobalAccelerationManager"]
    speed_nodes = [node for node in configured["nodes"] if node["type"] == "TESpeedMiniMaxH3"]
    api_prompt = {
        str(node["id"]): {"class_type": node["type"], "inputs": {}}
        for node in [*editors, *controllers, *manager, *speed_nodes]
    }

    result = configure_api_prompt(api_prompt, configured)
    editor_values = sorted(
        ((item["inputs"]["duration"], item["inputs"]["draft"]) for item in result.values() if item["class_type"] == "XYUE_H3_PromptEditor"),
        key=lambda item: item[0],
    )
    assert editor_values == [(4.0, "two"), (7.0, "one"), (9.0, "three")]
    assert all(item["inputs"]["enabled"] is True for item in result.values() if item["class_type"] == "XYUE_H3_AccelerationController")
    manager_values = [item["inputs"]["mode"] for item in result.values() if item["class_type"] == "XYUE_H3_GlobalAccelerationManager"]
    assert manager_values == ["不启用"]
    te_modes = [item["inputs"]["mode"] for item in result.values() if item["class_type"] == "TESpeedMiniMaxH3"]
    assert len(te_modes) == 10
    assert te_modes.count("standard") == 5


def test_inspect_models_reports_per_stage_model_selection():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    report = inspect_models(workflow)

    assert len(report) == 5
    assert {"mode", "base_model", "reference_model", "language_model", "video_vae", "audio_vae"} <= set(report[0])


def test_validate_model_files_detects_missing_and_accepts_existing():
    root = Path(__file__).parents[1]
    existing = "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors"
    missing = validate_model_files([{"reference_model": "definitely_missing.safetensors"}, {}, {}])
    assert len(missing) == 1
    clean = validate_model_files([{"reference_model": existing}, {}, {}])
    assert clean == []


def test_list_available_models_lists_diffusion_text_vae_and_loras():
    available = list_available_models()
    assert "diffusion_models" in available and "loras" in available
    assert any("ref2va" in name for name in available["diffusion_models"])
    assert any("minimax_h3" in name for name in available["loras"])


def test_validate_lora_files_rejects_missing_and_accepts_existing():
    missing = validate_lora_files({
        "stages": [{"lora": {"name": "nope/missing.safetensors"}}, {}, {}],
    })
    assert len(missing) == 1
    clean = validate_lora_files({
        "stages": [{"lora": {"name": "minimax_h3\\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"}}, {}, {}],
    })
    assert clean == []
    assert validate_lora_files({"stages": [{"lora": {"name": "不使用 LoRA"}}, {}, {}]}) == []


def test_validate_mode_plan_flags_workflow_mismatch():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    warnings = validate_mode_plan([{"mode": "多参考模式"}] * 3, workflow, None)
    assert len(warnings) == 2
    assert validate_mode_plan(
        [{"mode": "多参考模式"}, {"mode": "首帧生视频模式"}, {"mode": "首帧生视频模式"}],
        workflow,
        None,
    ) == []


def test_lint_prompts_accepts_natural_language_and_checks_references():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    issues = lint_prompts(workflow, ["short one", "short two", "short three"], [5, 5, 5])
    assert issues == []
    good = lint_prompts(
        workflow,
        [
            "subject_definitions:\n<Subject 1> ...\n\nsummary:\n...\n\nretention_analysis:\n...\n\ndetailed_description:\n...\n\noverall_soundscape:\n...\n\nnon_diegetic_music:\nNone",
            "integrated_multimodal_description:\n...\n\noverall_soundscape:\n...\n\nnon_diegetic_music:\nNone",
            "integrated_multimodal_description:\n...\n\noverall_soundscape:\n...\n\nnon_diegetic_music:\nNone",
        ],
        [5, 5, 5],
    )
    assert good == []


def test_configure_unified_workflow_writes_single_stage():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_统一工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_unified_workflow(
        workflow,
        "integrated_multimodal_description:\n[Shot 1] A dancer.\n\noverall_soundscape:\nMusic.\n\nnon_diegetic_music:\nNone",
        7,
        generation={"global": {"steps": 18, "audio_steps": 12}},
        model={"mode": "多参考模式", "reference_model": "Minimax_H3\\minimax_h3_ref2va_pruned_int8_convrot.safetensors"},
    )

    editor = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_PromptEditor")
    profile = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_GenerationProfile")
    selector = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_ModeModelSelector")
    assert editor["widgets_values"][1] == 7.0
    assert "dancer" in editor["widgets_values"][2]
    assert profile["widgets_values"][2] == 7
    assert profile["widgets_values"][3] == 18
    assert selector["widgets_values"][0] == "多参考模式"
    assert configured["extra"]["xyue_h3_multi_stage"]["unified"] is True


def test_sampling_settings_are_written_to_global_and_stages():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    sampling = {
        "sampling_preset": "高品质双段",
        "sampling_mode": "双段采样",
        "coarse_steps": 3,
        "upscale_factor": 1.5,
        "refine_pass": True,
        "extend_sigmas": 4,
    }
    configured = configure_workflow(
        workflow,
        ["one", "two", "three"],
        [5, 5, 5],
        generation={
            "global_enabled": True,
            "global": {"sampling": sampling},
            "stages": [
                {"sampling": {"sampling_preset": "高品质双段"}},
                {"sampling": dict(sampling)},
                {},
            ],
        },
    )
    controller = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_StudioController")
    profiles = sorted(
        (node for node in configured["nodes"] if node["type"] == "XYUE_H3_StageGenerationProfile"),
        key=lambda node: node["pos"][1],
    )[:3]
    assert controller["widgets_values"][10:12] == ["高品质双段", 3]
    assert profiles[0]["widgets_values"][9:11] == ["高品质双段", "第1阶段"]
    assert profiles[1]["widgets_values"][9:11] == ["高品质双段", "第2阶段"]
    assert profiles[2]["widgets_values"][9:11] == ["快速单次（推荐）", "第3阶段"]


def test_inspect_sampling_reports_global_and_stages():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_多段循环工作流.json").read_text(encoding="utf-8-sig"))
    report = inspect_sampling(workflow)

    assert report["global"]["sampling_preset"] == "快速单次（推荐）"
    assert len(report["stages"]) == 5
    assert report["stages"][0]["coarse_steps"] == 2
    assert report["stages"][0]["refine_pass"] is False


def test_cloud_multi_stage_config_parses_json_code_block_and_selects_stage():
    config = parse_multi_stage_config(
        """说明\n```json
        {
          "schema": "xyue.h3.multi-stage-cloud-config/v1",
          "workflow": "all_reference",
          "stage_count": 2,
          "prompts": ["one", "two"],
          "generation": {
            "global_enabled": false,
            "stages": [
              {"aspect": "9:16", "resolution": "720p", "duration": 4},
              {"aspect": "9:16", "resolution": "720p", "duration": 7}
            ]
          },
          "acceleration": {"global_mode": "模式1"}
        }
        ```\n说明"""
    )
    prompt, values = stage_values(config, 2)
    assert prompt == "two"
    assert values["duration"] == 7
    assert config["acceleration"]["global_mode"] == "模式1"


def test_cloud_multi_stage_config_rejects_model_and_lora_overrides():
    with pytest.raises(ValueError, match="模型或 LoRA"):
        parse_multi_stage_config({
            "schema": "xyue.h3.multi-stage-cloud-config/v1",
            "stage_count": 1,
            "prompts": ["one"],
            "generation": {"stages": [{"duration": 5}]},
            "models": [{}],
        })


def test_configure_unified_workflow_writes_sampling():
    root = Path(__file__).parents[1]
    workflow = json.loads((root / "workflows" / "XYUE_H3_统一工作流.json").read_text(encoding="utf-8-sig"))
    configured = configure_unified_workflow(
        workflow,
        "integrated_multimodal_description:\n[Shot 1] A dancer.\n\noverall_soundscape:\nMusic.\n\nnon_diegetic_music:\nNone",
        7,
        generation={
            "global": {
                "sampling": {
                    "sampling_preset": "高品质双段",
                    "sampling_mode": "双段采样",
                    "coarse_steps": 2,
                    "upscale_factor": 1.2,
                    "refine_pass": True,
                    "extend_sigmas": 2,
                }
            }
        },
    )
    profile = next(node for node in configured["nodes"] if node["type"] == "XYUE_H3_GenerationProfile")
    assert profile["widgets_values"][9:10] == ["高品质双段"]


def test_resolve_sampling_presets_override_widget_values():
    assert resolve_sampling("快速单次（推荐）", "双段采样", 8, 4.0, False, 0) == {
        "preset": "快速单次（推荐）",
        "mode": "single",
        "coarse_steps": 2,
        "upscale_factor": 1.0,
        "refine_pass": False,
        "extend_sigmas": 0,
    }
    assert resolve_sampling("高品质双段") == {
        "preset": "高品质双段",
        "mode": "dual",
        "coarse_steps": 2,
        "upscale_factor": 1.2,
        "refine_pass": True,
        "extend_sigmas": 2,
    }
    assert resolve_sampling("未知预设", "双段采样", 3, 1.5, True, 4) == {
        "preset": "快速单次（推荐）",
        "mode": "single",
        "coarse_steps": 2,
        "upscale_factor": 1.0,
        "refine_pass": False,
        "extend_sigmas": 0,
    }


def test_acceleration_modes_use_euler_sampler():
    assert sampler_for_acceleration("模式2") == "euler"
    assert sampler_for_acceleration("模式3") == "euler"
    assert sampler_for_acceleration("不启用") == "euler"
    assert sampler_for_acceleration("模式1") == "euler"


def test_acceleration_mode_labels_keep_legacy_aliases():
    assert normalize_acceleration_mode("模式1：TE加速") == "模式1"
    assert normalize_acceleration_mode("模式2：HQ参考") == "模式2"
    assert normalize_acceleration_mode("模式3：实验低显存") == "模式3"
