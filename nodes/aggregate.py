"""Standalone facade node for the maintained XYUE H3 workflow templates."""

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
            display_name="XYUE H3 聚合工作流",
            category=CATEGORY,
            description="独立节点入口。内部使用维护中的完整工作流模板，保留原有节点、第三方节点和每个加速分支的原始顺序。",
            inputs=[
                io.String.Input(
                    "config_text",
                    display_name="聚合配置 JSON",
                    multiline=True,
                    dynamic_prompts=False,
                    default=json.dumps(
                        {
                            "schema": "xyue-h3/aggregate-workflow-config-v2",
                            "workflow": "全程多参考短剧",
                            "stage_count": 1,
                            "stage_titles": ["云海问剑"],
                            "prompts": ["integrated_multimodal_description: [Shot 1] ...\n\noverall_soundscape: ...\n\nnon_diegetic_music: ..."],
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
                            "generation": {"global_enabled": False, "stages": [{
                                "aspect": "16:9", "resolution": "480p（864×480）", "duration": 5,
                                "steps": 4, "audio_steps": 4, "scheduler": "简单稳定（推荐）",
                                "seed": 0, "seed_control": "randomize", "reference_size": "适配生成画布（省显存）",
                                "sampling": {"sampling_preset": "高品质双段"},
                            }]},
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
            "schema": "xyue-h3/aggregate-workflow-config-v2",
            "workflow": report["workflow"],
            "stage_count": report["stage_count"],
            "stage_titles": list(plan.get("stage_titles") or [f"镜头 {index:02d}" for index in range(1, report["stage_count"] + 1)]),
            "prompts": list(plan["prompts"]),
            "durations": report["durations"],
            "transitions": report["transitions"],
            "acceleration_modes": report["acceleration_modes"],
            "models": list(plan["models"]),
            "generation": dict(plan.get("generation") or {}),
        }
        return io.NodeOutput(config, json.dumps(report, ensure_ascii=False, indent=2))


AGGREGATE_NODE_CLASSES = [XYUEH3AggregateWorkflow]
