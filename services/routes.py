"""HTTP routes for profile management and document uploads."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import folder_paths
from aiohttp import web
from server import PromptServer

from .api_profiles import delete_profile, get_profile, list_profiles, save_profile
from .prompt_api import request_prompt
from ..core.aggregate_workflow import PLUGIN_ROOT, build_aggregate_workflow, config_from_text, dependency_report, load_workflow
from ..core.material_library import scan_material_library

routes = PromptServer.instance.routes
STUDIO_UI_ROOT = (PLUGIN_ROOT / "studio_ui").resolve()


def _studio_file(asset: str) -> Path:
    relative = str(asset or "index.html").strip("/") or "index.html"
    target = (STUDIO_UI_ROOT / relative).resolve()
    if target != STUDIO_UI_ROOT and STUDIO_UI_ROOT not in target.parents:
        raise web.HTTPBadRequest(text="非法静态资源路径")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise web.HTTPNotFound(text="Studio UI 资源不存在")
    return target


@routes.get("/xyue-h3/studio")
async def xyue_studio_index(request):
    del request
    return web.FileResponse(_studio_file("index.html"), headers={"Cache-Control": "no-cache"})


@routes.get("/xyue-h3/studio/{asset:.*}")
async def xyue_studio_asset(request):
    asset = request.match_info.get("asset", "")
    target = _studio_file(asset)
    cache_control = "public, max-age=31536000, immutable" if target.parent.name == "assets" else "no-cache"
    return web.FileResponse(target, headers={"Cache-Control": cache_control})


@routes.get("/xyue-h3/aggregate/templates")
async def xyue_aggregate_templates(request):
    del request
    templates = []
    for name in ("全程多参考短剧", "多段循环"):
        workflow = load_workflow(name)
        templates.append({
            "name": name,
            "stages": sum(node.get("type") == "XYUE_H3_PromptEditor" for node in workflow.get("nodes", [])),
            "dependencies": dependency_report(workflow),
        })
    return web.json_response({"templates": templates})


@routes.post("/xyue-h3/aggregate/preview")
async def xyue_aggregate_preview(request):
    payload = await request.json()
    workflow, report = build_aggregate_workflow(config_from_text(payload))
    return web.json_response({"report": report, "workflow": workflow})


@routes.get("/xyue-h3/materials")
async def xyue_material_library(request):
    del request
    return web.json_response({"materials": scan_material_library(Path(folder_paths.get_input_directory()))})


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


