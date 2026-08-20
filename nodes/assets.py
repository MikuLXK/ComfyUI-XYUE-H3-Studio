"""Image, video, audio, and material manager nodes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import torch
import folder_paths
import nodes as comfy_nodes
import comfy.utils
from comfy_api.latest import io
from comfy_extras.nodes_audio import load as load_audio
from comfy_extras.nodes_video import LoadVideo

from ..core.contracts import (
    ALIAS_MODES,
    AUDIO_ITEM_SCHEMA,
    AUDIO_PACK_SCHEMA,
    AUDIO_ANCHOR_TYPES,
    CATEGORY,
    IMAGE_ITEM_SCHEMA,
    IMAGE_PACK_SCHEMA,
    IMAGE_ROLES,
    IMAGE_FIT_MODES,
    MATERIAL_PACK_SCHEMA,
    MAX_AUDIOS,
    MAX_PICTURES,
    MAX_VIDEOS,
    VIDEO_ROLES,
    VIDEO_ITEM_SCHEMA,
    VIDEO_PACK_SCHEMA,
)
from ..core.materials import build_audio_pack, build_image_pack, build_material_pack, build_video_pack
from ..core.reference_limits import validate_reference_limits

IMAGE_ITEM = io.Custom("XYUE_H3_IMAGE_ITEM")
IMAGE_PACK = io.Custom("XYUE_H3_IMAGE_PACK")
VIDEO_ITEM = io.Custom("XYUE_H3_VIDEO_ITEM")
VIDEO_PACK = io.Custom("XYUE_H3_VIDEO_PACK")
AUDIO_ITEM = io.Custom("XYUE_H3_AUDIO_ITEM")
AUDIO_PACK = io.Custom("XYUE_H3_AUDIO_PACK")
MATERIAL_PACK = io.Custom("XYUE_H3_MATERIAL_PACK")
MENTION_REGISTRY = io.Custom("XYUE_H3_MENTION_REGISTRY")
NO_IMAGE_SELECTED = "未选择图片"
NO_VIDEO_SELECTED = "未选择视频"
NO_AUDIO_SELECTED = "未选择音频"


def _display(name: str) -> str:
    return f"XYUE_{name}"


def _files(kind: str) -> list[str]:
    input_dir = folder_paths.get_input_directory()
    names = [name for name in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, name))]
    return sorted(folder_paths.filter_files_content_types(names, [kind]))


def _audio_files() -> list[str]:
    """Match ComfyUI's native Load Audio sources, including video soundtracks."""

    input_dir = folder_paths.get_input_directory()
    names = [name for name in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, name))]
    return sorted(folder_paths.filter_files_content_types(names, ["audio", "video"]))


def _is_unselected(value: Any, sentinel: str) -> bool:
    return str(value or "").strip() in {"", sentinel}


def _trim_video(video: Any, start_time: float, duration: float) -> Any:
    if start_time <= 0 and duration <= 0:
        return video
    trimmed = video.as_trimmed(float(start_time), float(duration), strict_duration=True)
    if trimmed is None:
        raise ValueError("视频裁剪范围超出源视频时长")
    return trimmed


def _video_components(video: Any) -> tuple[torch.Tensor, dict[str, Any] | None, float]:
    components = video.get_components()
    frames = components.images
    audio = components.audio
    fps = float(components.frame_rate)
    if fps <= 0:
        fps = 24.0
    if abs(fps - 24.0) > 0.001 and frames.shape[0] > 1:
        count = max(1, int(round(frames.shape[0] * 24.0 / fps)))
        indices = torch.linspace(0, frames.shape[0] - 1, count).round().long()
        frames = frames[indices]
        fps = 24.0
    return frames, audio, fps


def _fit_image(image: torch.Tensor, fit_mode: str) -> torch.Tensor:
    """Normalize the image tensor without changing its batch/channel contract."""
    if fit_mode == "保持原图" or image.numel() == 0:
        return image
    height, width = int(image.shape[1]), int(image.shape[2])
    if fit_mode == "居中裁剪":
        side = min(height, width)
        top, left = (height - side) // 2, (width - side) // 2
        return image[:, top:top + side, left:left + side, :]
    if fit_mode == "留边适配":
        side = max(height, width)
        canvas = torch.zeros((image.shape[0], side, side, image.shape[-1]), dtype=image.dtype, device=image.device)
        top, left = (side - height) // 2, (side - width) // 2
        canvas[:, top:top + height, left:left + width, :] = image
        return canvas
    raise ValueError(f"不支持的图片适配策略：{fit_mode}")


def _fit_mask(mask: torch.Tensor, fit_mode: str, height: int, width: int) -> torch.Tensor:
    if fit_mode == "保持原图" or mask.numel() == 0:
        return mask
    if fit_mode == "居中裁剪":
        side = min(height, width)
        top, left = (height - side) // 2, (width - side) // 2
        return mask[:, top:top + side, left:left + side]
    side = max(height, width)
    canvas = torch.zeros((mask.shape[0], side, side), dtype=mask.dtype, device=mask.device)
    top, left = (side - height) // 2, (side - width) // 2
    canvas[:, top:top + height, left:left + width] = mask
    return canvas


class XYUEH3ImageAsset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_ImageAsset",
            display_name=_display("图片素材"),
            category=CATEGORY,
            description="导入图片，默认按启用顺序建立 @图片N 别名；关闭启用后不会参与素材编号。",
            inputs=[
                io.Combo.Input(
                    "image",
                    display_name="上传/选择图片",
                    options=[NO_IMAGE_SELECTED, *_files("image")],
                    default=NO_IMAGE_SELECTED,
                    upload=io.UploadType.image,
                ),
                io.Boolean.Input("enabled", display_name="启用图片", default=False, label_on="启用", label_off="禁止"),
                io.Combo.Input("alias_mode", display_name="别名模式", options=["@图片N", "@文件名"], default="@图片N"),
                io.Combo.Input("role", display_name="图片用途", options=list(IMAGE_ROLES), default=IMAGE_ROLES[0]),
                io.Combo.Input("fit_mode", display_name="适配策略", options=list(IMAGE_FIT_MODES), default="保持原图"),
            ],
            outputs=[
                IMAGE_ITEM.Output(display_name="图片素材项"),
                io.Image.Output(display_name="图片"),
                io.Mask.Output(display_name="遮罩"),
                io.Image.Output(display_name="参考图"),
            ],
        )

    @classmethod
    def execute(cls, image, enabled, alias_mode, role, fit_mode):
        if _is_unselected(image, NO_IMAGE_SELECTED):
            if enabled:
                raise ValueError("图片素材已启用，但尚未上传或选择图片文件")
            item = {
                "schema": IMAGE_ITEM_SCHEMA,
                "image": None,
                "enabled": False,
                "filename": "",
                "numbered_alias": str(alias_mode) == "@图片N",
                "role": str(role),
                "fit_mode": str(fit_mode),
            }
            return io.NodeOutput(item, None, None, None)
        loaded, mask = comfy_nodes.LoadImage().load_image(image)
        original_height, original_width = int(loaded.shape[1]), int(loaded.shape[2])
        loaded = _fit_image(loaded, str(fit_mode))
        mask = _fit_mask(mask, str(fit_mode), original_height, original_width)
        item = {
            "schema": IMAGE_ITEM_SCHEMA,
            "image": loaded,
            "enabled": bool(enabled),
            "filename": str(image),
            "numbered_alias": str(alias_mode) == "@图片N",
            "role": str(role),
            "fit_mode": str(fit_mode),
        }
        return io.NodeOutput(item, loaded, mask, loaded if enabled else None)

    @classmethod
    def fingerprint_inputs(cls, image, enabled, alias_mode, role, fit_mode):
        if _is_unselected(image, NO_IMAGE_SELECTED):
            return f"empty:{enabled}:{alias_mode}:{role}:{fit_mode}"
        return f"{comfy_nodes.LoadImage.IS_CHANGED(image)}:{int(bool(enabled))}:{alias_mode}:{role}:{fit_mode}"

    @classmethod
    def validate_inputs(cls, image, enabled, alias_mode, role, fit_mode):
        del alias_mode, role, fit_mode
        if _is_unselected(image, NO_IMAGE_SELECTED):
            return "图片素材已启用，但尚未上传或选择图片文件" if enabled else True
        return comfy_nodes.LoadImage.VALIDATE_INPUTS(image)


class XYUEH3ImageManager(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_ImageManager",
            display_name=_display("图片管理器"),
            category=CATEGORY,
            description="最多管理 9 张启用图片，并生成连续的 Picture 标签和 @ 引用表。",
            inputs=[IMAGE_ITEM.Input(f"image_{index}", display_name=f"图片{index}", optional=True) for index in range(1, MAX_PICTURES + 1)],
            outputs=[IMAGE_PACK.Output(display_name="图片素材包"), MENTION_REGISTRY.Output(display_name="图片引用表"), io.String.Output(display_name="图片清单")],
        )

    @classmethod
    def execute(cls, **kwargs):
        items = []
        for index in range(1, MAX_PICTURES + 1):
            item = kwargs.get(f"image_{index}")
            items.append({**item, "source_slot": index} if isinstance(item, dict) else item)
        pack, aliases = build_image_pack(items)
        registry = {"schema": "xyue-h3/mention-registry-v1", "alias_to_token": aliases, "token_to_alias": pack["token_to_alias"], "entries": pack["entries"]}
        lines = [f"{entry['alias']} → {entry['token']}｜{entry.get('role', '图片')}｜{entry.get('filename', '')}" for entry in pack["entries"]]
        return io.NodeOutput(pack, registry, "\n".join(lines) if lines else "未启用图片")


class XYUEH3VideoAsset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_VideoAsset",
            display_name=_display("视频素材"),
            category=CATEGORY,
            description="裁剪视频、选择是否携带原声，并输出可直接作为 H3 参考的视频和尾帧。",
            inputs=[
                io.Combo.Input(
                    "video",
                    display_name="上传/选择视频",
                    options=[NO_VIDEO_SELECTED, *_files("video")],
                    default=NO_VIDEO_SELECTED,
                    upload=io.UploadType.video,
                ),
                io.Boolean.Input("enabled", display_name="启用视频", default=False, label_on="启用", label_off="禁止"),
                io.Combo.Input("alias_mode", display_name="别名模式", options=["@视频N", "@文件名"], default="@视频N"),
                io.Combo.Input("role", display_name="视频用途", options=list(VIDEO_ROLES), default=VIDEO_ROLES[0]),
                io.Float.Input("start_time", display_name="起始秒", default=0.0, min=0.0, max=3600.0, step=0.01),
                io.Float.Input("duration", display_name="裁剪时长（0=全片）", default=0.0, min=0.0, max=3600.0, step=0.01),
                io.Boolean.Input("include_audio", display_name="包含原声", default=False, label_on="包含", label_off="忽略"),
            ],
            outputs=[
                VIDEO_ITEM.Output(display_name="视频素材项"),
                io.Video.Output(display_name="视频"),
                io.Image.Output(display_name="尾帧"),
                io.Audio.Output(display_name="原声"),
                io.Image.Output(display_name="参考帧"),
            ],
        )

    @classmethod
    def execute(cls, video, enabled, alias_mode, role, start_time, duration, include_audio):
        if _is_unselected(video, NO_VIDEO_SELECTED):
            if enabled:
                raise ValueError("视频素材已启用，但尚未上传或选择视频文件")
            item = {
                "schema": VIDEO_ITEM_SCHEMA,
                "video": None,
                "frames": None,
                "audio": None,
                "enabled": False,
                "filename": "",
                "numbered_alias": str(alias_mode) == "@视频N",
                "role": str(role),
                "fps": 24.0,
            }
            return io.NodeOutput(item, None, None, None, None)
        source = LoadVideo.execute(video)[0]
        trimmed = _trim_video(source, float(start_time), float(duration))
        frames, audio, fps = _video_components(trimmed)
        if not include_audio:
            audio = None
        item = {
            "schema": VIDEO_ITEM_SCHEMA,
            "video": trimmed,
            "frames": frames,
            "audio": audio,
            "enabled": bool(enabled),
            "filename": str(video),
            "numbered_alias": str(alias_mode) == "@视频N",
            "role": str(role),
            "fps": fps,
        }
        tail = frames[-1:].contiguous()
        return io.NodeOutput(item, trimmed, tail, audio, frames if enabled else None)

    @classmethod
    def fingerprint_inputs(cls, video, enabled, alias_mode, role, start_time, duration, include_audio):
        if _is_unselected(video, NO_VIDEO_SELECTED):
            return f"empty:{enabled}:{alias_mode}:{role}:{start_time}:{duration}:{include_audio}"
        path = folder_paths.get_annotated_filepath(video)
        return f"{os.path.getmtime(path)}:{os.path.getsize(path)}:{enabled}:{alias_mode}:{role}:{start_time}:{duration}:{include_audio}"

    @classmethod
    def validate_inputs(cls, video, enabled, alias_mode, role, start_time, duration, include_audio):
        del alias_mode, role, start_time, duration, include_audio
        if _is_unselected(video, NO_VIDEO_SELECTED):
            return "视频素材已启用，但尚未上传或选择视频文件" if enabled else True
        return True if folder_paths.exists_annotated_filepath(video) else f"视频不存在：{video}"


class XYUEH3VideoManager(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_VideoManager",
            display_name=_display("视频管理器"),
            category=CATEGORY,
            description="最多管理 3 个视频，编号为 Video N，并携带已选择的视频原声。",
            inputs=[VIDEO_ITEM.Input(f"video_{index}", display_name=f"视频{index}", optional=True) for index in range(1, MAX_VIDEOS + 1)],
            outputs=[VIDEO_PACK.Output(display_name="视频素材包"), MENTION_REGISTRY.Output(display_name="视频引用表"), io.String.Output(display_name="视频清单")],
        )

    @classmethod
    def execute(cls, **kwargs):
        items = [kwargs.get(f"video_{index}") for index in range(1, MAX_VIDEOS + 1)]
        active = [item for item in items if isinstance(item, dict) and item.get("enabled")]
        total = sum(float(item.get("video").get_duration()) for item in active if item.get("video") is not None)
        if any(float(item.get("video").get_duration()) < 2.0 or float(item.get("video").get_duration()) > 15.0 for item in active if item.get("video") is not None):
            raise ValueError("每个 H3 参考视频必须为 2–15 秒")
        if total > 15.0:
            raise ValueError(f"参考视频总时长不能超过 15 秒，当前为 {total:.2f} 秒")
        pack, aliases = build_video_pack(items)
        registry = {"schema": "xyue-h3/mention-registry-v1", "alias_to_token": aliases, "token_to_alias": pack["token_to_alias"], "entries": pack["entries"]}
        lines = [f"{entry['alias']} → {entry['token']}｜{entry.get('role', '视频')}｜{entry.get('filename', '')}" for entry in pack["entries"]]
        return io.NodeOutput(pack, registry, "\n".join(lines) if lines else "未启用视频")


class XYUEH3AudioAsset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_AudioAsset",
            display_name=_display("音频素材"),
            category=CATEGORY,
            description="建立声音锚点与具体角色/对象的映射，并完成裁剪、增益和归一化。",
            inputs=[
                io.Combo.Input(
                    "audio",
                    display_name="上传/选择音频",
                    options=[NO_AUDIO_SELECTED, *_audio_files()],
                    default=NO_AUDIO_SELECTED,
                    upload=io.UploadType.audio,
                ),
                io.Boolean.Input("enabled", display_name="启用音频", default=False, label_on="启用", label_off="禁止"),
                io.Combo.Input("alias_mode", display_name="别名模式", options=["@音频N", "@文件名"], default="@音频N"),
                io.Combo.Input("anchor_type", display_name="声音锚点类型", options=list(AUDIO_ANCHOR_TYPES), default=AUDIO_ANCHOR_TYPES[0]),
                io.String.Input("anchor_name", display_name="角色/对象名称", default="角色A", multiline=False),
                io.Float.Input("start_time", display_name="起始秒", default=0.0, min=0.0, max=3600.0, step=0.01),
                io.Float.Input("duration", display_name="裁剪时长（0=全片）", default=0.0, min=0.0, max=3600.0, step=0.01),
                io.Float.Input("gain_db", display_name="增益 dB", default=0.0, min=-24.0, max=24.0, step=0.1),
                io.Boolean.Input("normalize", display_name="峰值归一化", default=False, label_on="归一化", label_off="原始"),
            ],
            outputs=[
                AUDIO_ITEM.Output(display_name="音频素材项"),
                io.Audio.Output(display_name="音频"),
                io.Audio.Output(display_name="参考音频"),
            ],
        )

    @classmethod
    def execute(cls, audio, enabled, alias_mode, anchor_type, anchor_name, start_time, duration, gain_db, normalize):
        filename = str(audio).strip()
        if _is_unselected(filename, NO_AUDIO_SELECTED):
            if enabled:
                raise ValueError("音频素材已启用，但尚未上传或选择音频文件")
            item = {
                "schema": AUDIO_ITEM_SCHEMA,
                "audio": None,
                "enabled": False,
                "filename": "",
                "numbered_alias": str(alias_mode) == "@音频N",
                "anchor_type": str(anchor_type),
                "anchor_name": str(anchor_name).strip(),
                "anchor_label": f"{str(anchor_name).strip()}｜{str(anchor_type)}",
            }
            return io.NodeOutput(item, None, None)
        path = folder_paths.get_annotated_filepath(audio)
        waveform, sample_rate = load_audio(path)
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        start = max(0, int(float(start_time) * sample_rate))
        end = None if float(duration) <= 0 else start + int(float(duration) * sample_rate)
        waveform = waveform[:, start:end].clone()
        if normalize and waveform.numel():
            peak = float(waveform.abs().max())
            if peak > 0:
                waveform = waveform * (10 ** (-1 / 20)) / peak
        waveform = waveform * (10 ** (float(gain_db) / 20))
        audio_data = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
        item = {
            "schema": AUDIO_ITEM_SCHEMA,
            "audio": audio_data,
            "enabled": bool(enabled),
            "filename": str(audio),
            "numbered_alias": str(alias_mode) == "@音频N",
            "anchor_type": str(anchor_type),
            "anchor_name": str(anchor_name).strip(),
            "anchor_label": f"{str(anchor_name).strip()}｜{str(anchor_type)}",
        }
        return io.NodeOutput(item, audio_data, audio_data if enabled else None)

    @classmethod
    def fingerprint_inputs(cls, audio, enabled, alias_mode, anchor_type, anchor_name, start_time, duration, gain_db, normalize):
        if _is_unselected(audio, NO_AUDIO_SELECTED):
            return f"empty:{enabled}:{alias_mode}:{anchor_type}:{anchor_name}:{start_time}:{duration}:{gain_db}:{normalize}"
        path = folder_paths.get_annotated_filepath(audio)
        return f"{os.path.getmtime(path)}:{os.path.getsize(path)}:{enabled}:{alias_mode}:{anchor_type}:{anchor_name}:{start_time}:{duration}:{gain_db}:{normalize}"

    @classmethod
    def validate_inputs(cls, audio, enabled, alias_mode, anchor_type, anchor_name, start_time, duration, gain_db, normalize):
        del alias_mode, anchor_type, start_time, duration, gain_db, normalize
        if enabled and not str(anchor_name).strip():
            return "角色/对象名称不能为空"
        if _is_unselected(audio, NO_AUDIO_SELECTED):
            return "音频素材已启用，但尚未上传或选择音频文件" if enabled else True
        return True if folder_paths.exists_annotated_filepath(audio) else f"音频不存在：{audio}"


class XYUEH3AudioManager(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_AudioManager",
            display_name=_display("音频管理器"),
            category=CATEGORY,
            description="最多管理 3 个独立音频，编号为 Audio N。",
            inputs=[AUDIO_ITEM.Input(f"audio_{index}", display_name=f"音频{index}", optional=True) for index in range(1, MAX_AUDIOS + 1)],
            outputs=[AUDIO_PACK.Output(display_name="音频素材包"), MENTION_REGISTRY.Output(display_name="音频引用表"), io.String.Output(display_name="音频清单")],
        )

    @classmethod
    def execute(cls, **kwargs):
        items = [kwargs.get(f"audio_{index}") for index in range(1, MAX_AUDIOS + 1)]
        active = [item for item in items if isinstance(item, dict) and item.get("enabled")]
        total = sum(float(item["audio"]["waveform"].shape[-1]) / float(item["audio"]["sample_rate"]) for item in active if item.get("audio"))
        if any(float(item["audio"]["waveform"].shape[-1]) / float(item["audio"]["sample_rate"]) < 2.0 or float(item["audio"]["waveform"].shape[-1]) / float(item["audio"]["sample_rate"]) > 15.0 for item in active if item.get("audio")):
            raise ValueError("每个 H3 参考音频必须为 2–15 秒")
        if total > 15.0:
            raise ValueError(f"参考音频总时长不能超过 15 秒，当前为 {total:.2f} 秒")
        pack, aliases = build_audio_pack(items)
        registry = {"schema": "xyue-h3/mention-registry-v1", "alias_to_token": aliases, "token_to_alias": pack["token_to_alias"], "entries": pack["entries"]}
        lines = [f"{entry['alias']} → {entry['token']}｜{entry.get('anchor_label', '声音锚点')}｜{entry.get('filename', '')}" for entry in pack["entries"]]
        return io.NodeOutput(pack, registry, "\n".join(lines) if lines else "未启用音频")


class XYUEH3MaterialManager(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_MaterialManager",
            display_name=_display("集中素材管理"),
            category=CATEGORY,
            description="汇总图片、视频、视频原声和独立音频，生成统一的 H3 素材引用表。",
            inputs=[
                IMAGE_PACK.Input("image_pack", display_name="图片包", optional=True),
                VIDEO_PACK.Input("video_pack", display_name="视频包", optional=True),
                AUDIO_PACK.Input("audio_pack", display_name="独立音频包", optional=True),
            ],
            outputs=[MATERIAL_PACK.Output(display_name="统一素材包"), MENTION_REGISTRY.Output(display_name="统一引用表"), io.String.Output(display_name="素材清单")],
        )

    @classmethod
    def execute(cls, image_pack=None, video_pack=None, audio_pack=None):
        counts = validate_reference_limits(image_pack, video_pack, audio_pack)
        pack, registry = build_material_pack(image_pack, video_pack, audio_pack)
        lines = [f"{entry.get('alias', '')} → {entry.get('token', '')}｜{entry.get('filename', '')}" for entry in registry.get("entries", []) if entry.get("token")]
        summary = f"Ref2VA 文件计数：图片 {counts['pictures']}/9｜视频 {counts['videos']}/3｜音频 {counts['audios']}/3｜混合 {counts['mixed']}/12"
        return io.NodeOutput(pack, registry, summary + ("\n" + "\n".join(lines) if lines else "\n当前没有启用参考素材"))


ASSET_NODE_CLASSES = [
    XYUEH3ImageAsset,
    XYUEH3ImageManager,
    XYUEH3VideoAsset,
    XYUEH3VideoManager,
    XYUEH3AudioAsset,
    XYUEH3AudioManager,
    XYUEH3MaterialManager,
]
