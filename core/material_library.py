"""Read ComfyUI input media as aggregate-studio material candidates."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any


_FALLBACK_EXTENSIONS = {
    "image": {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"},
    "video": {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".wmv"},
    "audio": {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma"},
}


def media_kind(path: Path) -> str | None:
    mime = mimetypes.guess_type(path.name)[0] or ""
    category = mime.split("/", 1)[0]
    if category in _FALLBACK_EXTENSIONS:
        return category
    suffix = path.suffix.lower()
    return next((kind for kind, extensions in _FALLBACK_EXTENSIONS.items() if suffix in extensions), None)


def scan_material_library(root: Path) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    if not base.is_dir():
        return []
    entries = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        kind = media_kind(path)
        if kind is None:
            continue
        stat = path.stat()
        entries.append({
            "kind": kind,
            "file": path.relative_to(base).as_posix(),
            "size": stat.st_size,
            "modified": int(stat.st_mtime),
        })
    return sorted(entries, key=lambda item: (-item["modified"], item["file"].lower()))


def scan_generated_library(root: Path) -> list[dict[str, Any]]:
    """List generated media as reusable, non-destructive Studio assets."""

    entries = scan_material_library(root)
    for entry in entries:
        entry["source"] = "generated"
        entry["preview"] = {
            "filename": Path(entry["file"]).name,
            "subfolder": str(Path(entry["file"]).parent).replace(".", "").replace("\\", "/").strip("/"),
            "type": "output",
        }
    return entries
