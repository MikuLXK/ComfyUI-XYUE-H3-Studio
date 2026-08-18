"""Display the five saved stage videos and the final concatenation together."""

from __future__ import annotations

import json
import os
from typing import Any

import folder_paths
from comfy_api.latest import Types, io, ui

from ..core.contracts import CATEGORY, MAX_STAGES, STUDIO_CONTROL_SCHEMA
from .video_concat import concatenate_videos
from ..services.video_checkpoints import save_stage_video


STUDIO_CONTROL = io.Custom("XYUE_H3_STUDIO_CONTROL")
MISSING = object()


def _stage_count(studio_control: dict[str, Any] | None) -> int:
    control = dict(studio_control or {})
    if control.get("schema") != STUDIO_CONTROL_SCHEMA:
        return MAX_STAGES
    return max(1, min(MAX_STAGES, int(control.get("stage_count", MAX_STAGES))))


def _saved_result(report: str | None):
    if not report or report is MISSING:
        return None
    try:
        data = json.loads(str(report))
    except (TypeError, ValueError):
        return None
    file_value = data.get("file")
    if not file_value:
        return None
    output_dir = os.path.abspath(folder_paths.get_output_directory())
    path = os.path.abspath(str(file_value))
    try:
        if os.path.commonpath((output_dir, path)) != output_dir:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(path, output_dir).replace("\\", "/")
    subfolder, filename = os.path.split(relative)
    return ui.SavedResult(filename, subfolder, io.FolderType.output)


class XYUEH3VideoBoard(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="XYUE_H3_VideoBoard",
            display_name="XYUE_五段视频完成面板",
            category=CATEGORY,
            description="右侧以两行三列展示阶段 1-5 和最终合成视频，并统一负责最终拼接、保存和预览。",
            inputs=[
                io.Video.Input("stage1_video", display_name="阶段1视频", lazy=True),
                io.Video.Input("stage2_video", display_name="阶段2视频", optional=True, lazy=True),
                io.Video.Input("stage3_video", display_name="阶段3视频", optional=True, lazy=True),
                io.Video.Input("stage4_video", display_name="阶段4视频", optional=True, lazy=True),
                io.Video.Input("stage5_video", display_name="阶段5视频", optional=True, lazy=True),
                io.String.Input("stage1_report", display_name="阶段1视频报告", force_input=True, lazy=True),
                io.String.Input("stage2_report", display_name="阶段2视频报告", optional=True, force_input=True, lazy=True),
                io.String.Input("stage3_report", display_name="阶段3视频报告", optional=True, force_input=True, lazy=True),
                io.String.Input("stage4_report", display_name="阶段4视频报告", optional=True, force_input=True, lazy=True),
                io.String.Input("stage5_report", display_name="阶段5视频报告", optional=True, force_input=True, lazy=True),
                STUDIO_CONTROL.Input("studio_control", display_name="阶段控制", optional=True),
                io.String.Input("filename_prefix", display_name="最终保存路径", default="xyue_h3/多段/最终合成", multiline=False),
                io.Combo.Input("format", display_name="封装格式", options=Types.VideoContainer.as_input(), default="mp4"),
                io.Combo.Input("codec", display_name="视频编码", options=Types.VideoCodec.as_input(), default="h264"),
            ],
            outputs=[io.Video.Output(display_name="最终合成视频"), io.String.Output(display_name="面板报告")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, stage1_video, stage2_video=None, stage3_video=None, stage4_video=None, stage5_video=None,
                          stage1_report=MISSING, stage2_report=None, stage3_report=None, stage4_report=None,
                          stage5_report=None, studio_control=None, filename_prefix="xyue_h3/多段/最终合成",
                          format="mp4", codec="h264"):
        videos = (stage1_video, stage2_video, stage3_video, stage4_video, stage5_video)
        reports = (stage1_report, stage2_report, stage3_report, stage4_report, stage5_report)
        needed = []
        for index in range(1, _stage_count(studio_control) + 1):
            if videos[index - 1] is None or videos[index - 1] is MISSING:
                needed.append(f"stage{index}_video")
            if reports[index - 1] is None or reports[index - 1] is MISSING:
                needed.append(f"stage{index}_report")
        return needed or None

    @classmethod
    def execute(cls, stage1_video, stage2_video=None, stage3_video=None, stage4_video=None, stage5_video=None,
                stage1_report=None, stage2_report=None, stage3_report=None, stage4_report=None,
                stage5_report=None, studio_control=None, filename_prefix="xyue_h3/多段/最终合成",
                format="mp4", codec="h264"):
        videos = (stage1_video, stage2_video, stage3_video, stage4_video, stage5_video)
        reports = (stage1_report, stage2_report, stage3_report, stage4_report, stage5_report)
        active_count = _stage_count(studio_control)
        stages = []
        previews = []
        active_videos = list(videos[:active_count])
        if any(video is None or video is MISSING for video in active_videos):
            raise ValueError("启用阶段缺少视频输出。")
        for index, report in enumerate(reports, start=1):
            saved = _saved_result(report)
            stages.append({
                "slot": f"stage{index}",
                "active": index <= active_count,
                "report": report,
                "available": index <= active_count and saved is not None,
            })
            if index <= active_count and saved is not None:
                previews.append(saved)
        final_video, _ = concatenate_videos(active_videos)
        saved = save_stage_video(final_video, filename_prefix, format, codec, prompt=cls.hidden.prompt, extra_pnginfo=cls.hidden.extra_pnginfo)
        previews.append(ui.SavedResult(saved.file, saved.subfolder, io.FolderType.output))
        payload = {
            "schema": "xyue-h3/video-board-v1",
            "layout": "3x2",
            "stages": stages,
            "final_file": saved.full_path,
            "status": "saved_and_previewed",
        }
        preview = ui.PreviewVideo(previews)
        return io.NodeOutput(final_video, json.dumps(payload, ensure_ascii=False, indent=2), ui=preview)


VIDEO_BOARD_NODE_CLASSES = [XYUEH3VideoBoard]
