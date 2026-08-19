"""UI labels and normalization for H3 generation controls."""

from __future__ import annotations

from typing import Final


DEFAULT_DURATION: Final = 5
DEFAULT_STEPS: Final = 12
MIN_STEPS: Final = 1
MIN_AUDIO_STEPS: Final = 1
MAX_STEPS: Final = 20

SCHEDULER_LABELS: Final = {
    "简单稳定（推荐）": "simple",
    "Beta 动态细节": "beta",
    "标准均衡": "normal",
}
REFERENCE_SIZE_LABELS: Final = {
    "适配生成画布（省显存）": "match",
    "保留参考图细节（高显存）": "max",
}

SCHEDULER_OPTIONS: Final = tuple(SCHEDULER_LABELS)
REFERENCE_SIZE_OPTIONS: Final = tuple(REFERENCE_SIZE_LABELS)
DEFAULT_SCHEDULER: Final = SCHEDULER_OPTIONS[0]
DEFAULT_REFERENCE_SIZE: Final = REFERENCE_SIZE_OPTIONS[0]

SAMPLING_PRESET_OPTIONS: Final = ("快速单次（推荐）", "高品质双段")
SAMPLING_MODE_OPTIONS: Final = ("单次采样", "双段采样")
DEFAULT_SAMPLING_PRESET: Final = SAMPLING_PRESET_OPTIONS[0]
DEFAULT_SAMPLING_MODE: Final = SAMPLING_MODE_OPTIONS[0]

SAMPLING_PRESETS: Final = {
    "快速单次（推荐）": {
        "mode": "单次采样",
        "coarse_steps": 2,
        "upscale_factor": 1.0,
        "refine_pass": False,
        "extend_sigmas": 0,
    },
    "高品质双段": {
        "mode": "双段采样",
        "coarse_steps": 4,
        "upscale_factor": 1.5,
        "refine_pass": True,
        "extend_sigmas": 1,
    },
}


def normalize_sampling_mode(value: str) -> str:
    """Convert the localized sampling-mode option to the internal id."""

    return {"单次采样": "single", "双段采样": "dual"}.get(str(value), str(value))


def resolve_sampling(
    preset: str = DEFAULT_SAMPLING_PRESET,
    mode: str = DEFAULT_SAMPLING_MODE,
    coarse_steps: int = 2,
    upscale_factor: float = 1.0,
    refine_pass: bool = False,
    extend_sigmas: int = 0,
) -> dict:
    """Resolve the effective sampling parameters from a verified preset.

    A named preset is authoritative and overrides the individual widget values.
    Keys: preset, mode, coarse_steps,
    upscale_factor, refine_pass, extend_sigmas.
    """

    preset = str(preset or DEFAULT_SAMPLING_PRESET)
    if preset in SAMPLING_PRESETS:
        values = dict(SAMPLING_PRESETS[preset])
        values["mode"] = normalize_sampling_mode(values["mode"])
        return {"preset": preset, **values}
    values = dict(SAMPLING_PRESETS[DEFAULT_SAMPLING_PRESET])
    values["mode"] = normalize_sampling_mode(values["mode"])
    return {"preset": DEFAULT_SAMPLING_PRESET, **values}


def normalize_scheduler(value: str) -> str:
    """Convert the localized UI option to the sampler scheduler id."""

    return SCHEDULER_LABELS.get(str(value), str(value))


def normalize_reference_size(value: str) -> str:
    """Convert the localized UI option to MiniMax H3's reference-size id."""

    return REFERENCE_SIZE_LABELS.get(str(value), str(value))


def sampler_for_acceleration(mode: str) -> str:
    return "euler"
