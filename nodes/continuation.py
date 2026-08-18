"""Reference-pack transformation for continuous Ref2VA scenes."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io

from ..core.contracts import CATEGORY, IMAGE_ITEM_SCHEMA
from ..core.materials import build_image_pack, build_material_pack
from ..core.reference_limits import continuation_image_action, validate_reference_limits
from .assets import MATERIAL_PACK, MENTION_REGISTRY


STRATEGIES = ("自动追加，9 图时替换最后启用图片（推荐）", "始终追加并校验上限")


class XYUEH3ContinuationReference(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_ContinuationReference",
            display_name="XYUE_续接帧加入多参考",
            category=CATEGORY,
            description=(
                "将上一段尾帧加入 Ref2VA 图片参考。图片少于 9 张时占用下一个 Picture 编号；"
                "只有图片已满 9 张时，才按连接顺序替换最后一张已启用图片。"
            ),
            inputs=[
                MATERIAL_PACK.Input("material_pack", display_name="原素材包"),
                io.Image.Input("continuation_frame", display_name="上一段尾帧"),
                io.Combo.Input("strategy", display_name="槽位策略", options=list(STRATEGIES), default=STRATEGIES[0]),
                io.String.Input("anchor_name", display_name="续接帧别名", default="上一段尾帧", multiline=False),
            ],
            outputs=[
                MATERIAL_PACK.Output(display_name="续接素材包"),
                MENTION_REGISTRY.Output(display_name="续接引用表"),
                io.String.Output(display_name="替换报告"),
            ],
        )

    @classmethod
    def execute(cls, material_pack, continuation_frame, strategy, anchor_name):
        base = dict(material_pack or {})
        images = dict(base.get("images") or {})
        videos = dict(base.get("videos") or {})
        audios = dict(base.get("audios") or {})
        image_entries = [dict(entry) for entry in images.get("entries") or []]
        counts_before = validate_reference_limits(images, videos, audios)

        replaced: dict[str, Any] | None = None
        action = "append_picture"
        if str(strategy) == STRATEGIES[0]:
            action = continuation_image_action(images, videos, audios)
        else:
            validate_reference_limits(images, videos, audios, reserve=1)
        if action == "replace_last_picture":
            replaced = image_entries.pop()

        name = str(anchor_name).strip()
        if not name:
            raise ValueError("续接帧别名不能为空")
        image_entries.append({
            "schema": IMAGE_ITEM_SCHEMA,
            "image": continuation_frame,
            "enabled": True,
            "filename": f"{name}.png",
            "numbered_alias": False,
            "role": "片段续接画面锚点",
            "fit_mode": "保持原图",
            "source_slot": "续接帧",
        })
        next_images, _ = build_image_pack(image_entries)
        counts_after = validate_reference_limits(next_images, videos, audios)
        pack, registry = build_material_pack(next_images, videos, audios)
        inserted = next_images["entries"][-1]

        if replaced:
            physical = replaced.get("source_slot", "未知")
            replaced_text = (
                f"已替换：物理图片槽位 {physical}｜执行编号 {replaced.get('token', '未知')}｜"
                f"{replaced.get('alias', '')}｜{replaced.get('filename', '')}"
            )
        else:
            replaced_text = f"未替换原图：续接帧追加为第 {inserted['index']} 张图片参考。"
        report = "\n".join((
            replaced_text,
            f"续接帧：{inserted['alias']} → {inserted['token']}",
            f"混合素材：{counts_before['mixed']} → {counts_after['mixed']} / 12",
            "说明：该尾帧是 Ref2VA 普通图片参考，不是 I2VA/FL2VA 的硬首帧约束。",
        ))
        return io.NodeOutput(pack, registry, report)


CONTINUATION_NODE_CLASSES = [XYUEH3ContinuationReference]
