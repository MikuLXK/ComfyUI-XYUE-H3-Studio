"""H3 canvas and duration calculation."""

from __future__ import annotations

import math

from .contracts import CANVAS_MULTIPLE, FPS, MAX_PIXELS

ASPECTS = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "1:1": (1, 1),
    "21:9": (21, 9),
}

RESOLUTION_PRESETS_16_9 = {
    "352p（608×352）": (608, 352),
    "416p（736×416）": (736, 416),
    "480p（864×480）": (864, 480),
    "544p（960×544）": (960, 544),
    "608p（1056×608）": (1056, 608),
    "640p（1152×640）": (1152, 640),
    "672p（1216×672）": (1216, 672),
    "720p（1280×736，32倍数近似）": (1280, 736),
    "768p（1344×768）": (1344, 768),
    "768p+（1376×768，实验）": (1376, 768),
    "832p（1504×832，实验）": (1504, 832),
    "928p（1664×928，实验）": (1664, 928),
    "1024p（1824×1024，实验）": (1824, 1024),
    "1080p（1920×1088，32倍数近似，实验）": (1920, 1088),
}
NATIVE_RESOLUTION = "768p（H3原生推荐）"
RESOLUTION_OPTIONS = (NATIVE_RESOLUTION, *RESOLUTION_PRESETS_16_9)


def _align(value: float) -> int:
    return max(CANVAS_MULTIPLE, int(math.floor(value / CANVAS_MULTIPLE + 0.5)) * CANVAS_MULTIPLE)


def native_canvas(aspect: str) -> tuple[int, int]:
    if aspect not in ASPECTS:
        raise ValueError(f"不支持的画面比例：{aspect}")
    ratio_w, ratio_h = ASPECTS[aspect]
    short = 768.0
    if ratio_w >= ratio_h:
        width, height = short * ratio_w / ratio_h, short
    else:
        width, height = short, short * ratio_h / ratio_w
    if width * height > MAX_PIXELS:
        scale = math.sqrt(MAX_PIXELS / (width * height))
        width *= scale
        height *= scale
    return _align(width), _align(height)


def preset_canvas(aspect: str, preset: str) -> tuple[int, int]:
    if aspect == "16:9" and preset in RESOLUTION_PRESETS_16_9:
        return RESOLUTION_PRESETS_16_9[preset]
    if aspect not in ASPECTS or preset not in RESOLUTION_PRESETS_16_9:
        raise ValueError("无效的比例或分辨率档位")
    base_width, base_height = RESOLUTION_PRESETS_16_9[preset]
    target = float(base_width * base_height)
    ratio_w, ratio_h = ASPECTS[aspect]
    height = math.sqrt(target * ratio_h / ratio_w)
    width = height * ratio_w / ratio_h
    candidates = []
    for dw in range(-64, 65, CANVAS_MULTIPLE):
        for dh in range(-64, 65, CANVAS_MULTIPLE):
            w, h = _align(width + dw), _align(height + dh)
            error = abs((w * h - target) / target) + abs((w / h) - (ratio_w / ratio_h))
            candidates.append((error, w, h))
    _, selected_w, selected_h = min(candidates)
    return selected_w, selected_h


def resolve_canvas(aspect: str, resolution: str) -> tuple[int, int, bool]:
    if resolution == NATIVE_RESOLUTION:
        width, height = native_canvas(aspect)
    else:
        width, height = preset_canvas(aspect, resolution)
    experimental = min(width, height) > 768 or width * height > MAX_PIXELS
    return width, height, experimental


def downscale_canvas(width: int, height: int, scale: float) -> tuple[int, int]:
    """Return a H3-compatible base canvas for a learned latent upscale pass."""

    factor = max(1.0, float(scale))
    return _align(width / factor), _align(height / factor)


def align_duration(seconds: int | float) -> tuple[int, float]:
    requested = max(1, min(15, int(seconds)))
    frames = max(5, int(round(requested * FPS)))
    while frames % 17 != 5:
        frames += 1
    return frames, frames / FPS
