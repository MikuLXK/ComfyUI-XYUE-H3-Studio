"""Stage checkpoint persistence and lazy resume routing."""

from __future__ import annotations

import os

from comfy_api.latest import Types, io, ui

from ..core.contracts import CATEGORY, MAX_STAGES, STUDIO_CONTROL_SCHEMA
from ..services.video_checkpoints import (
    NO_CHECKPOINT,
    checkpoint_report,
    checkpoint_video_options,
    find_latest_stage_checkpoint,
    load_checkpoint_video,
    save_stage_video,
)


CURRENT_STAGE = "运行当前阶段并保存"
SAVED_STAGE = "跳过当前阶段，从保存视频续接"
RESUME_SOURCES = (CURRENT_STAGE, SAVED_STAGE)
MISSING = object()
STUDIO_CONTROL = io.Custom("XYUE_H3_STUDIO_CONTROL")


def _stage_number(stage_name: str) -> int:
    for index, marker in enumerate(("第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段"), start=1):
        if marker in str(stage_name):
            return index
    text = str(stage_name)
    for index in range(MAX_STAGES, 0, -1):
        if f"阶段{index}" in text or f"阶段 {index}" in text:
            return index
    return 1


def _stage_count(studio_control) -> int:
    control = dict(studio_control or {})
    if control.get("schema") != STUDIO_CONTROL_SCHEMA:
        return 3
    return max(1, min(MAX_STAGES, int(control.get("stage_count", 3))))


class XYUEH3StageCheckpointSave(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StageCheckpointSave",
            display_name="XYUE_阶段检查点保存",
            category=CATEGORY,
            description="立即保存当前阶段视频，再把同一个 VIDEO 透传给尾帧截取器。中间阶段失败不会丢失已完成片段。",
            inputs=[
                io.Video.Input("video", display_name="当前阶段视频"),
                io.String.Input("stage_name", display_name="阶段名称", default="第一阶段", multiline=False),
                io.String.Input("filename_prefix", display_name="保存路径前缀", default="xyue_h3/短剧/第一阶段", multiline=False),
                io.Combo.Input("format", display_name="封装格式", options=Types.VideoContainer.as_input(), default="auto"),
                io.Combo.Input("codec", display_name="视频编码", options=Types.VideoCodec.as_input(), default="auto"),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            outputs=[
                io.Video.Output(display_name="已保存视频"),
                io.String.Output(display_name="保存报告"),
            ],
        )

    @classmethod
    def execute(cls, video, stage_name, filename_prefix, format, codec):
        if video is None:
            report = checkpoint_report(stage_name, "skipped", "阶段已禁用，跳过保存", None)
            return io.NodeOutput(None, report)
        saved = save_stage_video(
            video,
            filename_prefix,
            format,
            codec,
            prompt=cls.hidden.prompt,
            extra_pnginfo=cls.hidden.extra_pnginfo,
        )
        report = checkpoint_report(stage_name, "generated", saved.full_path, video)
        preview = ui.PreviewVideo([ui.SavedResult(saved.file, saved.subfolder, io.FolderType.output)])
        return io.NodeOutput(video, report, ui=preview)


class XYUEH3StageResume(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StageResume",
            display_name="XYUE_阶段续接选择",
            category=CATEGORY,
            description=(
                "默认运行并使用当前阶段；切换到保存视频时，只读取检查点，惰性跳过当前阶段及其全部上游生成。"
                "输出应连接尾帧截取器。"
            ),
            inputs=[
                io.Combo.Input("source", display_name="阶段来源", options=list(RESUME_SOURCES), default=CURRENT_STAGE),
                io.Combo.Input(
                    "checkpoint_file",
                    display_name="保存的阶段视频",
                    options=checkpoint_video_options(),
                    default=NO_CHECKPOINT,
                ),
                io.String.Input("stage_name", display_name="阶段名称", default="第一阶段", multiline=False),
                io.Video.Input("generated_video", display_name="刚保存的视频", optional=True, lazy=True),
                io.Boolean.Input(
                    "resume_enabled",
                    display_name="启用续跑",
                    default=False,
                    label_on="继续 ▶",
                    label_off="运行本阶段",
                    tooltip="关闭时运行并保存本阶段；开启时跳过本阶段生成器，直接读取上方选择的保存视频。",
                ),
                io.Video.Input("fallback_video", display_name="前一启用阶段视频", optional=True, lazy=True),
                STUDIO_CONTROL.Input("studio_control", display_name="阶段控制", optional=True),
            ],
            outputs=[
                io.Video.Output(display_name="续接视频"),
                io.String.Output(display_name="续接报告"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, source, checkpoint_file, stage_name, generated_video=MISSING, resume_enabled=False,
                          fallback_video=MISSING, studio_control=None):
        if _stage_number(stage_name) > _stage_count(studio_control):
            return [] if fallback_video is not None else ["fallback_video"]
        effective_source = SAVED_STAGE if bool(resume_enabled) else source
        if effective_source == CURRENT_STAGE and generated_video is None:
            return ["generated_video"]
        return None

    @classmethod
    def execute(cls, source, checkpoint_file, stage_name, generated_video=MISSING, resume_enabled=False,
                fallback_video=MISSING, studio_control=None):
        if _stage_number(stage_name) > _stage_count(studio_control):
            if fallback_video is MISSING or fallback_video is None:
                raise ValueError(f"{stage_name} 已禁用，但没有可透传的前一启用阶段视频。")
            report = checkpoint_report(stage_name, "disabled", "跳过当前阶段", fallback_video)
            return io.NodeOutput(fallback_video, report)
        effective_source = SAVED_STAGE if bool(resume_enabled) else source
        if effective_source == CURRENT_STAGE:
            if generated_video is MISSING or generated_video is None:
                raise ValueError("当前阶段来源未连接“阶段检查点保存”的视频输出。")
            report = checkpoint_report(stage_name, "generated", "本次运行刚保存的视频", generated_video)
            return io.NodeOutput(generated_video, report)

        selected_file = checkpoint_file
        source_name = "checkpoint"
        if not selected_file or selected_file == NO_CHECKPOINT:
            selected_file = find_latest_stage_checkpoint(stage_name)
            source_name = "auto_checkpoint"
        if not selected_file:
            raise ValueError(f"{stage_name} 没有找到可用的阶段保存视频。")
        video, path = load_checkpoint_video(selected_file)
        report = checkpoint_report(stage_name, source_name, os.path.abspath(path), video)
        return io.NodeOutput(video, report)

    @classmethod
    def fingerprint_inputs(cls, source, checkpoint_file, stage_name, generated_video=MISSING, resume_enabled=False,
                           fallback_video=MISSING, studio_control=None):
        if _stage_number(stage_name) > _stage_count(studio_control):
            return "disabled", stage_name, _stage_count(studio_control)
        effective_source = SAVED_STAGE if bool(resume_enabled) else source
        if effective_source != SAVED_STAGE or checkpoint_file == NO_CHECKPOINT:
            return effective_source, stage_name, bool(resume_enabled)
        try:
            _, path = load_checkpoint_video(checkpoint_file)
            return source, stage_name, path, os.path.getmtime(path)
        except (OSError, ValueError):
            return source, stage_name, checkpoint_file


class XYUEH3StageFinish(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_StageFinish",
            display_name="XYUE_阶段流程完成",
            category=CATEGORY,
            description="作为工作流最终输出，保证它前面的阶段检查点保存节点被执行；本节点不会重复写入视频文件。",
            is_output_node=True,
            inputs=[io.Video.Input("video", display_name="最终已保存视频")],
            outputs=[io.Video.Output(display_name="最终视频")],
        )

    @classmethod
    def execute(cls, video):
        return io.NodeOutput(video)


CHECKPOINT_NODE_CLASSES = [XYUEH3StageCheckpointSave, XYUEH3StageResume, XYUEH3StageFinish]
