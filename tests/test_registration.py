import asyncio
import importlib.util
import sys
from pathlib import Path


def _schemas():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("xyue_h3_registration_new", root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    extension = asyncio.run(module.comfy_entrypoint())
    return {node.GET_SCHEMA().node_id: node.GET_SCHEMA() for node in asyncio.run(extension.get_node_list())}


def test_public_surface_is_studio_and_asset_library():
    schemas = _schemas()
    assert "XYUE_H3_AggregateWorkflow" in schemas
    assert "XYUE_H3_StudioExecutor" in schemas
    assert "XYUE_H3_ImageAsset" not in schemas
    assert "XYUE_H3_Generator" not in schemas
    assert "XYUE_H3_StageGenerationProfile" not in schemas
    assert "XYUE_H3_GlobalAccelerationManager" not in schemas


def test_executor_accepts_project_config():
    schemas = _schemas()
    executor = schemas["XYUE_H3_StudioExecutor"]
    assert executor.inputs[0].id == "config_text"
