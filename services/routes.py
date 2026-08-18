"""HTTP routes for profile management and document uploads."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import folder_paths
from aiohttp import web
from server import PromptServer

from .api_profiles import delete_profile, get_profile, list_profiles, save_profile
from .prompt_api import request_prompt

routes = PromptServer.instance.routes


def _docs_dir() -> Path:
    path = Path(folder_paths.get_input_directory()) / "xyue_h3_docs"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


@routes.get("/xyue-h3/profiles")
async def xyue_list_profiles(request):
    del request
    return web.json_response({"profiles": list_profiles()})


@routes.post("/xyue-h3/profiles")
async def xyue_save_profile(request):
    payload = await request.json()
    return web.json_response(save_profile(payload))


@routes.delete("/xyue-h3/profiles/{profile_id}")
async def xyue_delete_profile(request):
    delete_profile(request.match_info["profile_id"])
    return web.json_response({"ok": True})


@routes.post("/xyue-h3/profiles/{profile_id}/test")
async def xyue_test_profile(request):
    profile = get_profile(request.match_info["profile_id"])
    result, report = request_prompt(
        profile,
        "Return a valid H3 prompt with minimal content.",
        "文生视频模式",
        {"entries": [], "alias_to_token": {}, "token_to_alias": {}},
        [],
    )
    return web.json_response({"ok": bool(result), "report": {"protocol": report.get("protocol"), "model": profile.get("model")}})


@routes.get("/xyue-h3/profiles/{profile_id}/models")
async def xyue_list_models(request):
    """Fetch model IDs without returning or logging the API key."""
    profile = get_profile(request.match_info["profile_id"])
    base_url = str(profile["base_url"]).rstrip("/")
    models_url = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
    headers = {"Accept": "application/json", **(profile.get("headers") or {})}
    if profile.get("api_key"):
        headers["Authorization"] = f"Bearer {profile['api_key']}"
    try:
        req = Request(models_url, headers=headers, method="GET")
        with urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise web.HTTPBadGateway(text=f"获取模型列表失败：{exc}") from exc
    raw_models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else payload
    models = []
    for item in raw_models or []:
        if isinstance(item, str):
            models.append(item)
        elif isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))
    return web.json_response({"models": sorted(set(models))})


@routes.post("/xyue-h3/documents")
async def xyue_upload_document(request):
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file" or not field.filename:
        raise web.HTTPBadRequest(text="缺少 file 上传字段")
    filename = Path(field.filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md", ".json"}:
        raise web.HTTPBadRequest(text="不支持的文档类型")
    safe_name = "".join(char if char.isalnum() or char in "._-" else "_" for char in filename).strip(".") or "document" + suffix
    target = (_docs_dir() / safe_name).resolve()
    if _docs_dir() not in target.parents:
        raise web.HTTPBadRequest(text="非法文件路径")
    size = 0
    with target.open("wb") as output:
        while True:
            chunk = await field.read_chunk(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > 25 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise web.HTTPRequestEntityTooLarge(max_size=25 * 1024 * 1024, actual_size=size)
            output.write(chunk)
    return web.json_response({"filename": safe_name, "size": size})


@routes.get("/xyue-h3/documents")
async def xyue_list_documents(request):
    del request
    docs = [{"filename": path.name, "size": path.stat().st_size} for path in _docs_dir().iterdir() if path.is_file()]
    return web.json_response({"documents": sorted(docs, key=lambda item: item["filename"])})
