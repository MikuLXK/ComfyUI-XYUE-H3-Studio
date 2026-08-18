"""Save and load resumable stage videos without coupling workflow nodes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

import folder_paths
from comfy.cli_args import args
from comfy_api.latest import InputImpl, Types


NO_CHECKPOINT = "未选择阶段视频"
_VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


@dataclass(frozen=True)
class SavedCheckpoint:
    file: str
    subfolder: str
    full_path: str


def _relative_videos(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    files: list[str] = []
    for root, _, names in os.walk(directory):
        for name in names:
            if os.path.splitext(name)[1].lower() not in _VIDEO_EXTENSIONS:
                continue
            files.append(os.path.relpath(os.path.join(root, name), directory).replace("\\", "/"))
    return files


def checkpoint_video_options() -> list[str]:
    input_files = _relative_videos(folder_paths.get_input_directory())
    output_files = [f"{name} [output]" for name in _relative_videos(folder_paths.get_output_directory())]
    return [NO_CHECKPOINT, *sorted(input_files), *sorted(output_files)]


def find_latest_stage_checkpoint(stage_name: str) -> str | None:
    """Find the newest output video whose filename contains the stage name."""
    marker = str(stage_name).strip()
    if not marker:
        return None
    output_dir = folder_paths.get_output_directory()
    matches: list[tuple[float, str]] = []
    for root, _, names in os.walk(output_dir):
        for name in names:
            if marker not in name or os.path.splitext(name)[1].lower() not in _VIDEO_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            matches.append((os.path.getmtime(path), os.path.relpath(path, output_dir).replace("\\", "/")))
    if not matches:
        return None
    _, relative = max(matches)
    return f"{relative} [output]"


def load_checkpoint_video(file: str):
    if not file or file == NO_CHECKPOINT:
        raise ValueError("已选择从阶段视频续接，但尚未选择保存的视频文件。")
    path = folder_paths.get_annotated_filepath(file)
    if not os.path.isfile(path):
        raise ValueError(f"阶段视频不存在：{file}")
    if os.path.splitext(path)[1].lower() not in _VIDEO_EXTENSIONS:
        raise ValueError(f"阶段续接不支持该视频格式：{os.path.splitext(path)[1]}")
    return InputImpl.VideoFromFile(path), path


def save_stage_video(
    video,
    filename_prefix: str,
    container: str,
    codec: str,
    prompt: Any = None,
    extra_pnginfo: Any = None,
) -> SavedCheckpoint:
    prefix = str(filename_prefix).strip()
    if not prefix:
        raise ValueError("阶段视频文件名前缀不能为空。")

    width, height = video.get_dimensions()
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        prefix,
        folder_paths.get_output_directory(),
        width,
        height,
    )
    extension = Types.VideoContainer.get_extension(container)
    file = f"{filename}_{counter:05}_.{extension}"
    full_path = os.path.join(full_output_folder, file)

    metadata = None
    if not args.disable_metadata:
        metadata = {}
        if extra_pnginfo:
            metadata.update(extra_pnginfo)
        if prompt:
            metadata["prompt"] = prompt
        if not metadata:
            metadata = None

    video.save_to(
        full_path,
        format=Types.VideoContainer(container),
        codec=Types.VideoCodec(codec),
        metadata=metadata,
    )
    return SavedCheckpoint(file=file, subfolder=subfolder, full_path=full_path)


def checkpoint_report(stage_name: str, source: str, file: str, video) -> str:
    if video is None:
        width = height = duration = None
    else:
        width, height = video.get_dimensions()
        duration = float(video.get_duration())
    return json.dumps(
        {
            "schema": "xyue-h3/stage-checkpoint-v1",
            "stage": stage_name,
            "source": source,
            "file": file,
            "width": int(width) if width is not None else None,
            "height": int(height) if height is not None else None,
            "duration": duration,
        },
        ensure_ascii=False,
        indent=2,
    )
