"""Concatenate saved drama stages, save the result, and expose a ComfyUI preview."""

from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

import torch
import torch.nn.functional as F

from comfy_api.latest import InputImpl, Types, io, ui

from ..core.contracts import CATEGORY, MAX_STAGES, STUDIO_CONTROL_SCHEMA
from ..services.video_checkpoints import save_stage_video


TARGET_FPS = Fraction(24, 1)
STUDIO_CONTROL = io.Custom("XYUE_H3_STUDIO_CONTROL")


def _stage_count(studio_control) -> int:
    control = dict(studio_control or {})
    if control.get("schema") != STUDIO_CONTROL_SCHEMA:
        return 3
    return max(1, min(MAX_STAGES, int(control.get("stage_count", 3))))


def _frames_at_rate(frames: torch.Tensor, source_rate: Fraction) -> torch.Tensor:
    """Convert a frame batch to 24 FPS while preserving the source duration."""

    if frames.shape[0] == 0 or source_rate == TARGET_FPS:
        return frames
    duration = frames.shape[0] / float(source_rate)
    target_count = max(1, round(duration * float(TARGET_FPS)))
    indices = torch.linspace(0, frames.shape[0] - 1, target_count, device=frames.device).round().long()
    return frames.index_select(0, indices)


def _fit_frames(frames: torch.Tensor, height: int, width: int) -> torch.Tensor:
    if frames.shape[1:3] == (height, width):
        return frames
    nchw = frames.permute(0, 3, 1, 2).float()
    resized = F.interpolate(nchw, size=(height, width), mode="bilinear", align_corners=False)
    return resized.permute(0, 2, 3, 1).contiguous()


def _resample_audio(waveform: torch.Tensor, source_rate: int, target_rate: int) -> torch.Tensor:
    if source_rate == target_rate:
        return waveform
    target_samples = max(1, round(waveform.shape[-1] * target_rate / source_rate))
    return F.interpolate(waveform.float(), size=target_samples, mode="linear", align_corners=False)


def concatenate_videos(videos: list[Any]):
    """Build one 24 FPS VideoInput from the enabled stage VideoInputs."""

    components = [video.get_components() for video in videos]
    first = components[0]
    height, width = int(first.images.shape[1]), int(first.images.shape[2])
    frame_parts = [
        _fit_frames(_frames_at_rate(item.images, item.frame_rate), height, width).float()
        for item in components
    ]
    frames = torch.cat(frame_parts, dim=0).contiguous()

    audio_items = [item.audio for item in components]
    available = [audio for audio in audio_items if audio is not None]
    audio = None
    if available:
        target_rate = int(available[0]["sample_rate"])
        target_channels = max(int(item["waveform"].shape[1]) for item in available)
        audio_parts = []
        for item, audio_item in zip(components, audio_items):
            duration_samples = max(1, round(item.images.shape[0] / float(item.frame_rate) * target_rate))
            if audio_item is None:
                part = torch.zeros((1, target_channels, duration_samples), dtype=torch.float32)
            else:
                part = _resample_audio(audio_item["waveform"], int(audio_item["sample_rate"]), target_rate)
                if part.shape[1] < target_channels:
                    part = F.pad(part, (0, 0, 0, target_channels - part.shape[1]))
                elif part.shape[1] > target_channels:
                    part = part[:, :target_channels]
                part = part[..., :duration_samples]
                if part.shape[-1] < duration_samples:
                    part = F.pad(part, (0, duration_samples - part.shape[-1]))
            audio_parts.append(part)
        audio = {"waveform": torch.cat(audio_parts, dim=-1).contiguous(), "sample_rate": target_rate}

    return InputImpl.VideoFromComponents(
        Types.VideoComponents(images=frames, frame_rate=TARGET_FPS, audio=audio),
        bit_depth=10,
    ), components


class XYUEH3VideoConcat(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_VideoConcat",
            display_name="XYUE_多段视频合成并预览",
            category=CATEGORY,
            description="按启用阶段顺序拼接视频，统一为 24 FPS，自动保存并直接显示预览。",
            inputs=[
                io.Video.Input("stage1_video", display_name="第一阶段视频"),
                io.Video.Input("stage2_video", display_name="第二阶段视频", optional=True, lazy=True),
                io.Video.Input("stage3_video", display_name="第三阶段视频", optional=True, lazy=True),
                io.Video.Input("stage4_video", display_name="第四阶段视频", optional=True, lazy=True),
                io.Video.Input("stage5_video", display_name="第五阶段视频", optional=True, lazy=True),
                io.String.Input("filename_prefix", display_name="最终保存路径", default="xyue_h3/短剧/最终合成", multiline=False),
                io.Combo.Input("format", display_name="封装格式", options=Types.VideoContainer.as_input(), default="mp4"),
                io.Combo.Input("codec", display_name="视频编码", options=Types.VideoCodec.as_input(), default="h264"),
                STUDIO_CONTROL.Input("studio_control", display_name="阶段控制", optional=True),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            outputs=[io.Video.Output(display_name="最终合成视频"), io.String.Output(display_name="合成报告")],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, stage1_video, stage2_video=None, stage3_video=None, stage4_video=None, stage5_video=None,
                          filename_prefix="xyue_h3/短剧/最终合成", format="mp4", codec="h264", studio_control=None):
        count = _stage_count(studio_control)
        videos = (stage1_video, stage2_video, stage3_video, stage4_video, stage5_video)
        needed = [f"stage{index}_video" for index in range(2, count + 1) if videos[index - 1] is None]
        return needed or None

    @classmethod
    def execute(cls, stage1_video, stage2_video=None, stage3_video=None, stage4_video=None, stage5_video=None,
                filename_prefix="xyue_h3/短剧/最终合成", format="mp4", codec="h264", studio_control=None):
        all_videos = (stage1_video, stage2_video, stage3_video, stage4_video, stage5_video)
        videos = list(all_videos[:_stage_count(studio_control)])
        if any(video is None for video in videos):
            raise ValueError("启用阶段缺少视频输出。")
        video, components = concatenate_videos(videos)
        saved = save_stage_video(
            video,
            filename_prefix,
            format,
            codec,
            prompt=cls.hidden.prompt,
            extra_pnginfo=cls.hidden.extra_pnginfo,
        )
        durations = [float(item.images.shape[0] / float(item.frame_rate)) for item in components]
        report = {
            "schema": "xyue-h3/final-video-v1",
            "stages": len(videos),
            "stage_durations": durations,
            "total_duration": sum(durations),
            "fps": int(TARGET_FPS),
            "frames": int(video.get_components().images.shape[0]),
            "file": saved.full_path,
            "status": "saved_and_previewed",
        }
        preview = ui.PreviewVideo([ui.SavedResult(saved.file, saved.subfolder, io.FolderType.output)])
        return io.NodeOutput(video, json.dumps(report, ensure_ascii=False, indent=2), ui=preview)


VIDEO_CONCAT_NODE_CLASSES = [XYUEH3VideoConcat]
