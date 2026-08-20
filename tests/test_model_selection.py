import asyncio
import importlib.util
import sys
from pathlib import Path


def _generation_module():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("xyue_model_selection_new", root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    extension = asyncio.run(module.comfy_entrypoint())
    asyncio.run(extension.get_node_list())
    return sys.modules[f"{spec.name}.nodes.generation"]


def test_internal_model_selector_exposes_lora_and_attention_controls():
    generation = _generation_module()
    schema = generation.XYUEH3ModeModelSelector.GET_SCHEMA()
    inputs = {item.id: item for item in schema.inputs}
    assert {"lora_enabled", "lora_name", "lora_strength", "attention_mode"} <= set(inputs)
    assert "MiniMax H3 Kitchen Attention" in inputs["attention_mode"].options
    assert "Patch Sol-Attn" in inputs["attention_mode"].options


def test_generation_defaults_match_target_sampling_plan():
    generation = _generation_module()
    profile = generation.XYUEH3GenerationProfile.execute(
        aspect="16:9",
        resolution="0.4MP|480p（864×480）",
        duration=5,
        video_steps=4,
        audio_steps=4,
        scheduler="Beta 动态细节",
        seed=1,
        reference_size="适配生成画布（省显存）",
        upscale_factor=1.5,
        sigma_steps=3,
        denoise=0.3,
    )[0]
    assert profile["video_steps"] == 4
    assert profile["audio_steps"] == 4
    assert profile["sampling"]["sigma_steps"] == 3
    assert profile["sampling"]["denoise"] == 0.3
