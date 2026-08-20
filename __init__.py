"""XYUE H3 Studio: local MiniMax H3 workflow tools."""

from __future__ import annotations

import os
import sys

from comfy_api.latest import ComfyExtension, io

# ComfyUI loads custom-node directories through a path-derived module name.
# Give this hyphenated directory a normal package alias before relative imports.
if __package__ and (":" in __package__ or "\\" in __package__ or "/" in __package__):
    _runtime_package = "xyue_h3_studio_runtime"
    sys.modules[_runtime_package] = sys.modules[__name__]
    sys.modules[_runtime_package].__path__ = [os.path.dirname(__file__)]
    __package__ = _runtime_package

if __package__:
    from .nodes.aggregate import AGGREGATE_NODE_CLASSES
    from .nodes.studio_executor import STUDIO_EXECUTOR_NODE_CLASSES
    from .nodes.assets import ASSET_NODE_CLASSES
    try:
        from .services import routes as _routes  # noqa: F401
    except (AttributeError, ImportError):
        _routes = None
else:  # pytest imports a hyphenated custom-node directory as a bare module.
    AGGREGATE_NODE_CLASSES = STUDIO_EXECUTOR_NODE_CLASSES = ASSET_NODE_CLASSES = []

WEB_DIRECTORY = "./web"


class XYUEH3StudioExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return AGGREGATE_NODE_CLASSES + STUDIO_EXECUTOR_NODE_CLASSES


async def comfy_entrypoint() -> XYUEH3StudioExtension:
    return XYUEH3StudioExtension()


__all__ = ["WEB_DIRECTORY", "comfy_entrypoint"]
