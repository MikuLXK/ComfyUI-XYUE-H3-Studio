"""Runtime node for portable multi-stage cloud configuration text."""

from __future__ import annotations

import json

from comfy_api.latest import io

from ..core.contracts import CATEGORY
from ..core.multi_stage_config import parse_multi_stage_config


MULTI_STAGE_CONFIG = io.Custom("XYUE_H3_MULTI_STAGE_CONFIG")


class XYUEH3MultiStageConfig(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_MultiStageConfig",
            display_name="XYUE_多段云端配置",
            category=CATEGORY,
            description="粘贴 h3.multi-stage-cloud-config/v1 JSON；只覆盖提示词、阶段参数和全局加速，不修改模型或 LoRA。",
            inputs=[
                io.String.Input(
                    "config_text",
                    display_name="多段配置文本",
                    multiline=True,
                    dynamic_prompts=False,
                    default="",
                ),
            ],
            outputs=[MULTI_STAGE_CONFIG.Output(display_name="多段配置"), io.String.Output(display_name="配置报告")],
        )

    @classmethod
    def execute(cls, config_text):
        config = parse_multi_stage_config(config_text)
        if not config:
            return io.NodeOutput({}, json.dumps({"status": "disabled", "model_policy": "keep_workflow_models_and_loras"}, ensure_ascii=False, indent=2))
        report = {
            "status": "passed",
            "workflow": config["workflow"],
            "stage_count": config["stage_count"],
            "model_policy": "keep_workflow_models_and_loras",
            "acceleration": config["acceleration"]["global_mode"],
        }
        return io.NodeOutput(config, json.dumps(report, ensure_ascii=False, indent=2))


MULTI_STAGE_NODE_CLASSES = [XYUEH3MultiStageConfig]
