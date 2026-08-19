import torch

from core import latent_refine
from core.sigma_refiner import refine_sigmas


def test_sigma_refiner_adds_cosine_tail_step_and_keeps_schedule_monotonic():
    sigmas = torch.tensor([1.0, 0.9, 0.8, 0.7, 0.5, 0.25, 0.0])

    refined = refine_sigmas(sigmas, extra_steps=1, start_at_sigma=0.7)

    assert len(refined) == len(sigmas) + 1
    assert refined[0].item() == sigmas[0].item()
    assert refined[-1].item() == 0.0
    assert torch.all(refined[:-1] >= refined[1:])


def test_sigma_refiner_noop_preserves_original_tensor():
    sigmas = torch.tensor([1.0, 0.5, 0.0])

    assert refine_sigmas(sigmas, extra_steps=0) is sigmas


def test_upscaler_precision_follows_selected_weight():
    assert latent_refine._model_precision("minimax_h3_latent_upscaler_3d_bf16.safetensors") == "bf16"
    assert latent_refine._model_precision("minimax_h3_latent_upscaler_3d_fp16.safetensors") == "fp16"
    assert latent_refine._model_precision("minimax_h3_latent_upscaler_3d_fp32.pth") == "fp32"


def test_latent_refine_calls_upscaler_and_condition_sync(monkeypatch):
    calls = {}
    upscaled = {"samples": object()}
    positive = object()
    negative = object()

    class ResolutionNode:
        def run(self, latent, model_name, width, height, align, device, precision):
            calls["upscale"] = (latent, model_name, width, height, align, device, precision)
            return (upscaled,)

    class SyncNode:
        def run(self, latent, positive_value, negative_value):
            calls["sync"] = (latent, positive_value, negative_value)
            return latent, "synced-positive", "synced-negative"

    monkeypatch.setattr(latent_refine, "_upscaler_components", lambda: (ResolutionNode, SyncNode))
    source = {"samples": object()}

    result = latent_refine.refine_av_latent(
        source,
        positive,
        negative,
        model_name="h3-upscaler.safetensors",
        target_width=864,
        target_height=480,
    )

    assert calls["upscale"] == (
        source,
        "h3-upscaler.safetensors",
        864,
        480,
        2,
        "cuda",
        "fp16",
    )
    assert calls["sync"] == (upscaled, positive, negative)
    assert result == (upscaled, "synced-positive", "synced-negative")
