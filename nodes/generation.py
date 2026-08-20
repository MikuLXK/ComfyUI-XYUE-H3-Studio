"""Local MiniMax H3 model selection, generation profile, and renderer."""

from __future__ import annotations

import json
import os
from typing import Any

import folder_paths
import nodes as comfy_nodes
from comfy_api.latest import io, ui
from comfy_extras.nodes_audio import VAEDecodeAudio
from comfy_extras.nodes_custom_sampler import (
    BasicGuider,
    BasicScheduler,
    CFGGuider,
    KSamplerSelect,
    RandomNoise,
    SamplerCustomAdvanced,
    SplitSigmas,
)
from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift
from comfy_extras.nodes_video import CreateVideo

from ..core.contracts import CATEGORY, GENERATION_PROFILE_SCHEMA, MAX_STAGES, MODE_OPTIONS, MODEL_PROFILE_SCHEMA, STUDIO_CONTROL_SCHEMA, normalize_mode
from ..core.generation_options import (
    DEFAULT_AUDIO_STEPS,
    DEFAULT_DENOISE,
    DEFAULT_DURATION,
    DEFAULT_REFERENCE_SIZE,
    DEFAULT_SCHEDULER,
    DEFAULT_SIGMA_STEPS,
    DEFAULT_STEPS,
    MIN_AUDIO_STEPS,
    MAX_STEPS,
    MIN_STEPS,
    REFERENCE_SIZE_OPTIONS,
    SCHEDULER_OPTIONS,
    normalize_reference_size,
    normalize_scheduler,
    resolve_sampling,
)
from ..core.latent_refine import refine_av_latent
from ..core.model_pipeline import ATTENTION_OPTIONS, NO_LORA, apply_attention, apply_lora
from ..core.motion_context import apply_motion_context, trim_motion_context
from ..core.preview import attach_preview
from ..core.resolution import ASPECTS, DEFAULT_RESOLUTION, RESOLUTION_OPTIONS, align_duration, canonical_resolution_label, latent_scaled_canvas, resolve_canvas
from ..core.sigma_refiner import refine_sigmas
from ..core.multi_stage_config import stage_values
from ..core.h3_prompt import compile_draft
from .assets import MATERIAL_PACK

MODEL_PROFILE = io.Custom("XYUE_H3_MODEL_PROFILE")
GENERATION_PROFILE = io.Custom("XYUE_H3_GENERATION_PROFILE")
STUDIO_CONTROL = io.Custom("XYUE_H3_STUDIO_CONTROL")
MULTI_STAGE_CONFIG = io.Custom("XYUE_H3_MULTI_STAGE_CONFIG")
MOTION_CONTEXT = io.Custom("XYUE_H3_MOTION_CONTEXT")


def _display(name: str) -> str:
    return f"XYUE_{name}"


def _stage_number(value: str) -> int:
    markers = ("一", "二", "三", "四", "五")
    text = str(value)
    for index, marker in enumerate(markers, start=1):
        if f"第{marker}阶段" in text:
            return index
    for index in range(1, MAX_STAGES + 1):
        if f"阶段{index}" in text or f"阶段 {index}" in text:
            return index
    return 1


def _models(folder: str, needle: str = "") -> list[str]:
    if folder == "latent_upscale_models" and folder not in folder_paths.folder_names_and_paths:
        folder_paths.add_model_folder_path(folder, os.path.join(folder_paths.models_dir, folder))
    try:
        values = list(folder_paths.get_filename_list(folder))
    except KeyError:
        values = []
    if needle:
        filtered = [value for value in values if needle.lower() in value.lower()]
        if filtered:
            values = filtered
    return sorted(values)


def _optional_models(folder: str, fallback: str = "none") -> list[str]:
    values = _models(folder)
    return [fallback, *values] if fallback not in values else values


def _pick(values: list[str], needles: tuple[str, ...], fallback: str = "") -> str:
    for value in values:
        if any(needle.lower() in value.lower() for needle in needles):
            return value
    return values[0] if values else fallback


def _pick_lora(values: list[str], mode: str) -> str:
    marker = "ref2v" if normalize_mode(mode) == "Ref2VA" else "fl2v"
    preferred = [value for value in values if marker in value.lower() and "4step" in value.lower()]
    return preferred[0] if preferred else NO_LORA


def _profile_with_overrides(
    aspect, resolution, duration, video_steps, audio_steps, scheduler, seed, reference_size,
    upscale_factor, sigma_steps, denoise,
    overrides: dict[str, Any] | None,
):
    values = dict(overrides or {})
    sampling = dict(values.get("sampling") or {})
    return XYUEH3GenerationProfile.execute(
        aspect=values.get("aspect", aspect),
        resolution=values.get("resolution", resolution),
        duration=values.get("duration", duration),
        video_steps=values.get("video_steps", video_steps),
        audio_steps=values.get("audio_steps", audio_steps),
        scheduler=values.get("scheduler", scheduler),
        seed=values.get("seed", seed),
        reference_size=values.get("reference_size", reference_size),
        upscale_factor=sampling.get("upscale_factor", upscale_factor),
        sigma_steps=sampling.get("sigma_steps", sigma_steps),
        denoise=sampling.get("denoise", denoise),
    )


class XYUEH3ModeModelSelector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        diffusion = _models("diffusion_models")
        text = _models("text_encoders")
        vaes = _models("vae", "minimax_h3")
        latent_upscalers = [
            model_name
            for model_name in _models("latent_upscale_models")
            if "minimax_h3" in model_name.lower()
        ]
        tiny_vaes = _optional_models("vae_approx")
        loras = [NO_LORA, *_models("loras")]
        default_lora = _pick_lora(loras[1:], "文生视频模式")
        return io.Schema(
            node_id="XYUE_H3_ModeModelSelector",
            display_name=_display("模式与模型选择"),
            category=CATEGORY,
            description="快速选择 H3 生成模式，并自由选择主模型、语言模型和音画 VAE。",
            inputs=[
                io.Combo.Input("mode", display_name="生成模式", options=list(MODE_OPTIONS), default="文生视频模式"),
                io.Combo.Input("base_model", display_name="基础/首尾帧模型", options=diffusion, default=_pick(diffusion, ("fl2va",))),
                io.Combo.Input("reference_model", display_name="多参考模型", options=diffusion, default=_pick(diffusion, ("ref2va",))),
                io.Combo.Input("language_model", display_name="语言模型", options=text, default=_pick(text, ("qwen3vl", "minimax"))),
                io.Combo.Input("video_vae", display_name="视频 VAE", options=vaes, default=_pick(vaes, ("video_vae",))),
                io.Combo.Input("audio_vae", display_name="音频 VAE", options=vaes, default=_pick(vaes, ("audio_vae",))),
                io.Combo.Input("latent_upscale_model", display_name="H3 Latent 放大模型", options=latent_upscalers or ["(未安装 H3 Latent Upscaler)"], default=_pick(latent_upscalers, ("minimax_h3_latent_upscaler_3d_fp16",), latent_upscalers[0] if latent_upscalers else "(未安装 H3 Latent Upscaler)")),
                io.Combo.Input("tiny_vae", display_name="实时预览 Tiny VAE", options=tiny_vaes, default="none"),
                io.Boolean.Input("lora_enabled", display_name="启用 LoRA", default=default_lora != NO_LORA, label_on="开启", label_off="关闭"),
                io.Combo.Input("lora_name", display_name="LoRA 模型", options=loras, default=default_lora),
                io.Float.Input("lora_strength", display_name="LoRA 强度", default=1.0, min=0.0, max=2.0, step=0.05),
                io.Combo.Input("attention_mode", display_name="注意力模式", options=list(ATTENTION_OPTIONS), default=ATTENTION_OPTIONS[0]),
            ],
            outputs=[MODEL_PROFILE.Output(display_name="模型配置"), io.String.Output(display_name="模型报告"), io.Model.Output(display_name="主模型")],
        )

    @classmethod
    def execute(cls, mode, base_model, reference_model, language_model, video_vae, audio_vae, latent_upscale_model="", tiny_vae="none",
                lora_enabled=True, lora_name=NO_LORA, lora_strength=1.0, attention_mode=ATTENTION_OPTIONS[0]):
        mode = normalize_mode(str(mode))
        profile = {
            "schema": MODEL_PROFILE_SCHEMA,
            "mode": mode,
            "main_model": str(reference_model if mode == "Ref2VA" else base_model),
            "base_model": str(base_model),
            "reference_model": str(reference_model),
            "language_model": str(language_model),
            "video_vae": str(video_vae),
            "audio_vae": str(audio_vae),
            "latent_upscale_model": str(latent_upscale_model),
            "tiny_vae": str(tiny_vae or "none"),
            "lora_enabled": bool(lora_enabled),
            "lora_name": str(lora_name or NO_LORA),
            "lora_strength": float(lora_strength),
            "attention_mode": str(attention_mode),
        }
        model = None
        if profile["main_model"]:
            model = comfy_nodes.UNETLoader().load_unet(profile["main_model"], "default")[0]
            model = MiniMaxH3SigmaShift.execute(model=model, shift_video=12.0, shift_audio=3.0)[0]
            model = apply_lora(model, enabled=profile["lora_enabled"], name=profile["lora_name"], strength=profile["lora_strength"])
            model = apply_attention(model, profile["attention_mode"])
        return io.NodeOutput(profile, json.dumps(profile, ensure_ascii=False, indent=2), model)


class XYUEH3GenerationProfile(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_GenerationProfile",
            display_name=_display("生成参数"),
            category=CATEGORY,
            description="统一设置比例、原生/MP 画布、时长、步数、调度和种子。",
            inputs=[
                io.Combo.Input("aspect", display_name="画面比例", options=list(ASPECTS), default="16:9"),
                io.Combo.Input("resolution", display_name="初始分辨率（推荐 0.4MP）", options=list(RESOLUTION_OPTIONS), default=DEFAULT_RESOLUTION),
                io.Int.Input("duration", display_name="时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("video_steps", display_name="基础视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1),
                io.Int.Input("audio_steps", display_name="基础音频步数", default=DEFAULT_AUDIO_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1,
                             tooltip="H3 使用联合音画采样，执行时采用视频/音频步数中的较大值作为共享基础步数。"),
                io.Combo.Input("scheduler", display_name="调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="控制去噪步在噪声区间中的分布。简单稳定适合作为默认；Beta 偏重动态细节；标准均衡用于对照。"),
                io.Int.Input("seed", display_name="随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="默认每次生成后随机；下拉菜单可切换为固定、递增或递减。"),
                io.Combo.Input("reference_size", display_name="参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                                tooltip="适配生成画布会缩放参考图并节省显存；保留参考图细节会使用更大参考尺寸并增加显存占用。"),
                io.Float.Input("upscale_factor", display_name="自动放大倍率", default=1.5, min=1.0, max=4.0, step=0.1),
                io.Int.Input("sigma_steps", display_name="Sigma 精修步数", default=DEFAULT_SIGMA_STEPS, min=1, max=20, step=1),
                io.Float.Input("denoise", display_name="降噪程度", default=DEFAULT_DENOISE, min=0.01, max=1.0, step=0.01),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[GENERATION_PROFILE.Output(display_name="生成配置"), io.Int.Output(display_name="宽"), io.Int.Output(display_name="高"), io.Int.Output(display_name="帧数"), io.String.Output(display_name="参数报告")],
        )

    @classmethod
    def execute(cls, aspect, resolution, duration=DEFAULT_DURATION, video_steps=DEFAULT_STEPS, audio_steps=DEFAULT_AUDIO_STEPS,
                scheduler=DEFAULT_SCHEDULER, seed=0, reference_size=DEFAULT_REFERENCE_SIZE, upscale_factor=1.5,
                sigma_steps=DEFAULT_SIGMA_STEPS, denoise=DEFAULT_DENOISE, multi_stage_config=None):
        _, configured_values = stage_values(multi_stage_config, 1)
        if configured_values is not None:
            return _profile_with_overrides(
                aspect, resolution, duration, video_steps, audio_steps, scheduler, seed, reference_size,
                upscale_factor, sigma_steps, denoise,
                configured_values,
            )
        target_width, target_height, experimental = resolve_canvas(str(aspect), str(resolution))
        frames, effective_duration = align_duration(int(duration))
        if not MIN_STEPS <= int(video_steps) <= MAX_STEPS:
            raise ValueError(f"H3 视频步数必须在 {MIN_STEPS}–{MAX_STEPS} 之间")
        if not MIN_AUDIO_STEPS <= int(audio_steps) <= MAX_STEPS:
            raise ValueError(f"H3 音频步数必须在 {MIN_AUDIO_STEPS}–{MAX_STEPS} 之间")
        sampling = resolve_sampling(upscale_factor, sigma_steps, denoise)
        width, height = target_width, target_height
        target_width, target_height = latent_scaled_canvas(width, height, sampling["upscale_factor"])
        profile = {
            "schema": GENERATION_PROFILE_SCHEMA,
            "aspect": str(aspect),
            "resolution": canonical_resolution_label(str(resolution)),
            "width": width,
            "height": height,
            "target_width": target_width,
            "target_height": target_height,
            "first_width": width,
            "first_height": height,
            "second_width": target_width,
            "second_height": target_height,
            "duration": int(duration),
            "effective_duration": effective_duration,
            "frames": frames,
            "video_steps": int(video_steps),
            "audio_steps": int(audio_steps),
            "joint_steps": max(int(video_steps), int(audio_steps)),
            "scheduler": normalize_scheduler(str(scheduler)),
            "seed": int(seed),
            "reference_size": normalize_reference_size(str(reference_size)),
            "sampling": sampling,
            "experimental_resolution": experimental,
        }
        report = json.dumps(profile, ensure_ascii=False, indent=2)
        return io.NodeOutput(profile, width, height, frames, report)


class XYUEH3StudioController(io.ComfyNode):
    """Global switch and shared generation contract for multi-stage workflows."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StudioController",
            display_name=_display("全局生成控制器"),
            category=CATEGORY,
            description="开启全局控制后覆盖所有阶段；关闭后由每个阶段的独立配置控制。",
            inputs=[
                io.Boolean.Input("global_enabled", display_name="启用全局控制", default=True, label_on="全局统一", label_off="阶段独立"),
                io.Combo.Input("aspect", display_name="画面比例", options=list(ASPECTS), default="16:9"),
                io.Combo.Input("resolution", display_name="初始分辨率（推荐 0.4MP）", options=list(RESOLUTION_OPTIONS), default=DEFAULT_RESOLUTION),
                io.Int.Input("duration", display_name="全局时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("video_steps", display_name="全局基础视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1),
                io.Int.Input("audio_steps", display_name="全局基础音频步数", default=DEFAULT_AUDIO_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1),
                io.Combo.Input("scheduler", display_name="全局调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="统一控制各阶段的去噪步分布。简单稳定适合作为默认。"),
                io.Int.Input("seed", display_name="全局随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="默认每次生成后随机；关闭全局控制时，各阶段使用自己的随机种子。"),
                io.Combo.Input("reference_size", display_name="全局参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                               tooltip="适配画布更省显存；保留细节会提高参考图处理尺寸。"),
                io.Float.Input("upscale_factor", display_name="全局自动放大倍率", default=1.5, min=1.0, max=4.0, step=0.1),
                io.Int.Input("sigma_steps", display_name="全局 Sigma 精修步数", default=DEFAULT_SIGMA_STEPS, min=1, max=20, step=1),
                io.Float.Input("denoise", display_name="全局降噪程度", default=DEFAULT_DENOISE, min=0.01, max=1.0, step=0.01),
                io.Int.Input("stage_count", display_name="启用阶段数", default=3, min=1, max=MAX_STAGES, step=1,
                 tooltip="只运行前 N 个阶段，后续阶段惰性跳过。"),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[STUDIO_CONTROL.Output(display_name="全局控制"), io.String.Output(display_name="控制器报告")],
        )

    @classmethod
    def execute(cls, global_enabled, aspect, resolution, duration=DEFAULT_DURATION, video_steps=DEFAULT_STEPS,
                audio_steps=DEFAULT_AUDIO_STEPS, scheduler=DEFAULT_SCHEDULER, seed=0, reference_size=DEFAULT_REFERENCE_SIZE,
                upscale_factor=1.5, sigma_steps=DEFAULT_SIGMA_STEPS, denoise=DEFAULT_DENOISE, stage_count=3, multi_stage_config=None):
        config = dict(multi_stage_config or {})
        config_values = None
        if config.get("schema") == "xyue.h3.multi-stage-cloud-config/v1":
            generation = dict(config.get("generation") or {})
            config_values = dict(generation.get("global") or {})
            if not config_values:
                config_values = dict((generation.get("stages") or [{}])[0])
            global_enabled = bool(generation.get("global_enabled", global_enabled))
            stage_count = int(config.get("stage_count", stage_count))
        profile, *_ = _profile_with_overrides(
            aspect, resolution, duration, video_steps, audio_steps, scheduler, seed, reference_size,
            upscale_factor, sigma_steps, denoise,
            config_values,
        )
        control = {
            "schema": STUDIO_CONTROL_SCHEMA,
            "global_enabled": bool(global_enabled),
            "profile": dict(profile),
            "stage_count": max(1, min(MAX_STAGES, int(stage_count))),
        }
        report = {
            "global_enabled": bool(global_enabled),
            "source": "全局" if global_enabled else "阶段独立",
            "stage_count": control["stage_count"],
            "profile": profile,
        }
        return io.NodeOutput(control, json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3StageGenerationProfile(io.ComfyNode):
    """Resolve one stage's profile from the global controller or its local controls."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StageGenerationProfile",
            display_name=_display("阶段生成配置"),
            category=CATEGORY,
            description="全局控制开启时采用控制器参数；关闭时仅采用本阶段参数。每个阶段可独立设置画面、时长和精度。",
            inputs=[
                STUDIO_CONTROL.Input("studio_control", display_name="全局控制器", optional=True),
                io.Combo.Input("aspect", display_name="本阶段比例", options=list(ASPECTS), default="16:9"),
                io.Combo.Input("resolution", display_name="本阶段初始分辨率（推荐 0.4MP）", options=list(RESOLUTION_OPTIONS), default=DEFAULT_RESOLUTION),
                io.Int.Input("duration", display_name="本阶段时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("video_steps", display_name="本阶段基础视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1),
                io.Int.Input("audio_steps", display_name="本阶段基础音频步数", default=DEFAULT_AUDIO_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1),
                io.Combo.Input("scheduler", display_name="本阶段调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="仅在全局控制关闭时生效。简单稳定适合作为默认。"),
                io.Int.Input("seed", display_name="本阶段随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="每次生成后自动随机；仅在全局控制关闭时生效。"),
                io.Combo.Input("reference_size", display_name="本阶段参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                               tooltip="仅在全局控制关闭时生效。适配画布更省显存，保留细节会占用更多显存。"),
                io.Float.Input("upscale_factor", display_name="本阶段自动放大倍率", default=1.5, min=1.0, max=4.0, step=0.1),
                io.Int.Input("sigma_steps", display_name="本阶段 Sigma 精修步数", default=DEFAULT_SIGMA_STEPS, min=1, max=20, step=1),
                io.Float.Input("denoise", display_name="本阶段降噪程度", default=DEFAULT_DENOISE, min=0.01, max=1.0, step=0.01),
                io.String.Input("stage_name", display_name="阶段名称", default="第一阶段", multiline=False,
                                 tooltip="控制器启用的阶段数之外的本阶段会被跳过，不加载模型不采样。"),
                io.Int.Input("stage_count", display_name="项目镜头数", default=1, min=1, max=MAX_STAGES, step=1),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[GENERATION_PROFILE.Output(display_name="阶段生成配置"), io.String.Output(display_name="阶段参数报告")],
        )

    @classmethod
    def execute(cls, studio_control=None, aspect="16:9", resolution=DEFAULT_RESOLUTION, duration=DEFAULT_DURATION,
                 video_steps=DEFAULT_STEPS, audio_steps=DEFAULT_AUDIO_STEPS, scheduler=DEFAULT_SCHEDULER, seed=0,
                 reference_size=DEFAULT_REFERENCE_SIZE, upscale_factor=1.5, sigma_steps=DEFAULT_SIGMA_STEPS,
                 denoise=DEFAULT_DENOISE,
                 stage_name="第一阶段", stage_count=1, multi_stage_config=None):
        config = dict(multi_stage_config or {})
        config_values = None
        if config.get("schema") == "xyue.h3.multi-stage-cloud-config/v1":
            stage_index = _stage_number(stage_name)
            _, config_values = stage_values(config, stage_index)
            if bool((config.get("generation") or {}).get("global_enabled")):
                config_values = dict((config.get("generation") or {}).get("global") or config_values or {})
        local_profile, *_ = _profile_with_overrides(
            aspect, resolution, duration, video_steps, audio_steps, scheduler, seed, reference_size,
            upscale_factor, sigma_steps, denoise, config_values,
        )
        control = dict(studio_control or {})
        if control.get("schema") != STUDIO_CONTROL_SCHEMA:
            selected = local_profile
            source = "阶段独立"
            stage_count = max(1, min(MAX_STAGES, int(stage_count)))
        elif bool(control.get("global_enabled")):
            selected = dict(control.get("profile") or local_profile)
            source = "全局"
            stage_count = max(1, min(MAX_STAGES, int(control.get("stage_count", 3))))
        else:
            selected = local_profile
            source = "阶段独立"
            stage_count = max(1, min(MAX_STAGES, int(control.get("stage_count", 3))))
        selected["source"] = source
        selected["stage_name"] = str(stage_name)
        selected["stage_count"] = stage_count
        return io.NodeOutput(selected, json.dumps({"source": source, "stage_name": str(stage_name), "stage_count": stage_count, "profile": selected}, ensure_ascii=False, indent=2))


def _reference_payload(material_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    images: dict[str, Any] = {}
    videos: dict[str, Any] = {}
    video_audios: dict[str, Any] = {}
    audios: dict[str, Any] = {}
    for entry in (material_pack.get("images", {}).get("entries") or []):
        if entry.get("image") is not None:
            images[f"ref_image_{entry.get('index', len(images) + 1)}"] = entry["image"]
    for entry in (material_pack.get("videos", {}).get("entries") or []):
        if entry.get("frames") is not None:
            index = entry.get("index", len(videos) + 1)
            videos[f"ref_video_{index}"] = entry["frames"]
            if entry.get("audio") is not None:
                video_audios[f"ref_video_audio_{index}"] = entry["audio"]
    for entry in (material_pack.get("audios", {}).get("entries") or []):
        if entry.get("audio") is not None:
            audios[f"ref_audio_{len(audios) + 1}"] = entry["audio"]
    return {"ref_images": images, "ref_videos": videos, "ref_video_audios": video_audios, "ref_audios": audios}


def _sample_av(
    *,
    model,
    conditioned,
    guider,
    sampler,
    sigmas,
    latent,
    noise,
    sampling,
    target_width,
    target_height,
    model_profile,
):
    """Run the official H3 learned-upscale two-pass flow."""

    coarse_steps = max(1, int(sampling.get("base_steps") or 1))
    sigmas = refine_sigmas(
        sigmas,
        extra_steps=max(1, int(sampling.get("sigma_steps") or DEFAULT_SIGMA_STEPS)),
        start_at_sigma=float(sampling.get("sigma_start", 0.7)),
        end_at_sigma=float(sampling.get("sigma_end", 0.0)),
        spacing=str(sampling.get("sigma_spacing", "cosine")),
    )
    coarse_steps = min(coarse_steps, max(int(sigmas.shape[-1]) - 2, 1))
    high_sigmas, low_sigmas = SplitSigmas.execute(sigmas=sigmas, step=coarse_steps)
    coarse_pass = SamplerCustomAdvanced.execute(
        noise=noise,
        guider=guider,
        sampler=sampler,
        sigmas=high_sigmas,
        latent_image=latent,
    )

    negative = comfy_nodes.ConditioningZeroOut().zero_out(conditioning=conditioned)[0]
    refined_latent, refined_positive, refined_negative = refine_av_latent(
        coarse_pass[1],
        conditioned,
        negative,
        model_name=str(model_profile.get("latent_upscale_model") or ""),
        scale=float(sampling.get("upscale_factor", 1.5)),
        device=str(sampling.get("upscale_device", "cuda")),
        precision=str(sampling.get("upscale_precision", "fp16")),
    )
    refine_guider = CFGGuider.execute(
        model=model,
        positive=refined_positive,
        negative=refined_negative,
        cfg=1.0,
    )[0]
    finished = SamplerCustomAdvanced.execute(
        noise=noise,
        guider=refine_guider,
        sampler=sampler,
        sigmas=low_sigmas,
        latent_image=refined_latent,
    )[0]
    return finished


class XYUEH3Generator(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_Generator",
            display_name=_display("本地 H3 生成器"),
            category=CATEGORY,
            description="调用已经完成 LoRA 与注意力处理的 H3 模型完成五种模式音画联合生成。",
            inputs=[
                MODEL_PROFILE.Input("model_profile", display_name="模型配置"),
                GENERATION_PROFILE.Input("generation_profile", display_name="生成配置"),
                io.String.Input("prompt", display_name="正式 H3 提示词", multiline=True, dynamic_prompts=True),
                MATERIAL_PACK.Input("material_pack", display_name="参考素材包", optional=True),
                io.Image.Input("first_frame", display_name="首帧", optional=True),
                io.Image.Input("last_frame", display_name="尾帧", optional=True),
                io.Model.Input("prepared_model", display_name="LoRA 与注意力模型"),
                io.Video.Input("motion_context", display_name="上一镜动作音频上下文", optional=True),
            ],
            is_output_node=True,
            outputs=[io.Video.Output(display_name="生成视频"), io.Image.Output(display_name="画面帧"), io.Audio.Output(display_name="生成音频"), io.String.Output(display_name="生成报告"), MOTION_CONTEXT.Output(display_name="动作音频上下文")],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def execute(cls, model_profile, generation_profile, prompt, prepared_model, material_pack=None, first_frame=None, last_frame=None, motion_context=None, unique_id=None):
        model_profile = dict(model_profile or {})
        generation_profile = dict(generation_profile or {})
        stage_name = str(generation_profile.get("stage_name") or "第一阶段")
        stage_count = max(1, min(MAX_STAGES, int(generation_profile.get("stage_count") or 3)))
        if _stage_number(stage_name) > stage_count:
            report = {
                "schema": "xyue-h3/generation-report-v1",
                "mode": str(model_profile.get("mode")),
                "stage": stage_name,
                "stage_count": stage_count,
                "status": "disabled",
            }
            return io.NodeOutput(None, None, None, json.dumps(report, ensure_ascii=False, indent=2), None)
        mode = str(model_profile.get("mode"))
        mode = normalize_mode(mode)
        if model_profile.get("schema") != MODEL_PROFILE_SCHEMA or generation_profile.get("schema") != GENERATION_PROFILE_SCHEMA:
            raise ValueError("请连接 XYUE H3 模式模型选择器和生成参数节点")
        if mode in {"I2VA", "FL2VA"} and first_frame is None:
            raise ValueError(f"{mode} 必须连接首帧")
        if mode in {"FL2VA", "L2VA"} and last_frame is None:
            raise ValueError(f"{mode} 必须连接尾帧")
        has_material = any((material_pack or {}).get(key, {}).get("entries") for key in ("images", "videos", "audios"))
        if mode in {"T2VA", "I2VA", "FL2VA", "L2VA"} and has_material:
            raise ValueError("首尾帧模式不能同时连接参考素材包")
        if mode == "Ref2VA" and (first_frame is not None or last_frame is not None):
            raise ValueError("Ref2VA 不能同时连接首帧或尾帧")
        if mode == "Ref2VA" and not any((material_pack or {}).get(key, {}).get("entries") for key in ("images", "videos", "audios")):
            raise ValueError("Ref2VA 至少需要一项启用参考素材")

        registry = (material_pack or {}).get("registry") if isinstance(material_pack, dict) else None
        prompt, _ = compile_draft(
            str(prompt),
            mode,
            registry,
            float(generation_profile.get("duration", 5)),
        )

        model = prepared_model
        clip = comfy_nodes.CLIPLoader().load_clip(model_profile["language_model"], "minimax", "default")[0]
        video_vae = comfy_nodes.VAELoader().load_vae(model_profile["video_vae"])[0]
        audio_vae = comfy_nodes.VAELoader().load_vae(model_profile["audio_vae"])[0]
        model = attach_preview(
            model,
            tiny_vae=str(model_profile.get("tiny_vae") or "none"),
            unique_id=unique_id,
            preview_frames=12,
            preview_fps=12,
        )
        width = int(generation_profile["width"])
        height = int(generation_profile["height"])
        target_width = int(generation_profile.get("target_width", width))
        target_height = int(generation_profile.get("target_height", height))
        length = int(generation_profile["frames"])
        if mode == "Ref2VA":
            references = _reference_payload(dict(material_pack or {}))
            conditioned, latent = MiniMaxH3ReferenceToVideo.execute(
                clip=clip, vae=video_vae, audio_vae=audio_vae, prompt=str(prompt), width=width, height=height, length=length,
                ref_image_size=str(generation_profile.get("reference_size", "match")), **references,
            )
        else:
            conditioned, latent = MiniMaxH3ImageToVideo.execute(
                clip=clip, vae=video_vae, prompt=str(prompt), width=width, height=height, length=length,
                first_frame=first_frame if mode in {"I2VA", "FL2VA"} else None,
                last_frame=last_frame if mode in {"FL2VA", "L2VA"} else None,
            )
        trim_frames = 0
        if motion_context is not None:
            components = motion_context.get_components()
            previous_context = {
                "schema": "xyue-h3/motion-context-media-v1",
                "frames": components.images,
                "audio": components.audio,
                "width": width,
                "height": height,
            }
            conditioned, trim_frames = apply_motion_context(
                conditioned,
                video_vae,
                audio_vae,
                latent,
                previous_context,
                context_length=22,
                audio_context_length=24,
            )
        guider = BasicGuider.execute(model=model, conditioning=conditioned)[0]
        sampler_name = "euler"
        sampler = KSamplerSelect.execute(sampler_name)[0]
        sampling = dict(generation_profile.get("sampling") or {})
        joint_steps = int(generation_profile.get("joint_steps") or max(generation_profile["video_steps"], generation_profile["audio_steps"]))
        sampling["base_steps"] = joint_steps
        sigmas = BasicScheduler.execute(
            model=model,
            scheduler=str(generation_profile["scheduler"]),
            steps=joint_steps,
            denoise=float(sampling.get("denoise", DEFAULT_DENOISE)),
        )[0]
        noise = RandomNoise.execute(noise_seed=int(generation_profile["seed"]))[0]
        finished = _sample_av(
            model=model,
            conditioned=conditioned,
            guider=guider,
            sampler=sampler,
            sigmas=sigmas,
            latent=latent,
            noise=noise,
            sampling=sampling,
            target_width=target_width,
            target_height=target_height,
            model_profile=model_profile,
        )
        images = comfy_nodes.VAEDecode().decode(video_vae, finished)[0]
        audio = VAEDecodeAudio.execute(audio_vae, finished)[0]
        images, audio = trim_motion_context(images, audio, trim_frames)
        video = CreateVideo.execute(images=images, fps=24.0, audio=audio, bit_depth=10)[0]
        next_motion_context = {
            "schema": "xyue-h3/motion-context-v2",
            "final_latent": finished,
            "frames": images,
            "audio": audio,
            "width": target_width,
            "height": target_height,
        }
        report = {
            "schema": "xyue-h3/generation-report-v1",
            "mode": mode,
            "canvas": f"{target_width}x{target_height}",
            "base_canvas": f"{width}x{height}",
            "frames": length,
            "video_steps": int(generation_profile["video_steps"]),
            "audio_steps": int(generation_profile["audio_steps"]),
            "joint_steps": joint_steps,
            "seed": int(generation_profile["seed"]),
            "sampling": sampling,
            "sampler": sampler_name,
            "lora_enabled": bool(model_profile.get("lora_enabled")),
            "lora_name": model_profile.get("lora_name"),
            "attention_mode": model_profile.get("attention_mode"),
            "experimental_resolution": bool(generation_profile.get("experimental_resolution")),
            "motion_context": bool(motion_context is not None),
            "motion_context_trim_frames": int(trim_frames),
            "status": "passed",
        }
        return io.NodeOutput(video, images, audio, json.dumps(report, ensure_ascii=False, indent=2), next_motion_context)


class XYUEH3LastFrameExtractor(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_LastFrameExtractor",
            display_name=_display("视频尾帧截取"),
            category=CATEGORY,
            description="从视频末尾取出最后一帧或倒数第 N 帧，用于 L2VA/FL2VA 后续生成。",
            inputs=[io.Video.Input("video", display_name="视频"), io.Int.Input("offset_frames", display_name="倒数第 N 帧", default=1, min=1, max=24, step=1)],
            outputs=[io.Image.Output(display_name="尾帧"), io.String.Output(display_name="视频信息")],
        )

    @classmethod
    def execute(cls, video, offset_frames):
        components = video.get_components()
        frames = components.images
        index = max(0, frames.shape[0] - int(offset_frames))
        report = {"frames": int(frames.shape[0]), "fps": float(components.frame_rate), "duration": float(frames.shape[0] / float(components.frame_rate)), "selected_index": index}
        frame = frames[index:index + 1].contiguous()
        return io.NodeOutput(frame, json.dumps(report, ensure_ascii=False, indent=2), ui=ui.PreviewImage(frame))


GENERATION_NODE_CLASSES = [
    XYUEH3ModeModelSelector,
    XYUEH3GenerationProfile,
    XYUEH3StudioController,
    XYUEH3StageGenerationProfile,
    XYUEH3Generator,
    XYUEH3LastFrameExtractor,
]
