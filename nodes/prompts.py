"""Prompt editor, H3 enhancer, and text output nodes."""

from __future__ import annotations

import json

from comfy_api.latest import io

from ..core.contracts import CATEGORY, DOCUMENT_PACK_SCHEMA, MAX_STAGES, MODE_OPTIONS, normalize_mode
from ..core.h3_prompt import compile_draft, validate_prompt
from ..core.multi_stage_config import stage_values
from ..services.api_profiles import get_profile, list_profiles
from ..services.prompt_api import request_prompt

MENTION_REGISTRY = io.Custom("XYUE_H3_MENTION_REGISTRY")
DOCUMENT_PACK = io.Custom("XYUE_H3_DOCUMENT_PACK")
MULTI_STAGE_CONFIG = io.Custom("XYUE_H3_MULTI_STAGE_CONFIG")


def _display(name: str) -> str:
    return f"XYUE_{name}"


class XYUEH3PromptEditor(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_PromptEditor",
            display_name=_display("提示词文本"),
            category=CATEGORY,
            description="用中文写草稿；前端支持 @ 别名和 <Picture N>/<Video N>/<Audio N> 快速插入。",
            inputs=[
                io.Combo.Input("mode", display_name="H3 模式", options=list(MODE_OPTIONS), default="文生视频模式"),
                io.Float.Input("duration", display_name="有效时长", default=5.0, min=1.0, max=15.0, step=0.1),
                io.String.Input("draft", display_name="提示词草稿", multiline=True, dynamic_prompts=True, default="描述人物、场景、动作、运镜、声音和结尾。"),
                io.Int.Input("stage_index", display_name="阶段编号", default=1, min=1, max=MAX_STAGES, step=1),
                MENTION_REGISTRY.Input("mention_registry", display_name="素材引用表", optional=True),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[io.String.Output(display_name="原始草稿"), io.String.Output(display_name="规范化提示词"), io.String.Output(display_name="引用报告")],
        )

    @classmethod
    def execute(cls, mode, duration, draft, stage_index=1, mention_registry=None, multi_stage_config=None):
        mode = normalize_mode(str(mode))
        configured_draft, configured_values = stage_values(multi_stage_config, int(stage_index))
        if configured_values is not None:
            draft = configured_draft
            duration = configured_values["duration"]
        compiled, used = compile_draft(str(draft), mode, mention_registry, float(duration))
        report = {"mode": mode, "duration": float(duration), "stage_index": int(stage_index), "used_aliases": list(used), "status": "passed"}
        return io.NodeOutput(str(draft), compiled, json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3PromptEnhancer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        profiles = list_profiles()
        profile_options = [item["id"] for item in profiles] or ["未配置 API"]
        return io.Schema(
            node_id="XYUE_H3_PromptEnhancer",
            display_name=_display("提示词强化"),
            category=CATEGORY,
            description="使用全局 Responses 或 Chat Completions 配置，将草稿转换为严格 H3 英文结构。",
            inputs=[
                io.Combo.Input("mode", display_name="H3 模式", options=list(MODE_OPTIONS), default="文生视频模式"),
                io.Float.Input("duration", display_name="有效时长", default=5.0, min=1.0, max=15.0, step=0.1),
                io.Combo.Input("profile_id", display_name="API 配置", options=profile_options, default=profile_options[0]),
                io.Boolean.Input("enabled", display_name="启用强化", default=False, label_on="强化", label_off="直通"),
                io.String.Input("draft", display_name="待强化提示词", multiline=True, dynamic_prompts=True, force_input=True),
                io.Int.Input("stage_index", display_name="阶段编号", default=1, min=1, max=MAX_STAGES, step=1),
                MENTION_REGISTRY.Input("mention_registry", display_name="素材引用表", optional=True),
                DOCUMENT_PACK.Input("document_pack", display_name="参考文档包", optional=True),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[io.String.Output(display_name="强化提示词"), io.String.Output(display_name="API 原始响应"), io.String.Output(display_name="验证报告")],
        )

    @classmethod
    def execute(cls, mode, duration, profile_id, enabled, draft, stage_index=1, mention_registry=None, document_pack=None, multi_stage_config=None):
        mode = normalize_mode(str(mode))
        configured_draft, configured_values = stage_values(multi_stage_config, int(stage_index))
        if configured_values is not None:
            draft = configured_draft
            duration = configured_values["duration"]
        registry = dict(mention_registry or {})
        source, _ = compile_draft(str(draft), mode, registry, float(duration))
        if not enabled:
            # Natural-language prompts are valid H3 input. The six-field
            # Context-IR layout is a recommendation, not an execution gate.
            errors = validate_prompt(source, mode, float(duration), registry, strict_fields=False)
            if errors:
                raise ValueError("直通提示词未通过检查：" + "；".join(errors))
            return io.NodeOutput(
                source,
                "",
                json.dumps(
                    {
                        "status": "passthrough",
                        "format": "natural_language_or_structured",
                        "errors": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        if profile_id == "未配置 API":
            raise ValueError("请先在 ComfyUI 设置中配置 XYUE H3 API")
        profile = get_profile(str(profile_id))
        documents = list((document_pack or {}).get("entries") or [])
        enhanced, raw_report = request_prompt(profile, source, mode, registry, documents)
        # H3-Base accepts free-form natural language. The Context-IR field
        # layout is a recommendation, so API output is diagnosed but never
        # rejected or sent through an automatic repair request.
        errors = validate_prompt(enhanced, mode, float(duration), registry, strict_fields=False)
        report = {
            "status": "passed",
            "repaired": False,
            "mode": mode,
            "format": "structured_context_ir" if any(field in enhanced for field in ("integrated_multimodal_description:", "subject_definitions:")) else "natural_language",
            "warnings": errors,
            "api": {"protocol": profile.get("protocol"), "model": profile.get("model")},
        }
        return io.NodeOutput(enhanced, json.dumps(raw_report, ensure_ascii=False, indent=2, default=str), json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3PromptOutput(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_PromptOutput",
            display_name=_display("提示词输出"),
            category=CATEGORY,
            description="展示和复制最终提示词，并继续输出 STRING。",
            inputs=[io.String.Input("prompt", display_name="最终提示词", multiline=True, force_input=True)],
            outputs=[io.String.Output(display_name="提示词")],
        )

    @classmethod
    def execute(cls, prompt):
        return io.NodeOutput(str(prompt))


PROMPT_NODE_CLASSES = [XYUEH3PromptEditor, XYUEH3PromptEnhancer, XYUEH3PromptOutput]
