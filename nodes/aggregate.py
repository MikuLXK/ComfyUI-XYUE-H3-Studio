"""Studio configuration facade node."""

from __future__ import annotations

import json

from comfy_api.latest import io

from ..core.aggregate_workflow import build_aggregate_workflow, config_from_text
from ..core.contracts import CATEGORY


AGGREGATE_CONFIG = io.Custom("XYUE_H3_AGGREGATE_CONFIG")
class XYUEH3AggregateWorkflow(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_AggregateWorkflow",
            display_name="XYUE H3 Studio",
            category=CATEGORY,
            description="XYUE H3 Studio 唯一入口：按当前项目和目标镜头动态构建执行图。",
            inputs=[
                io.String.Input(
                    "config_text",
                    display_name="聚合配置 JSON",
                    multiline=True,
                    dynamic_prompts=False,
                    default=json.dumps(
                        {
                            "schema": "xyue-h3/studio-config-v3",
                            "stage_count": 1,
                            "stage_titles": ["云海问剑"],
                            "prompts": ["integrated_multimodal_description: [Shot 1] ...\n\noverall_soundscape: ...\n\nnon_diegetic_music: ..."],
                            "durations": [5],
                            "transitions": ["cut"],
                            "models": [{
                                "mode": "文生视频模式",
                                "base_model": "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                                "reference_model": "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors",
                                "language_model": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
                                "video_vae": "minimax_h3_video_vae_fp16.safetensors",
                                "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
                                "latent_upscale_model": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
                                "tiny_vae": "none",
                                "lora_enabled": True,
                                "lora_name": "minimax_h3\\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
                                "lora_strength": 1.0,
                                "attention_mode": "MiniMax H3 Kitchen Attention",
                            }],
                            "generation": {"global_enabled": False, "stages": [{
                                "aspect": "16:9", "resolution": "0.4MP|480p（864×480）", "duration": 5,
                                "video_steps": 4, "audio_steps": 4, "scheduler": "简单稳定（推荐）",
                                "seed": 0, "seed_control": "randomize", "reference_size": "适配生成画布（省显存）",
                                "sampling": {"upscale_factor": 1.5, "sigma_steps": 3, "denoise": 0.3},
                            }]},
                            "save_policy": {
                                "project_name": "当前项目",
                                "project_folder": "当前项目",
                                "stage_pattern": "{name}_{index:02d}",
                                "final_pattern": "{name}_最终",
                                "collision": "increment",
                                "save_stage_videos": True,
                                "save_final_video": True,
                                "save_report": True,
                            },
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            outputs=[AGGREGATE_CONFIG.Output(display_name="聚合配置"), io.String.Output(display_name="聚合报告")],
        )

    @classmethod
    def execute(cls, config_text):
        plan = config_from_text(config_text)
        _, report = build_aggregate_workflow(plan)
        config = {
            "schema": "xyue-h3/studio-config-v3",
            "workflow": report["workflow"],
            "stage_count": report["stage_count"],
            "stage_titles": list(plan.get("stage_titles") or [f"镜头 {index:02d}" for index in range(1, report["stage_count"] + 1)]),
            "prompts": list(plan["prompts"]),
            "durations": report["durations"],
            "transitions": report["transitions"],
            "models": list(plan["models"]),
            "generation": dict(plan.get("generation") or {}),
            "composition": dict(plan.get("composition") or {}),
            "save_policy": dict(plan.get("save_policy") or {}),
        }
        return io.NodeOutput(config, json.dumps(report, ensure_ascii=False, indent=2))


AGGREGATE_NODE_CLASSES = [XYUEH3AggregateWorkflow]
