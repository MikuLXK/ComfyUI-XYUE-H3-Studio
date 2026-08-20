"""Stable contracts shared by XYUE H3 Studio nodes and services."""

from __future__ import annotations

from typing import Final


BRAND: Final = "XYUE H3 Studio"
CATEGORY: Final = "XYUE/H3 Studio"
FPS: Final = 24
CANVAS_MULTIPLE: Final = 32
MAX_PIXELS: Final = 768 * 1344
MAX_PICTURES: Final = 9
MAX_VIDEOS: Final = 3
MAX_AUDIOS: Final = 3
MAX_REFERENCE_FILES: Final = 12
MAX_DOCUMENTS: Final = 5
MAX_STAGES: Final = 5

IMAGE_ITEM_SCHEMA: Final = "xyue-h3/image-item-v1"
VIDEO_ITEM_SCHEMA: Final = "xyue-h3/video-item-v1"
AUDIO_ITEM_SCHEMA: Final = "xyue-h3/audio-item-v1"
IMAGE_PACK_SCHEMA: Final = "xyue-h3/image-pack-v1"
VIDEO_PACK_SCHEMA: Final = "xyue-h3/video-pack-v1"
AUDIO_PACK_SCHEMA: Final = "xyue-h3/audio-pack-v1"
MATERIAL_PACK_SCHEMA: Final = "xyue-h3/material-pack-v1"
DOCUMENT_ITEM_SCHEMA: Final = "xyue-h3/document-item-v1"
DOCUMENT_PACK_SCHEMA: Final = "xyue-h3/document-pack-v1"
MODEL_PROFILE_SCHEMA: Final = "xyue-h3/model-profile-v1"
GENERATION_PROFILE_SCHEMA: Final = "xyue-h3/generation-profile-v1"
STUDIO_CONTROL_SCHEMA: Final = "xyue-h3/studio-control-v1"
GLOBAL_LORA_CONTROL_SCHEMA: Final = "xyue-h3/global-lora-control-v1"
GLOBAL_ACCELERATION_CONTROL_SCHEMA: Final = "xyue-h3/sol-attn-control-v1"
MULTI_STAGE_CONFIG_SCHEMA: Final = "xyue.h3.multi-stage-cloud-config/v1"
MENTION_REGISTRY_SCHEMA: Final = "xyue-h3/mention-registry-v1"

MODES: Final = ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA")
MODE_LABELS: Final = {
    "T2VA": "文生视频模式",
    "I2VA": "首帧生视频模式",
    "FL2VA": "首尾帧生视频模式",
    "L2VA": "尾帧续写模式",
    "Ref2VA": "多参考模式",
}
MODE_OPTIONS: Final = tuple(MODE_LABELS.values())
MODE_ALIASES: Final = {
    **{mode: mode for mode in MODES},
    **{label: mode for mode, label in MODE_LABELS.items()},
    **{f"{label}（{mode}）": mode for mode, label in MODE_LABELS.items()},
    **{f"{label}({mode})": mode for mode, label in MODE_LABELS.items()},
}

IMAGE_ROLES: Final = (
    "未指定",
    "角色定妆图",
    "表情状态图",
    "服装造型图",
    "场景气氛图",
    "道具线索图",
    "构图光影图",
    "风格质感图",
    "品牌/文字参考",
    "其他视觉锚点",
)
VIDEO_ROLES: Final = (
    "动作节奏样片",
    "镜头运动样片",
    "表演情绪样片",
    "场面调度样片",
    "转场剪辑样片",
    "光影氛围样片",
    "口型/对白节奏",
    "环境运动参考",
    "其他动态锚点",
)
AUDIO_ANCHOR_TYPES: Final = (
    "角色声纹锚点",
    "角色语气锚点",
    "角色对白节奏锚点",
    "旁白声音锚点",
    "环境声场锚点",
    "动作拟音锚点",
    "音乐主题锚点",
    "节拍结构锚点",
    "自定义声音锚点",
)
ROLES: Final = IMAGE_ROLES + VIDEO_ROLES + AUDIO_ANCHOR_TYPES
ALIAS_MODES: Final = ("@文件名", "@图片N", "@视频N", "@音频N")
IMAGE_FIT_MODES: Final = ("保持原图", "居中裁剪", "留边适配")
SCHEDULERS: Final = ("simple", "beta", "normal")
STEPS: Final = (8, 10, 12, 15, 20)
DOCUMENT_EXTENSIONS: Final = (".pdf", ".docx", ".txt", ".md", ".json")


def mode_requires(mode: str) -> tuple[str, ...]:
    """Return the required external inputs for a generation mode."""

    mode = normalize_mode(mode)
    values = {
        "T2VA": (),
        "I2VA": ("first_frame",),
        "FL2VA": ("first_frame", "last_frame"),
        "L2VA": ("last_frame",),
        "Ref2VA": ("material_pack",),
    }
    try:
        return values[str(mode)]
    except KeyError as exc:
        raise ValueError(f"不支持的 H3 模式：{mode}") from exc


def normalize_mode(mode: str) -> str:
    """Convert a UI mode label to the canonical H3 mode key."""

    value = str(mode).strip()
    if value in MODE_ALIASES:
        return MODE_ALIASES[value]
    for key in MODES:
        if key.lower() in value.lower():
            return key
    raise ValueError(f"不支持的 H3 模式：{mode}")
