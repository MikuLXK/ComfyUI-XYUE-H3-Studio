"""Seed input and progression rules shared by Studio and direct execution."""

from __future__ import annotations

import secrets


MAX_SEED = 0xFFFFFFFFFFFFFFFF
SEED_MODES = ("random", "increase", "decrease", "fixed")
SEED_MODE_LABELS = {
    "random": "随机",
    "increase": "增加",
    "decrease": "减少",
    "fixed": "固定",
}


def normalize_seed_mode(value: object) -> str:
    mode = str(value or "random").strip().lower()
    aliases = {
        "reuse": "fixed",
        "randomize": "random",
        "随机种子": "random",
        "随机": "random",
        "增加": "increase",
        "减少": "decrease",
        "固定": "fixed",
    }
    mode = aliases.get(mode, mode)
    return mode if mode in SEED_MODES else "random"


def normalize_seed(value: object, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(0, min(MAX_SEED, number))


def next_seed(value: object, mode: object) -> int:
    current = normalize_seed(value)
    selected = normalize_seed_mode(mode)
    if selected == "fixed":
        return current
    if selected == "increase":
        return (current + 1) & MAX_SEED
    if selected == "decrease":
        return MAX_SEED if current == 0 else current - 1
    return secrets.randbits(64)
