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
from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo
from comfy_extras.nodes_video import CreateVideo

from ..core.contracts import CATEGORY, GENERATION_PROFILE_SCHEMA, GLOBAL_ACCELERATION_CONTROL_SCHEMA, MAX_STAGES, MODE_OPTIONS, MODEL_PROFILE_SCHEMA, STUDIO_CONTROL_SCHEMA, normalize_acceleration_mode, normalize_mode
from ..core.generation_options import (
    DEFAULT_DURATION,
    DEFAULT_REFERENCE_SIZE,
    DEFAULT_SAMPLING_MODE,
    DEFAULT_SAMPLING_PRESET,
    DEFAULT_SCHEDULER,
    DEFAULT_STEPS,
    MIN_AUDIO_STEPS,
    MAX_STEPS,
    MIN_STEPS,
    REFERENCE_SIZE_OPTIONS,
    SAMPLING_PRESET_OPTIONS,
    SCHEDULER_OPTIONS,
    normalize_reference_size,
    normalize_scheduler,
    resolve_sampling,
    sampler_for_acceleration,
)
from ..core.latent_refine import refine_av_latent
from ..core.preview import attach_preview
from ..core.resolution import ASPECTS, NATIVE_RESOLUTION, RESOLUTION_OPTIONS, align_duration, downscale_canvas, resolve_canvas
from ..core.sigma_refiner import refine_sigmas
from ..core.multi_stage_config import stage_values
from .assets import MATERIAL_PACK
from .checkpoints import _stage_number

MODEL_PROFILE = io.Custom("XYUE_H3_MODEL_PROFILE")
GENERATION_PROFILE = io.Custom("XYUE_H3_GENERATION_PROFILE")
STUDIO_CONTROL = io.Custom("XYUE_H3_STUDIO_CONTROL")
MULTI_STAGE_CONFIG = io.Custom("XYUE_H3_MULTI_STAGE_CONFIG")


def _display(name: str) -> str:
    return f"XYUE_{name}"


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


def _profile_with_overrides(
    aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
    sampling_preset, sampling_mode, coarse_steps, upscale_factor, refine_pass, extend_sigmas,
    overrides: dict[str, Any] | None,
):
    values = dict(overrides or {})
    sampling = dict(values.get("sampling") or {})
    return XYUEH3GenerationProfile.execute(
        values.get("aspect", aspect),
        values.get("resolution", resolution),
        values.get("duration", duration),
        values.get("steps", steps),
        values.get("audio_steps", audio_steps),
        values.get("scheduler", scheduler),
        values.get("seed", seed),
        values.get("reference_size", reference_size),
        values.get("sampling_preset", sampling.get("sampling_preset", sampling_preset)),
        sampling.get("sampling_mode", sampling_mode),
        sampling.get("coarse_steps", coarse_steps),
        sampling.get("upscale_factor", upscale_factor),
        sampling.get("refine_pass", refine_pass),
        sampling.get("extend_sigmas", extend_sigmas),
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
            ],
            outputs=[MODEL_PROFILE.Output(display_name="模型配置"), io.String.Output(display_name="模型报告"), io.Model.Output(display_name="主模型")],
        )

    @classmethod
    def execute(cls, mode, base_model, reference_model, language_model, video_vae, audio_vae, latent_upscale_model="", tiny_vae="none"):
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
        }
        model = None
        if profile["main_model"]:
            model = comfy_nodes.UNETLoader().load_unet(profile["main_model"], "default")[0]
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
                io.Combo.Input("resolution", display_name="分辨率", options=list(RESOLUTION_OPTIONS), default=NATIVE_RESOLUTION),
                io.Int.Input("duration", display_name="时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("steps", display_name="视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1,
                             tooltip="视频扩散采样次数。默认 12；更高通常更精细，但生成更慢。"),
                 io.Int.Input("audio_steps", display_name="音频步数", default=DEFAULT_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1,
                             tooltip="音频扩散采样次数，可与视频步数独立设置。默认 12。"),
                io.Combo.Input("scheduler", display_name="调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="控制去噪步在噪声区间中的分布。简单稳定适合作为默认；Beta 偏重动态细节；标准均衡用于对照。"),
                io.Int.Input("seed", display_name="随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="默认每次生成后随机；下拉菜单可切换为固定、递增或递减。"),
                io.Combo.Input("reference_size", display_name="参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                                tooltip="适配生成画布会缩放参考图并节省显存；保留参考图细节会使用更大参考尺寸并增加显存占用。"),
                io.Combo.Input("sampling_preset", display_name="采样方式预设", options=list(SAMPLING_PRESET_OPTIONS), default=DEFAULT_SAMPLING_PRESET,
                                tooltip="预设档位会锁定验证过的采样参数。"),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[GENERATION_PROFILE.Output(display_name="生成配置"), io.Int.Output(display_name="宽"), io.Int.Output(display_name="高"), io.Int.Output(display_name="帧数"), io.String.Output(display_name="参数报告")],
        )

    @classmethod
    def execute(cls, aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
                 sampling_preset=DEFAULT_SAMPLING_PRESET, sampling_mode=DEFAULT_SAMPLING_MODE, coarse_steps=2,
                 upscale_factor=1.2, refine_pass=True, extend_sigmas=2, multi_stage_config=None):
        _, configured_values = stage_values(multi_stage_config, 1)
        if configured_values is not None:
            return _profile_with_overrides(
                aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
                sampling_preset, sampling_mode, coarse_steps, upscale_factor, refine_pass, extend_sigmas,
                configured_values,
            )
        target_width, target_height, experimental = resolve_canvas(str(aspect), str(resolution))
        frames, effective_duration = align_duration(int(duration))
        if not MIN_STEPS <= int(steps) <= MAX_STEPS:
            raise ValueError(f"H3 视频步数必须在 {MIN_STEPS}–{MAX_STEPS} 之间")
        sampling = resolve_sampling(sampling_preset, sampling_mode, coarse_steps, upscale_factor, refine_pass, extend_sigmas)
        width, height = target_width, target_height
        if sampling["mode"] == "dual":
            width, height = downscale_canvas(target_width, target_height, sampling["upscale_factor"])
        profile = {
            "schema": GENERATION_PROFILE_SCHEMA,
            "aspect": str(aspect),
            "resolution": str(resolution),
            "width": width,
            "height": height,
            "target_width": target_width,
            "target_height": target_height,
            "duration": int(duration),
            "effective_duration": effective_duration,
            "frames": frames,
            "steps": int(steps),
            "audio_steps": int(audio_steps),
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
                io.Combo.Input("resolution", display_name="分辨率", options=list(RESOLUTION_OPTIONS), default=NATIVE_RESOLUTION),
                io.Int.Input("duration", display_name="全局时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("steps", display_name="全局视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1),
                 io.Int.Input("audio_steps", display_name="全局音频步数", default=DEFAULT_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1),
                io.Combo.Input("scheduler", display_name="全局调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="统一控制各阶段的去噪步分布。简单稳定适合作为默认。"),
                io.Int.Input("seed", display_name="全局随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="默认每次生成后随机；关闭全局控制时，各阶段使用自己的随机种子。"),
                io.Combo.Input("reference_size", display_name="全局参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                               tooltip="适配画布更省显存；保留细节会提高参考图处理尺寸。"),
                io.Combo.Input("sampling_preset", display_name="全局采样方式预设", options=list(SAMPLING_PRESET_OPTIONS), default=DEFAULT_SAMPLING_PRESET,
                               tooltip="预设档位会锁定验证过的采样参数。"),
                io.Int.Input("stage_count", display_name="启用阶段数", default=3, min=1, max=MAX_STAGES, step=1,
                 tooltip="只运行前 N 个阶段，后续阶段惰性跳过。"),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[STUDIO_CONTROL.Output(display_name="全局控制"), io.String.Output(display_name="控制器报告")],
        )

    @classmethod
    def execute(cls, global_enabled, aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
                 sampling_preset=DEFAULT_SAMPLING_PRESET, sampling_mode=DEFAULT_SAMPLING_MODE, coarse_steps=2,
                 upscale_factor=1.2, refine_pass=True, extend_sigmas=2, stage_count=3, multi_stage_config=None):
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
            aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
            sampling_preset, sampling_mode, coarse_steps, upscale_factor, refine_pass, extend_sigmas,
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
                io.Combo.Input("resolution", display_name="本阶段分辨率", options=list(RESOLUTION_OPTIONS), default=NATIVE_RESOLUTION),
                io.Int.Input("duration", display_name="本阶段时长（秒）", default=DEFAULT_DURATION, min=1, max=15, step=1),
                io.Int.Input("steps", display_name="本阶段视频步数", default=DEFAULT_STEPS, min=MIN_STEPS, max=MAX_STEPS, step=1),
                 io.Int.Input("audio_steps", display_name="本阶段音频步数", default=DEFAULT_STEPS, min=MIN_AUDIO_STEPS, max=MAX_STEPS, step=1),
                io.Combo.Input("scheduler", display_name="本阶段调度器", options=list(SCHEDULER_OPTIONS), default=DEFAULT_SCHEDULER,
                               tooltip="仅在全局控制关闭时生效。简单稳定适合作为默认。"),
                io.Int.Input("seed", display_name="本阶段随机种子", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True,
                             tooltip="每次生成后自动随机；仅在全局控制关闭时生效。"),
                io.Combo.Input("reference_size", display_name="本阶段参考图策略", options=list(REFERENCE_SIZE_OPTIONS), default=DEFAULT_REFERENCE_SIZE,
                               tooltip="仅在全局控制关闭时生效。适配画布更省显存，保留细节会占用更多显存。"),
                io.Combo.Input("sampling_preset", display_name="本阶段采样方式预设", options=list(SAMPLING_PRESET_OPTIONS), default=DEFAULT_SAMPLING_PRESET,
                               tooltip="预设档位会锁定验证过的采样参数。仅在全局控制关闭时生效。"),
                io.String.Input("stage_name", display_name="阶段名称", default="第一阶段", multiline=False,
                                 tooltip="控制器启用的阶段数之外的本阶段会被跳过，不加载模型不采样。"),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[GENERATION_PROFILE.Output(display_name="阶段生成配置"), io.String.Output(display_name="阶段参数报告")],
        )

    @classmethod
    def execute(cls, studio_control=None, aspect="16:9", resolution=NATIVE_RESOLUTION, duration=DEFAULT_DURATION,
                 steps=DEFAULT_STEPS, audio_steps=DEFAULT_STEPS, scheduler=DEFAULT_SCHEDULER, seed=0,
                 reference_size=DEFAULT_REFERENCE_SIZE, sampling_preset=DEFAULT_SAMPLING_PRESET,
                 sampling_mode=DEFAULT_SAMPLING_MODE, coarse_steps=2, upscale_factor=1.2, refine_pass=True,
                 extend_sigmas=2, stage_name="第一阶段", multi_stage_config=None):
        config = dict(multi_stage_config or {})
        config_values = None
        if config.get("schema") == "xyue.h3.multi-stage-cloud-config/v1":
            stage_index = _stage_number(stage_name)
            _, config_values = stage_values(config, stage_index)
            if bool((config.get("generation") or {}).get("global_enabled")):
                config_values = dict((config.get("generation") or {}).get("global") or config_values or {})
        local_profile, *_ = _profile_with_overrides(
            aspect, resolution, duration, steps, audio_steps, scheduler, seed, reference_size,
            sampling_preset, sampling_mode, coarse_steps, upscale_factor, refine_pass, extend_sigmas, config_values,
        )
        control = dict(studio_control or {})
        if control.get("schema") != STUDIO_CONTROL_SCHEMA:
            selected = local_profile
            source = "阶段独立"
            stage_count = 3
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
    """Run single sampling or the official H3 learned-upscale two-pass flow."""

    if str(sampling.get("mode") or "single") != "dual":
        return SamplerCustomAdvanced.execute(
            noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent
        )[0]

    coarse_steps = max(1, int(sampling.get("coarse_steps") or 2))
    sigmas = refine_sigmas(
        sigmas,
        extra_steps=max(0, int(sampling.get("extend_sigmas") or 0)),
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
        target_width=int(target_width),
        target_height=int(target_height),
        device=str(sampling.get("upscale_device", "cuda")),
        precision=str(sampling.get("upscale_precision", "auto")),
        align=int(sampling.get("upscale_align", 2)),
    )
    refine_guider = CFGGuider.execute(
        model=model,
        positive=refined_positive,
        negative=refined_negative,
        cfg=1.0,
    )[0]
    return SamplerCustomAdvanced.execute(
        noise=noise,
        guider=refine_guider,
        sampler=sampler,
        sigmas=low_sigmas,
        latent_image=refined_latent,
    )[0]


class XYUEH3Generator(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_Generator",
            display_name=_display("本地 H3 生成器"),
            category=CATEGORY,
            description="调用本地 H3 模型完成五种模式的音画联合生成；可接入 LoRA 与 TE-Speed 模型链，不自动保存文件。",
            inputs=[
                MODEL_PROFILE.Input("model_profile", display_name="模型配置"),
                GENERATION_PROFILE.Input("generation_profile", display_name="生成配置"),
                io.String.Input("prompt", display_name="正式 H3 提示词", multiline=True, dynamic_prompts=True, force_input=True),
                MATERIAL_PACK.Input("material_pack", display_name="参考素材包", optional=True),
                io.Image.Input("first_frame", display_name="首帧", optional=True),
                io.Image.Input("last_frame", display_name="尾帧", optional=True),
                io.Model.Input("accelerated_model", display_name="加速后模型", optional=True),
                io.Custom("XYUE_H3_GLOBAL_ACCELERATION_CONTROL").Input("global_acceleration", display_name="全局加速模式", optional=True),
            ],
            is_output_node=True,
            outputs=[io.Video.Output(display_name="生成视频"), io.Image.Output(display_name="画面帧"), io.Audio.Output(display_name="生成音频"), io.String.Output(display_name="生成报告")],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def execute(cls, model_profile, generation_profile, prompt, material_pack=None, first_frame=None, last_frame=None, accelerated_model=None, global_acceleration=None, unique_id=None):
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
            return io.NodeOutput(None, None, None, json.dumps(report, ensure_ascii=False, indent=2))
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

        model = accelerated_model
        if model is None:
            model = comfy_nodes.UNETLoader().load_unet(model_profile["main_model"], "default")[0]
        clip = comfy_nodes.CLIPLoader().load_clip(model_profile["language_model"], "minimax", "default")[0]
        video_vae = comfy_nodes.VAELoader().load_vae(model_profile["video_vae"])[0]
        audio_vae = comfy_nodes.VAELoader().load_vae(model_profile["audio_vae"])[0]
        model = attach_preview(
            model,
            tiny_vae=str(model_profile.get("tiny_vae") or "none"),
            unique_id=unique_id,
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
        guider = BasicGuider.execute(model=model, conditioning=conditioned)[0]
        acceleration = dict(global_acceleration or {})
        acceleration_mode = normalize_acceleration_mode(acceleration.get("mode")) if acceleration.get("schema") == GLOBAL_ACCELERATION_CONTROL_SCHEMA else "不启用"
        sampler_name = sampler_for_acceleration(acceleration_mode)
        sampler = KSamplerSelect.execute(sampler_name)[0]
        sigmas = BasicScheduler.execute(model=model, scheduler=str(generation_profile["scheduler"]), steps=int(generation_profile["steps"]), denoise=1.0)[0]
        noise = RandomNoise.execute(noise_seed=int(generation_profile["seed"]))[0]
        sampling = dict(generation_profile.get("sampling") or {})
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
        video = CreateVideo.execute(images=images, fps=24.0, audio=audio, bit_depth=10)[0]
        report = {
            "schema": "xyue-h3/generation-report-v1",
            "mode": mode,
            "canvas": f"{target_width}x{target_height}",
            "base_canvas": f"{width}x{height}",
            "frames": length,
            "steps": int(generation_profile["steps"]),
            "audio_steps": int(generation_profile.get("audio_steps", generation_profile["steps"])),
            "seed": int(generation_profile["seed"]),
            "sampling": sampling,
            "sampler": sampler_name,
            "acceleration_mode": acceleration_mode,
            "experimental_resolution": bool(generation_profile.get("experimental_resolution")),
            "accelerated_model": accelerated_model is not None,
            "status": "passed",
        }
        return io.NodeOutput(video, images, audio, json.dumps(report, ensure_ascii=False, indent=2))


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
