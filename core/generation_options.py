"""UI labels and normalization for H3 generation controls."""

from __future__ import annotations

from typing import Final


DEFAULT_DURATION: Final = 5
DEFAULT_STEPS: Final = 4
DEFAULT_AUDIO_STEPS: Final = 4
DEFAULT_SIGMA_STEPS: Final = 3
DEFAULT_DENOISE: Final = 0.3
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

def resolve_sampling(
    upscale_factor: float = 1.5,
    sigma_steps: int = DEFAULT_SIGMA_STEPS,
    denoise: float = DEFAULT_DENOISE,
) -> dict:
    """Build the fixed H3 dual-pass topology with user-controlled intensity."""

    return {
        "mode": "dual",
        "upscale_factor": round(min(4.0, max(1.0, float(upscale_factor))), 1),
        "sigma_steps": max(1, min(20, int(sigma_steps))),
        "denoise": round(min(1.0, max(0.01, float(denoise))), 2),
        "sigma_start": 0.7,
        "sigma_end": 0.0,
        "sigma_spacing": "cosine",
    }


def normalize_scheduler(value: str) -> str:
    """Convert the localized UI option to the sampler scheduler id."""

    return SCHEDULER_LABELS.get(str(value), str(value))


def normalize_reference_size(value: str) -> str:
    """Convert the localized UI option to MiniMax H3's reference-size id."""

    return REFERENCE_SIZE_LABELS.get(str(value), str(value))


def sampler_for_acceleration(enabled: bool) -> str:
    return "euler"
