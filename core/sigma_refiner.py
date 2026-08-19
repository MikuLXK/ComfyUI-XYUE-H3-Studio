"""MiniMax H3 low-sigma schedule refinement."""

from __future__ import annotations

import math

import torch


def refine_sigmas(
    sigmas: torch.Tensor,
    extra_steps: int = 1,
    start_at_sigma: float = 0.7,
    end_at_sigma: float = 0.0,
    spacing: str = "cosine",
) -> torch.Tensor:
    """Add samples to the low-noise tail without changing the high-noise head."""

    extra_steps = max(0, int(extra_steps))
    if extra_steps == 0 or sigmas.numel() < 2:
        return sigmas

    values = sigmas.detach().cpu()
    index = next((i for i, value in enumerate(values) if float(value) <= float(start_at_sigma)), -1)
    if index < 0 or index >= len(values) - 1:
        return sigmas

    head = values[:index]
    start = float(values[index])
    end = max(float(end_at_sigma), float(values[-1]))
    tail_length = len(values) - index + extra_steps
    t = torch.linspace(0.0, 1.0, steps=tail_length, dtype=values.dtype)

    if spacing == "cosine":
        factor = (1.0 - torch.cos(t * math.pi)) / 2.0
    elif spacing == "exponential":
        alpha = 3.0
        factor = (torch.exp(t * alpha) - 1.0) / (math.exp(alpha) - 1.0)
    else:
        factor = t

    tail = start + (end - start) * factor
    if float(values[-1]) == 0.0 and end > 0.0:
        tail = torch.cat((tail, torch.zeros(1, dtype=values.dtype)))

    refined = torch.cat((head, tail))
    return refined.to(device=sigmas.device, dtype=sigmas.dtype)

