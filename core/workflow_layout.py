"""Pure helpers for deterministic ComfyUI workflow layout."""

from __future__ import annotations


STAGE_MARKERS = tuple(
    (f"第{marker}阶段", index)
    for index, marker in enumerate(("一", "二", "三", "四", "五", "六", "七", "八", "九", "十"))
)


def stage_index(title: str) -> int:
    for marker, index in STAGE_MARKERS:
        if marker in str(title):
            return index
    return 99


def sort_nodes_by_stage(nodes: list[dict]) -> list[dict]:
    return sorted(nodes, key=lambda node: (stage_index(node.get("title", "")), int(node.get("id", 0))))
