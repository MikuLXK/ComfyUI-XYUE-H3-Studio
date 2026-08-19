import asyncio
import importlib.util
import sys
from pathlib import Path


def _load_generation_module():
    root = Path(__file__).parents[1]
    package_name = "xyue_h3_sampling_pipeline_test"
    spec = importlib.util.spec_from_file_location(
        package_name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    extension = asyncio.run(module.comfy_entrypoint())
    asyncio.run(extension.get_node_list())
    return sys.modules[f"{package_name}.nodes.generation"]


def test_dual_sampling_uses_denoised_latent_and_complete_low_sigmas(monkeypatch):
    generation = _load_generation_module()
    calls = {"sampler": []}
    high_sigmas = object()
    low_sigmas = object()
    upscaled_latent = object()
    refined_sigmas = type("RefinedSigmas", (), {"shape": (9,)})()

    class FakeSampler:
        @classmethod
        def execute(cls, **kwargs):
            calls["sampler"].append(kwargs)
            if len(calls["sampler"]) == 1:
                return "coarse-output", "coarse-denoised"
            return "final-output", "final-denoised"

    class FakeSplit:
        @classmethod
        def execute(cls, *, sigmas, step):
            calls["split"] = (sigmas, step)
            return high_sigmas, low_sigmas

    class FakeCFGGuider:
        @classmethod
        def execute(cls, **kwargs):
            calls["cfg"] = kwargs
            return ("refine-guider",)

    class FakeZeroOut:
        def zero_out(self, *, conditioning):
            calls["zero"] = conditioning
            return ("negative",)

    def fake_refine_sigmas(sigmas, **kwargs):
        calls["sigmas"] = (sigmas, kwargs)
        return refined_sigmas

    def fake_refine_latent(latent, positive, negative, **kwargs):
        calls["latent"] = (latent, positive, negative, kwargs)
        return upscaled_latent, "refined-positive", "refined-negative"

    monkeypatch.setattr(generation, "SamplerCustomAdvanced", FakeSampler)
    monkeypatch.setattr(generation, "SplitSigmas", FakeSplit)
    monkeypatch.setattr(generation, "CFGGuider", FakeCFGGuider)
    monkeypatch.setattr(generation, "refine_sigmas", fake_refine_sigmas)
    monkeypatch.setattr(generation, "refine_av_latent", fake_refine_latent)
    monkeypatch.setattr(generation.comfy_nodes, "ConditioningZeroOut", FakeZeroOut, raising=False)

    result = generation._sample_av(
        model="model",
        conditioned="positive",
        guider="coarse-guider",
        sampler="sampler",
        sigmas="original-sigmas",
        latent="source-latent",
        noise="noise",
        sampling={"mode": "dual", "coarse_steps": 4, "extend_sigmas": 1},
        target_width=864,
        target_height=480,
        model_profile={"latent_upscale_model": "h3-upscaler.safetensors"},
    )

    assert result == "final-output"
    assert calls["split"] == (refined_sigmas, 4)
    assert calls["sampler"][0]["sigmas"] is high_sigmas
    assert calls["sampler"][0]["latent_image"] == "source-latent"
    assert calls["latent"][0] == "coarse-denoised"
    assert calls["latent"][3]["model_name"] == "h3-upscaler.safetensors"
    assert calls["latent"][3]["align"] == 2
    assert calls["sampler"][1]["sigmas"] is low_sigmas
    assert calls["sampler"][1]["latent_image"] is upscaled_latent
    assert calls["sampler"][1]["guider"] == "refine-guider"
