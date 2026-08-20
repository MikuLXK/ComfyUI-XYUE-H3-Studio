import asyncio
import importlib.util
import sys
from pathlib import Path


def _video_asset_class():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "xyue_h3_asset_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{spec.name}.nodes.assets"].XYUEH3VideoAsset


def test_video_asset_exposes_reference_frames_without_changing_existing_outputs():
    node = _video_asset_class()
    schema = node.GET_SCHEMA()

    assert [output.id for output in schema.outputs[:4]] == [
        "_0_XYUE_H3_VIDEO_ITEM_",
        "_1_VIDEO_",
        "_2_IMAGE_",
        "_3_AUDIO_",
    ]
    assert schema.outputs[4].id == "_4_IMAGE_"

    result = node.execute("未选择视频", False, "@视频N", "动作节奏样片", 0.0, 0.0, False).result
    assert len(result) == 5
    assert result[0]["enabled"] is False
    assert result[4] is None


def test_disabled_reference_outputs_are_empty_for_all_asset_types():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "xyue_h3_asset_gate_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assets = sys.modules[f"{spec.name}.nodes.assets"]

    image_result = assets.XYUEH3ImageAsset.execute(
        "未选择图片", False, "@图片N", "未指定", "保持原图"
    ).result
    audio_result = assets.XYUEH3AudioAsset.execute(
        "未选择音频", False, "@音频N", "环境", "角色A", 0.0, 0.0, 0.0, False
    ).result
    assert image_result[3] is None
    assert audio_result[2] is None
