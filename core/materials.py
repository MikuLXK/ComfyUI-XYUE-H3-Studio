"""Pure material aliasing, numbering, and mention compilation rules."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from .contracts import (
    AUDIO_PACK_SCHEMA,
    IMAGE_PACK_SCHEMA,
    MATERIAL_PACK_SCHEMA,
    MENTION_REGISTRY_SCHEMA,
    VIDEO_PACK_SCHEMA,
)

_UNSAFE = re.compile(r"[^\w\u3400-\u9fff.\-]+", re.UNICODE)
_PICTURE = re.compile(r"<\s*picture\s*(\d+)\s*>", re.IGNORECASE)
_VIDEO = re.compile(r"<\s*video\s*(\d+)\s*>", re.IGNORECASE)
_AUDIO = re.compile(r"<\s*audio\s*(\d+)\s*>", re.IGNORECASE)
_MENTION = re.compile(r"@[\w\u3400-\u9fff.\-]+", re.UNICODE)
_NUMBERED_MENTION = re.compile(
    r"@(?P<kind>图片|picture|image|视频|video|音频|audio)[_ ]?(?P<index>\d+)(?![\w])",
    re.IGNORECASE,
)


def filename_stem(filename: str) -> str:
    value = unicodedata.normalize("NFKC", str(filename or ""))
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in value:
        value = value.rsplit(".", 1)[0]
    value = _UNSAFE.sub("_", value).strip("_.")
    return value or "素材"


def unique_alias(filename: str, used: set[str], kind: str, numbered: bool = False, index: int = 1) -> str:
    if numbered:
        prefix = {"image": "图片", "video": "视频", "audio": "音频"}.get(kind, "素材")
        candidate = f"@{prefix}{index}"
    else:
        candidate = f"@{filename_stem(filename)}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _active(items: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in (items or ()) if isinstance(item, Mapping) and item.get("enabled")]


def build_image_pack(items: Iterable[Mapping[str, Any]] | None) -> tuple[dict[str, Any], dict[str, str]]:
    active = _active(items)[:9]
    alias_to_token: dict[str, str] = {}
    token_to_alias: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, item in enumerate(active, 1):
        token = f"<Picture {index}>"
        alias = unique_alias(item.get("filename", ""), used, "image", bool(item.get("numbered_alias")), index)
        alias_to_token[alias] = token
        token_to_alias[token] = alias
        entries.append({**item, "index": index, "token": token, "alias": alias})
    return {
        "schema": IMAGE_PACK_SCHEMA,
        "entries": entries,
        "count": len(entries),
        "alias_to_token": alias_to_token,
        "token_to_alias": token_to_alias,
    }, alias_to_token


def build_video_pack(items: Iterable[Mapping[str, Any]] | None) -> tuple[dict[str, Any], dict[str, str]]:
    active = _active(items)[:3]
    alias_to_token: dict[str, str] = {}
    token_to_alias: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    used: set[str] = set()
    soundtrack_index = 0
    for index, item in enumerate(active, 1):
        token = f"<Video {index}>"
        alias = unique_alias(item.get("filename", ""), used, "video", bool(item.get("numbered_alias")), index)
        alias_to_token[alias] = token
        token_to_alias[token] = alias
        audio_token = None
        audio_alias = None
        if item.get("audio") is not None:
            soundtrack_index += 1
            audio_token = f"<Audio {soundtrack_index}>"
            audio_alias = unique_alias(f"{item.get('filename', '')}原声", used, "audio", False, soundtrack_index)
            alias_to_token[audio_alias] = audio_token
            token_to_alias[audio_token] = audio_alias
        entries.append({
            **item,
            "index": index,
            "token": token,
            "alias": alias,
            "audio_token": audio_token,
            "audio_alias": audio_alias,
        })
    return {
        "schema": VIDEO_PACK_SCHEMA,
        "entries": entries,
        "count": len(entries),
        "alias_to_token": alias_to_token,
        "token_to_alias": token_to_alias,
    }, alias_to_token


def build_audio_pack(items: Iterable[Mapping[str, Any]] | None, used: set[str] | None = None, offset: int = 0) -> tuple[dict[str, Any], dict[str, str]]:
    active = _active(items)[:3]
    alias_to_token: dict[str, str] = {}
    token_to_alias: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    aliases = used if used is not None else set()
    for local_index, item in enumerate(active, 1):
        index = offset + local_index
        token = f"<Audio {index}>"
        alias = unique_alias(item.get("filename", ""), aliases, "audio", bool(item.get("numbered_alias")), index)
        alias_to_token[alias] = token
        token_to_alias[token] = alias
        entries.append({**item, "index": index, "token": token, "alias": alias})
    return {
        "schema": AUDIO_PACK_SCHEMA,
        "entries": entries,
        "count": len(entries),
        "alias_to_token": alias_to_token,
        "token_to_alias": token_to_alias,
    }, alias_to_token


def build_material_pack(image_pack: Mapping[str, Any] | None, video_pack: Mapping[str, Any] | None, audio_pack: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    images = dict(image_pack or {})
    videos = dict(video_pack or {})
    audios = dict(audio_pack or {})
    alias_to_token: dict[str, str] = {}
    token_to_alias: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    for pack in (images, videos):
        for key, value in (pack.get("alias_to_token") or {}).items():
            alias_to_token[str(key)] = str(value)
        for key, value in (pack.get("token_to_alias") or {}).items():
            token_to_alias[str(key)] = str(value)
        entries.extend(pack.get("entries") or [])
    video_audio_count = sum(1 for entry in videos.get("entries", []) if entry.get("audio") is not None)
    rebased_audio_entries: list[dict[str, Any]] = []
    for local_index, entry in enumerate(audios.get("entries") or [], 1):
        index = video_audio_count + local_index
        token = f"<Audio {index}>"
        alias = str(entry.get("alias") or f"@音频{index}")
        alias_to_token[alias] = token
        token_to_alias[token] = alias
        rebased_audio_entries.append({**entry, "index": index, "token": token, "alias": alias})
    # Soundtracks are first-class registry entries even though they remain
    # nested on their source video for the native Ref2VA input shape.
    soundtrack_entries: list[dict[str, Any]] = []
    for video in videos.get("entries") or []:
        if video.get("audio") is None or not video.get("audio_token"):
            continue
        soundtrack_entries.append({
            "schema": "xyue-h3/audio-item-v1",
            "media_kind": "video_audio",
            "audio": video.get("audio"),
            "enabled": True,
            "filename": f"{video.get('filename', '')}原声",
            "role": "视频原声",
            "index": int(str(video["audio_token"]).rsplit(" ", 1)[-1].rstrip(">")),
            "token": video["audio_token"],
            "alias": video.get("audio_alias") or f"@音频{video['audio_token'].split()[-1].rstrip('>')}",
        })
    rebased_audios = {**audios, "entries": rebased_audio_entries, "count": len(rebased_audio_entries), "alias_to_token": {entry["alias"]: entry["token"] for entry in rebased_audio_entries}, "token_to_alias": {entry["token"]: entry["alias"] for entry in rebased_audio_entries}}
    entries.extend(soundtrack_entries)
    entries.extend(rebased_audio_entries)
    registry = {
        "schema": MENTION_REGISTRY_SCHEMA,
        "alias_to_token": alias_to_token,
        "token_to_alias": token_to_alias,
        "entries": entries,
        "counts": {
            "pictures": int(images.get("count", 0)),
            "videos": int(videos.get("count", 0)),
            "audios": int(audios.get("count", 0)) + video_audio_count,
        },
    }
    return {
        "schema": MATERIAL_PACK_SCHEMA,
        "images": images,
        "videos": videos,
        "audios": rebased_audios,
        "registry": registry,
    }, registry


def compile_mentions(
    text: str,
    registry: Mapping[str, Any] | None,
    reserved_tokens: Iterable[str] | None = None,
    reserved_aliases: Mapping[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    original = str(text or "")
    source = original
    mapping = dict((registry or {}).get("alias_to_token") or {})
    mapping.update({str(alias): str(token) for alias, token in (reserved_aliases or {}).items()})
    token_aliases = dict((registry or {}).get("token_to_alias") or {})
    numbered_aliases: dict[str, str] = {}
    for token in token_aliases:
        match = re.fullmatch(r"<(Picture|Video|Audio)\s+(\d+)>\s*", str(token), re.IGNORECASE)
        if not match:
            continue
        label, index = match.group(1).title(), match.group(2)
        names = {
            "Picture": ("图片", "picture", "image"),
            "Video": ("视频", "video"),
            "Audio": ("音频", "audio"),
        }[label]
        for name in names:
            # Accept the forms exposed by the editor and common hand-written
            # variants such as @image_9 and @图片 1.
            for separator in ("", "_", " "):
                numbered_aliases[f"@{name}{separator}{index}"] = token
    mapping = {**numbered_aliases, **mapping}
    aliases = sorted(mapping, key=len, reverse=True)
    used: list[str] = []
    for alias in aliases:
        if alias not in source:
            continue
        source = source.replace(alias, mapping[alias])
        used.append(alias)
    tokens = set((registry or {}).get("token_to_alias") or {})
    tokens.update(str(token) for token in (reserved_tokens or ()))
    enforce_tokens = registry is not None or reserved_tokens is not None
    for pattern, label in ((_PICTURE, "Picture"), (_VIDEO, "Video"), (_AUDIO, "Audio")):
        def normalize(match: re.Match[str]) -> str:
            candidate = f"<{label} {int(match.group(1))}>"
            if enforce_tokens and candidate not in tokens:
                raise ValueError(f"存在无效素材引用：{match.group(0)}")
            return candidate
        source = pattern.sub(normalize, source)
    unknown = []
    for match in _MENTION.finditer(original):
        mention = match.group(0).rstrip("。，、；：！？,.;:!?")
        if mention not in mapping and not any(mention.startswith(alias) for alias in mapping):
            unknown.append(mention)
    if unknown:
        raise ValueError(f"存在无效素材引用：{'、'.join(dict.fromkeys(unknown))}")
    return source, tuple(dict.fromkeys(used))
