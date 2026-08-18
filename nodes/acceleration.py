"""Selectable model acceleration nodes for MiniMax H3 workflows."""

from __future__ import annotations

import json

import folder_paths
import nodes as comfy_nodes
from comfy_api.latest import io

from ..core.contracts import (
    CATEGORY,
    GLOBAL_ACCELERATION_CONTROL_SCHEMA,
    GLOBAL_ACCELERATION_MODES,
    GLOBAL_LORA_CONTROL_SCHEMA,
    MODEL_PROFILE_SCHEMA,
    normalize_mode,
    normalize_acceleration_mode,
)


NO_LORA = "不使用 LoRA"
MODEL_PROFILE = io.Custom("XYUE_H3_MODEL_PROFILE")
GLOBAL_LORA_CONTROL = io.Custom("XYUE_H3_GLOBAL_LORA_CONTROL")
GLOBAL_ACCELERATION_CONTROL = io.Custom("XYUE_H3_GLOBAL_ACCELERATION_CONTROL")
MULTI_STAGE_CONFIG = io.Custom("XYUE_H3_MULTI_STAGE_CONFIG")


def _lora_options() -> tuple[list[str], str]:
    names = sorted(folder_paths.get_filename_list("loras"))
    preferred = next(
        (
            name
            for name in names
            if "minimax" in name.lower()
            and "h3" in name.lower()
            and any(marker in name.lower() for marker in ("8step", "8-step", "8_step"))
        ),
        NO_LORA,
    )
    return [NO_LORA, *names], preferred


class XYUEH3LoRASelector(io.ComfyNode):
    """Apply an optional user-selected LoRA to the selected H3 model."""

    @classmethod
    def define_schema(cls):
        options, default = _lora_options()
        return io.Schema(
            node_id="XYUE_H3_LoRASelector",
            display_name="XYUE_LoRA 选择",
            category=CATEGORY,
            description="从 ComfyUI 的 LoRA 目录自由选择加速 LoRA；选择“不使用 LoRA”可直接旁路。",
            inputs=[
                io.Model.Input("model", display_name="待处理模型"),
                MODEL_PROFILE.Input("model_profile", display_name="模型配置", optional=True),
                GLOBAL_LORA_CONTROL.Input("global_lora", display_name="全局 LoRA 配置", optional=True),
                io.Combo.Input("lora_name", display_name="LoRA 模型", options=options, default=default),
                io.Float.Input(
                    "strength_model",
                    display_name="模型强度",
                    default=1.0,
                    min=-100.0,
                    max=100.0,
                    step=0.01,
                ),
            ],
            outputs=[
                io.Model.Output(display_name="LoRA 后模型"),
                io.String.Output(display_name="LoRA 报告"),
            ],
        )

    @classmethod
    def execute(cls, model, lora_name, strength_model, model_profile=None, global_lora=None):
        profile = dict(model_profile or {})
        control = dict(global_lora or {})
        use_global = control.get("schema") == GLOBAL_LORA_CONTROL_SCHEMA and bool(control.get("enabled"))
        name = str(control.get("lora_name") if use_global else lora_name or NO_LORA)
        strength = float(control.get("strength_model") if use_global else strength_model)
        mode = normalize_mode(str(profile.get("mode"))) if profile.get("schema") == MODEL_PROFILE_SCHEMA else None
        if mode == "Ref2VA" and use_global and not bool(control.get("apply_to_ref2va")):
            name = NO_LORA
        if name == NO_LORA:
            report = {
                "enabled": False,
                "source": "全局" if use_global else "阶段",
                "mode": mode,
                "lora_name": None,
                "strength_model": 0.0,
            }
            return io.NodeOutput(model, json.dumps(report, ensure_ascii=False, indent=2))

        patched_model = comfy_nodes.LoraLoaderModelOnly().load_lora_model_only(
            model,
            name,
            strength,
        )[0]
        report = {
            "enabled": True,
            "source": "全局" if use_global else "阶段",
            "mode": mode,
            "lora_name": name,
            "strength_model": strength,
        }
        return io.NodeOutput(patched_model, json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3GlobalLoRAManager(io.ComfyNode):
    """Share one LoRA selection across all stages of a drama workflow."""

    @classmethod
    def define_schema(cls):
        options, default = _lora_options()
        return io.Schema(
            node_id="XYUE_H3_GlobalLoRAManager",
            display_name="XYUE_全局 LoRA 管理器",
            category=CATEGORY,
            description="统一控制各阶段 LoRA。Ref2VA 默认保持直通，避免误用 FL2VA 专用 LoRA。",
            inputs=[
                io.Boolean.Input(
                    "enabled",
                    display_name="启用全局 LoRA",
                    default=True,
                    label_on="全局统一",
                    label_off="阶段独立",
                ),
                io.Combo.Input("lora_name", display_name="全局 LoRA", options=options, default=default),
                io.Float.Input(
                    "strength_model",
                    display_name="全局模型强度",
                    default=1.0,
                    min=-100.0,
                    max=100.0,
                    step=0.01,
                ),
                io.Boolean.Input(
                    "apply_to_ref2va",
                    display_name="允许用于多参考模式",
                    default=False,
                    label_on="允许",
                    label_off="保持直通",
                ),
            ],
            outputs=[
                GLOBAL_LORA_CONTROL.Output(display_name="全局 LoRA 配置"),
                io.String.Output(display_name="全局 LoRA 报告"),
            ],
        )

    @classmethod
    def execute(cls, enabled, lora_name, strength_model, apply_to_ref2va):
        control = {
            "schema": GLOBAL_LORA_CONTROL_SCHEMA,
            "enabled": bool(enabled),
            "lora_name": str(lora_name or NO_LORA),
            "strength_model": float(strength_model),
            "apply_to_ref2va": bool(apply_to_ref2va),
        }
        return io.NodeOutput(control, json.dumps(control, ensure_ascii=False, indent=2))


class XYUEH3AccelerationController(io.ComfyNode):
    """Lazily select the original model or the complete acceleration branch."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_AccelerationController",
            display_name="XYUE_总加速控制器",
            category=CATEGORY,
            description="默认关闭并直接使用原始模型；开启后才执行并使用完整 LoRA、注意力和 TE-Speed 加速链。",
            inputs=[
                io.Boolean.Input(
                    "enabled",
                    display_name="启用完整加速",
                    default=False,
                    label_on="已开启",
                    label_off="已关闭",
                ),
                io.Model.Input("original_model", display_name="原始模型", lazy=True, optional=True),
                io.Model.Input("accelerated_model", display_name="模式1 模型", lazy=True, optional=True),
                io.Model.Input("hq_model", display_name="模式2 模型", lazy=True, optional=True),
                io.Model.Input("experimental_model", display_name="模式3 模型", lazy=True, optional=True),
                GLOBAL_ACCELERATION_CONTROL.Input("global_acceleration", display_name="全局加速控制", optional=True),
            ],
            outputs=[
                io.Model.Output(display_name="最终模型"),
                io.String.Output(display_name="加速状态"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, enabled, original_model=None, accelerated_model=None, hq_model=None, experimental_model=None, global_acceleration=None):
        mode = cls._effective_mode(enabled, global_acceleration)
        if mode == "模式1" and accelerated_model is None:
            return ["accelerated_model"]
        if mode == "模式2" and hq_model is None:
            return ["hq_model"]
        if mode == "模式3" and experimental_model is None:
            return ["experimental_model"]
        if mode == "不启用" and original_model is None:
            return ["original_model"]
        return []

    @classmethod
    def _effective_enabled(cls, enabled, global_acceleration=None):
        return cls._effective_mode(enabled, global_acceleration) != "不启用"

    @classmethod
    def _effective_mode(cls, enabled, global_acceleration=None):
        control = dict(global_acceleration or {})
        if control.get("schema") != GLOBAL_ACCELERATION_CONTROL_SCHEMA:
            return "模式1" if enabled else "不启用"
        mode = normalize_acceleration_mode(control.get("mode"))
        return mode if mode in GLOBAL_ACCELERATION_MODES else ("模式1" if enabled else "不启用")

    @classmethod
    def execute(cls, enabled, original_model=None, accelerated_model=None, hq_model=None, experimental_model=None, global_acceleration=None):
        mode = cls._effective_mode(enabled, global_acceleration)
        selected = {"不启用": original_model, "模式1": accelerated_model, "模式2": hq_model, "模式3": experimental_model}[mode]
        if selected is None:
            raise ValueError("总加速控制器缺少当前分支的模型输入")
        control = dict(global_acceleration or {})
        control_mode = normalize_acceleration_mode(control.get("mode")) if control.get("schema") == GLOBAL_ACCELERATION_CONTROL_SCHEMA else mode
        report = {
            "enabled": mode != "不启用",
            "selected": mode,
            "mode": mode,
            "global_mode": control_mode,
            "stage_enabled": bool(enabled),
        }
        return io.NodeOutput(selected, json.dumps(report, ensure_ascii=False, indent=2))


class XYUEH3GlobalAccelerationManager(io.ComfyNode):
    """Control all stage acceleration branches from one three-mode switch."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_GlobalAccelerationManager",
            display_name="XYUE_全局加速管理器",
            category=CATEGORY,
        description="统一控制所有阶段：不启用、模式1、模式2或实验模式3。",
            inputs=[
                io.Combo.Input(
                    "mode",
                    display_name="全局加速模式",
                    options=list(GLOBAL_ACCELERATION_MODES),
                    default=GLOBAL_ACCELERATION_MODES[0],
                ),
                MULTI_STAGE_CONFIG.Input("multi_stage_config", display_name="多段云端配置", optional=True),
            ],
            outputs=[
                GLOBAL_ACCELERATION_CONTROL.Output(display_name="全局加速控制"),
                io.String.Output(display_name="全局加速报告"),
            ],
        )

    @classmethod
    def execute(cls, mode, multi_stage_config=None):
        config = dict(multi_stage_config or {})
        if config.get("schema") == "xyue.h3.multi-stage-cloud-config/v1":
            mode = config.get("acceleration", {}).get("global_mode", mode)
        control = {
            "schema": GLOBAL_ACCELERATION_CONTROL_SCHEMA,
            "mode": normalize_acceleration_mode(mode),
        }
        return io.NodeOutput(control, json.dumps(control, ensure_ascii=False, indent=2))


ACCELERATION_NODE_CLASSES = [
    XYUEH3LoRASelector,
    XYUEH3GlobalLoRAManager,
    XYUEH3GlobalAccelerationManager,
    XYUEH3AccelerationController,
]
