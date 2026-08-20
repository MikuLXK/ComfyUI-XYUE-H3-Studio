"""Single public Studio executor; it calls core and third-party adapters directly."""

from __future__ import annotations

import json
import glob
import os
from pathlib import Path
from typing import Any

from comfy_api.latest import io
import folder_paths

from ..core.aggregate_workflow import AGGREGATE_CONFIG_SCHEMA, _validate_plan
from ..core.runtime_materials import load_material_pack
from ..core.save_policy import output_prefix, save_video_with_policy
from ..core.seed_policy import next_seed, normalize_seed_mode
from ..nodes.continuation import XYUEH3ContinuationReference
from ..nodes.generation import (
    XYUEH3Generator,
    XYUEH3LastFrameExtractor,
    XYUEH3ModeModelSelector,
    XYUEH3StageGenerationProfile,
)
from ..nodes.video_concat import concatenate_videos
from ..services.video_checkpoints import find_latest_stage_checkpoint, load_checkpoint_video


def _stage_name(index: int) -> str:
    return f"第{('一', '二', '三', '四', '五')[index - 1]}阶段"


def _load_previous(plan: dict[str, Any], index: int):
    files = list(plan.get("resume_files") or [])
    selected = files[index - 1] if index - 1 < len(files) else ""
    if not selected:
        policy = dict(plan.get("save_policy") or {})
        prefix = output_prefix(policy, kind="stage", index=index, stage=_stage_name(index), seed=0)
        matches = sorted(
            glob.glob(os.path.join(folder_paths.get_output_directory(), f"{prefix}*.mp4")),
            key=os.path.getmtime,
        )
        if matches:
            root = os.path.abspath(folder_paths.get_output_directory())
            relative = os.path.relpath(matches[-1], root).replace(os.sep, "/")
            selected = f"{relative} [output]"
    if not selected:
        selected = find_latest_stage_checkpoint(_stage_name(index)) or ""
    if not selected:
        raise ValueError(f"{_stage_name(index)} 没有可复用的已保存视频")
    return load_checkpoint_video(selected)[0]


class XYUEH3StudioExecutor(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StudioExecutor",
            display_name="XYUE H3 Studio 执行器",
            category="XYUE/H3 Studio/Internal",
            description="由 Studio 动态创建并执行当前目标镜头；不依赖固定工作流模板。",
            inputs=[io.String.Input("config_text", display_name="Studio 配置", multiline=True, force_input=True)],
            outputs=[io.Video.Output(display_name="当前镜头视频"), io.String.Output(display_name="执行报告")],
            hidden=[io.Hidden.unique_id, io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, config_text, unique_id=None):
        try:
            plan = json.loads(str(config_text)) if not isinstance(config_text, dict) else dict(config_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Studio 配置不是有效 JSON：第 {exc.lineno} 行，第 {exc.colno} 列") from exc
        if plan.get("schema") != AGGREGATE_CONFIG_SCHEMA:
            raise ValueError(f"配置 schema 必须是 {AGGREGATE_CONFIG_SCHEMA}")
        prompts, durations, stage_count, transitions, models = _validate_plan(plan)
        target = max(1, min(stage_count, int(plan.get("run_stage") or stage_count)))
        generation = dict(plan.get("generation") or {})
        stage_config = dict((generation.get("stages") or [])[target - 1])
        raw_seed_mode = stage_config.get("seed_control")
        if raw_seed_mode is None:
            raw_seed_mode = stage_config.get("seed_mode")
        if raw_seed_mode is None:
            raw_seed_mode = "fixed" if int(stage_config.get("seed") or 0) else "random"
        seed_mode = normalize_seed_mode(raw_seed_mode)
        stage_config["seed"] = next_seed(stage_config.get("seed", 0), seed_mode)
        stage_config["seed_mode"] = seed_mode
        model_config = dict(models[target - 1])
        mode = str(model_config.get("mode") or "文生视频模式")
        selector_output = XYUEH3ModeModelSelector.execute(
            mode=mode,
            base_model=model_config.get("base_model", ""),
            reference_model=model_config.get("reference_model", ""),
            language_model=model_config.get("language_model", ""),
            video_vae=model_config.get("video_vae", ""),
            audio_vae=model_config.get("audio_vae", ""),
            latent_upscale_model=model_config.get("latent_upscale_model", ""),
            tiny_vae=model_config.get("tiny_vae", "none"),
            lora_enabled=bool(model_config.get("lora_enabled", True)),
            lora_name=model_config.get("lora_name", "不使用 LoRA"),
            lora_strength=float(model_config.get("lora_strength", 1.0)),
            attention_mode=model_config.get("attention_mode", "MiniMax H3 Kitchen Attention"),
        )
        model_profile = selector_output[0]
        prepared_model = selector_output[2]
        stage_config["index"] = target
        generation_profile = XYUEH3StageGenerationProfile.execute(
            aspect=stage_config.get("aspect", "16:9"),
            resolution=stage_config.get("resolution", "0.4MP|480p（864×480）"),
            duration=durations[target - 1],
            video_steps=stage_config.get("video_steps", 4),
            audio_steps=stage_config.get("audio_steps", 4),
            scheduler=stage_config.get("scheduler", "简单稳定（推荐）"),
            seed=stage_config.get("seed", 0),
            reference_size=stage_config.get("reference_size", "适配生成画布（省显存）"),
            upscale_factor=(stage_config.get("sampling") or {}).get("upscale_factor", 1.5),
            sigma_steps=(stage_config.get("sampling") or {}).get("sigma_steps", 3),
            denoise=(stage_config.get("sampling") or {}).get("denoise", 0.3),
            stage_name=_stage_name(target),
            stage_count=target,
        )[0]
        material_pack = load_material_pack(list(plan.get("material_overrides") or [])) if mode == "多参考模式" else {}
        previous_video = None
        first_frame = None
        if target > 1 and transitions[target - 1] in {"tail", "motion"}:
            previous_video = _load_previous(plan, target - 1)
            if transitions[target - 1] == "tail":
                previous_components = previous_video.get_components()
                first_frame = previous_components.images[-1:].contiguous()
                if mode == "多参考模式":
                    material_pack = XYUEH3ContinuationReference.execute(
                        material_pack=material_pack,
                        continuation_frame=first_frame,
                        strategy="自动追加，9 图时替换最后启用图片（推荐）",
                        anchor_name="上一段尾帧",
                    )[0]
        generated = XYUEH3Generator.execute(
            model_profile=model_profile,
            generation_profile=generation_profile,
            prompt=prompts[target - 1],
            prepared_model=prepared_model,
            material_pack=material_pack if mode == "多参考模式" else None,
            first_frame=first_frame if mode in {"首帧生视频模式", "首尾帧生视频模式"} else None,
            last_frame=None,
            motion_context=previous_video if transitions[target - 1] == "motion" and target > 1 else None,
            unique_id=unique_id,
        )
        video = generated[0]
        policy = dict(plan.get("save_policy") or {})
        saved_stage = None
        if bool(policy.get("save_stage_videos", True)):
            saved_stage = save_video_with_policy(
                video,
                output_prefix(policy, kind="stage", index=target, stage=_stage_name(target), seed=int(stage_config.get("seed", 0))),
                "mp4",
                "h264",
                collision=str(policy.get("collision") or "increment"),
            )
        final_video = video
        final_saved = None
        if bool((plan.get("composition") or {}).get("enabled")):
            videos = []
            for index in range(1, target + 1):
                videos.append(video if index == target else _load_previous(plan, index))
            final_video, _ = concatenate_videos(videos)
            if bool(policy.get("save_final_video", True)):
                final_saved = save_video_with_policy(
                    final_video,
                    output_prefix(policy, kind="final", index=target, stage="最终", seed=int(stage_config.get("seed", 0))),
                    "mp4",
                    "h264",
                    collision=str(policy.get("collision") or "increment"),
                )
        report = {
            "schema": "xyue-h3/studio-execution-report-v3",
            "status": "passed",
            "target_stage": target,
            "stage_file": saved_stage.full_path if saved_stage else None,
            "final_file": final_saved.full_path if final_saved else (saved_stage.full_path if saved_stage else None),
            "seed": int(stage_config.get("seed", 0)),
            "seed_mode": seed_mode,
            "transition": transitions[target - 1],
            "lora_enabled": bool(model_config.get("lora_enabled", True)),
            "attention_mode": model_config.get("attention_mode", "MiniMax H3 Kitchen Attention"),
        }
        if bool(policy.get("save_report", True)):
            report_path = Path(folder_paths.get_output_directory()) / f"{output_prefix(policy, kind='final', index=target, stage='最终', seed=int(stage_config.get('seed', 0)))}_报告.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report["report_file"] = str(report_path)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return io.NodeOutput(final_video, json.dumps(report, ensure_ascii=False, indent=2))


STUDIO_EXECUTOR_NODE_CLASSES = [XYUEH3StudioExecutor]
