import asyncio
import importlib.util
import sys
from pathlib import Path

import folder_paths


def test_model_selector_exposes_h3_upscaler_and_all_local_tiny_vaes():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "xyue_h3_model_selection_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    extension = asyncio.run(module.comfy_entrypoint())
    classes = asyncio.run(extension.get_node_list())
    schema = next(
        node.GET_SCHEMA()
        for node in classes
        if node.GET_SCHEMA().node_id == "XYUE_H3_ModeModelSelector"
    )
    inputs = {input_spec.id: input_spec for input_spec in schema.inputs}

    assert inputs["latent_upscale_model"].default == "minimax_h3_latent_upscaler_3d_fp16.safetensors"
    assert all("minimax_h3" in option.lower() for option in inputs["latent_upscale_model"].options)
    assert inputs["tiny_vae"].default == "none"
    assert inputs["tiny_vae"].options[0] == "none"

    vae_approx = Path(folder_paths.models_dir) / "vae_approx"
    local_tiny_vaes = {
        path.name
        for path in vae_approx.iterdir()
        if path.is_file() and path.suffix.lower() in {".safetensors", ".pt", ".pth", ".ckpt"}
    }
    assert local_tiny_vaes <= set(inputs["tiny_vae"].options)

    generation = next(
        node
        for node in classes
        if node.GET_SCHEMA().node_id == "XYUE_H3_GenerationProfile"
    )
    profile = generation.execute(
        "16:9",
        "480p（864×480）",
        5,
        8,
        8,
        "Beta 动态细节",
        0,
        "适配生成画布（省显存）",
        "高品质双段",
    )[0]
    assert (profile["width"], profile["height"]) == (576, 320)
    assert (profile["target_width"], profile["target_height"]) == (864, 480)
