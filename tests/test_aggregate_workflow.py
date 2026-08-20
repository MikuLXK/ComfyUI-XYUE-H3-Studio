from core.aggregate_workflow import build_aggregate_workflow


def _model(mode="文生视频模式"):
    return {
        "mode": mode,
        "base_model": "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "reference_model": "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors",
        "language_model": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
        "video_vae": "minimax_h3_video_vae_fp16.safetensors",
        "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
        "latent_upscale_model": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
        "tiny_vae": "none",
        "lora_enabled": False,
        "lora_name": "不使用 LoRA",
        "lora_strength": 1.0,
        "attention_mode": "MiniMax H3 Kitchen Attention",
    }


def _stage():
    return {
        "aspect": "16:9",
        "resolution": "0.4MP|480p（864×480）",
        "duration": 5,
        "video_steps": 4,
        "audio_steps": 4,
        "scheduler": "简单稳定（推荐）",
        "seed": 1,
        "reference_size": "适配生成画布（省显存）",
        "sampling": {"upscale_factor": 1.5, "sigma_steps": 3, "denoise": 0.3},
    }


def _plan(count=3, *, target=3, execution=None, transitions=None):
    return {
        "schema": "xyue-h3/studio-config-v3",
        "stage_count": count,
        "run_stage": target,
        "execution_stages": execution or [target],
        "prompts": [f"prompt {index}" for index in range(1, count + 1)],
        "durations": [5] * count,
        "transitions": transitions or ["cut"] * count,
        "models": [_model() for _ in range(count)],
        "generation": {"stages": [_stage() for _ in range(count)]},
    }


def test_dynamic_graph_only_contains_target_cut_stage():
    workflow, report = build_aggregate_workflow(_plan())
    assert len(workflow["nodes"]) == 1
    assert workflow["nodes"][0]["type"] == "XYUE_H3_StudioExecutor"
    assert report["execution"] == "direct_studio_executor"
    assert report["run_stage"] == 3


def test_dynamic_graph_contains_previous_resume_for_motion():
    plan = _plan(execution=[2, 3], transitions=["cut", "cut", "motion"])
    workflow, _ = build_aggregate_workflow(plan)
    payload = workflow["nodes"][0]["widgets_values"][0]
    assert '"execution_stages":[2,3]' in payload


def test_configured_graph_is_not_a_template_file():
    workflow, _ = build_aggregate_workflow(_plan(count=1, target=1, execution=[1]))
    assert workflow["extra"]["xyue_h3_execution_graph"]["source"] == "studio-config-v3"
