"""Document upload and reference pack nodes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from ..core.contracts import CATEGORY, DOCUMENT_EXTENSIONS, DOCUMENT_ITEM_SCHEMA, DOCUMENT_PACK_SCHEMA, MAX_DOCUMENTS
from ..services.document_parser import extract_text, validate_document_path

DOCUMENT_ITEM = io.Custom("XYUE_H3_DOCUMENT_ITEM")
DOCUMENT_PACK = io.Custom("XYUE_H3_DOCUMENT_PACK")


def _documents_dir() -> Path:
    path = Path(folder_paths.get_input_directory()) / "xyue_h3_docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _document_names() -> list[str]:
    return sorted(path.name for path in _documents_dir().iterdir() if path.is_file() and path.suffix.lower() in DOCUMENT_EXTENSIONS)


class XYUEH3DocumentAsset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_DocumentAsset",
            display_name="XYUE_参考文档",
            category=CATEGORY,
            description="选择已上传到 input/xyue_h3_docs 的 PDF、DOCX、TXT、MD 或 JSON 文件。",
            inputs=[
                io.Combo.Input("document", display_name="文档", options=_document_names()),
                io.Boolean.Input("enabled", display_name="启用文档", default=True, label_on="启用", label_off="禁止"),
                io.String.Input("title", display_name="参考标题", default="", optional=True),
                io.Int.Input("priority", display_name="参考优先级", default=1, min=1, max=5, step=1),
            ],
            outputs=[DOCUMENT_ITEM.Output(display_name="文档素材项"), io.String.Output(display_name="文档信息")],
        )

    @classmethod
    def execute(cls, document, enabled, title, priority):
        path = _documents_dir() / Path(str(document)).name
        validate_document_path(path)
        excerpt, report = extract_text(path, 4000)
        item = {
            "schema": DOCUMENT_ITEM_SCHEMA,
            "path": str(path),
            "filename": path.name,
            "title": str(title or path.stem),
            "enabled": bool(enabled),
            "priority": int(priority),
            "excerpt": excerpt,
            "report": report,
        }
        return io.NodeOutput(item, json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3DocumentManager(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_DocumentManager",
            display_name="XYUE_文档管理",
            category=CATEGORY,
            description="组合最多 5 份参考文档，提示词强化器会按预算读取。",
            inputs=[DOCUMENT_ITEM.Input(f"document_{index}", display_name=f"文档{index}", optional=True) for index in range(1, MAX_DOCUMENTS + 1)],
            outputs=[DOCUMENT_PACK.Output(display_name="文档包"), io.String.Output(display_name="文档清单")],
        )

    @classmethod
    def execute(cls, **kwargs):
        entries = [dict(kwargs.get(f"document_{index}")) for index in range(1, MAX_DOCUMENTS + 1) if isinstance(kwargs.get(f"document_{index}"), dict) and kwargs[f"document_{index}"].get("enabled")]
        pack = {"schema": DOCUMENT_PACK_SCHEMA, "entries": entries, "count": len(entries), "budget": 80_000}
        lines = [f"{entry['title']}｜{entry['filename']}｜优先级 {entry['priority']}" for entry in entries]
        return io.NodeOutput(pack, "\n".join(lines) if lines else "未启用参考文档")


DOCUMENT_NODE_CLASSES = [XYUEH3DocumentAsset, XYUEH3DocumentManager]

