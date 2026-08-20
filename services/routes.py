"""HTTP routes for profile management and document uploads."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import folder_paths
from aiohttp import web
from server import PromptServer

from .api_profiles import delete_profile, get_profile, list_profiles, save_profile
from .prompt_api import request_prompt
from ..core.aggregate_workflow import PLUGIN_ROOT, build_aggregate_workflow, config_from_text, dependency_report
from ..core.material_library import scan_generated_library, scan_material_library
from ..core.material_sessions import load_material_session, save_material_session

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


@routes.get("/xyue-h3")
async def xyue_studio_shortcut(request):
    del request
    raise web.HTTPFound("/xyue-h3/studio/")


@routes.get("/xyue-h3/studio/{asset:.*}")
async def xyue_studio_asset(request):
    asset = request.match_info.get("asset", "")
    target = _studio_file(asset)
    cache_control = "public, max-age=31536000, immutable" if target.parent.name == "assets" else "no-cache"
    return web.FileResponse(target, headers={"Cache-Control": cache_control})


@routes.get("/xyue-h3/aggregate/templates")
async def xyue_aggregate_templates(request):
    del request
    return web.json_response({
        "templates": [],
        "execution": "dynamic",
        "max_shots": 5,
        "message": "Studio 根据当前项目配置动态构建执行图，不读取固定工作流模板。",
    })


@routes.get("/xyue-h3/models")
async def xyue_studio_models(request):
    del request
    def names(folder: str) -> list[str]:
        try:
            return sorted(folder_paths.get_filename_list(folder))
        except KeyError:
            return []
    if "latent_upscale_models" not in folder_paths.folder_names_and_paths:
        folder_paths.add_model_folder_path("latent_upscale_models", str(Path(folder_paths.models_dir) / "latent_upscale_models"))
    diffusion = names("diffusion_models")
    vaes = names("vae")
    latent = [name for name in names("latent_upscale_models") if "minimax_h3" in name.lower()]
    tiny = ["none", *names("vae_approx")]
    loras = ["不使用 LoRA", *names("loras")]
    return web.json_response({
        "baseModel": diffusion,
        "referenceModel": diffusion,
        "languageModel": names("text_encoders"),
        "videoVae": [name for name in vaes if "minimax_h3" in name.lower()] or vaes,
        "audioVae": [name for name in vaes if "minimax_h3" in name.lower()] or vaes,
        "latentUpscaleModel": latent,
        "tinyVae": tiny,
        "loras": loras,
    })


@routes.post("/xyue-h3/aggregate/preview")
async def xyue_aggregate_preview(request):
    payload = await request.json()
    if "material_overrides" not in payload:
        payload["material_overrides"] = load_material_session(payload.get("studio_id", ""))
    workflow, report = build_aggregate_workflow(config_from_text(payload))
    return web.json_response({"report": report, "workflow": workflow})


@routes.get("/xyue-h3/materials")
async def xyue_material_library(request):
    del request
    input_items = scan_material_library(Path(folder_paths.get_input_directory()))
    output_items = scan_generated_library(Path(folder_paths.get_output_directory()))
    for item in output_items:
        item["file"] = f"{item['file']} [output]"
    return web.json_response({"materials": input_items + output_items})


@routes.get("/xyue-h3/generated")
async def xyue_generated_library(request):
    """Expose output media for Studio history/clip management."""

    del request
    return web.json_response({"materials": scan_generated_library(Path(folder_paths.get_output_directory()))})


def _resolve_media_url(value: str) -> Path:
    parsed = urlparse(str(value or ""))
    query = parse_qs(parsed.query)
    filename = (query.get("filename") or [""])[0]
    subfolder = (query.get("subfolder") or [""])[0]
    media_type = (query.get("type") or ["output"])[0]
    root = Path(folder_paths.get_input_directory() if media_type == "input" else folder_paths.get_output_directory()).resolve()
    if not filename:
        filename = str(value).replace("\\", "/").lstrip("/")
        subfolder = ""
    target = (root / subfolder / filename).resolve()
    if root not in target.parents or not target.is_file():
        raise web.HTTPBadRequest(text=f"剪辑素材不存在：{filename}")
    return target


def _compose_files(payload: dict) -> tuple[Path, str]:
    clips = payload.get("clips")
    if not isinstance(clips, list) or not clips:
        raise web.HTTPBadRequest(text="至少需要一个剪辑片段")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise web.HTTPServiceUnavailable(text="未找到 ffmpeg，无法导出剪辑结果")
    output_root = Path(folder_paths.get_output_directory()).resolve() / "xyue_h3" / "editor"
    output_root.mkdir(parents=True, exist_ok=True)
    output_name = f"edit_{uuid.uuid4().hex[:12]}.mp4"
    output = output_root / output_name
    command = [ffmpeg, "-y"]
    active = [clip for clip in clips if isinstance(clip, dict) and clip.get("enabled", True)]
    filters = []
    concat_inputs = []
    for index, clip in enumerate(active):
        source = _resolve_media_url(str(clip.get("source") or ""))
        start = max(0.0, float(clip.get("in", 0) or 0))
        end = float(clip.get("out", 0) or 0)
        command.extend(["-ss", str(start)])
        if end > start:
            command.extend(["-to", str(end)])
        command.extend(["-i", str(source)])
        volume = 0.0 if clip.get("muted") else max(0.0, min(2.0, float(clip.get("volume", 1.0) or 1.0)))
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2[v{index}]")
        filters.append(f"[{index}:a]asetpts=PTS-STARTPTS,volume={volume}[a{index}]")
        concat_inputs.extend([f"[v{index}]", f"[a{index}]"])
    filters.append("".join(concat_inputs) + f"concat=n={len(active)}:v=1:a=1[outv][outa]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[outv]", "-map", "[outa]", "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    if completed.returncode != 0 or not output.is_file():
        raise web.HTTPBadRequest(text=f"剪辑导出失败：{completed.stderr[-1200:]}")
    return output, output_name


@routes.post("/xyue-h3/editor/export")
async def xyue_editor_export(request):
    payload = await request.json()
    output, output_name = _compose_files(payload)
    del output
    return web.json_response({
        "filename": output_name,
        "subfolder": "xyue_h3/editor",
        "type": "output",
        "url": f"/view?filename={output_name}&subfolder=xyue_h3/editor&type=output",
    })


@routes.post("/xyue-h3/materials/session")
async def xyue_save_material_session(request):
    payload = await request.json()
    overrides = payload.get("material_overrides")
    if not isinstance(overrides, list):
        raise web.HTTPBadRequest(text="material_overrides 必须是数组")
    try:
        save_material_session(payload.get("studio_id", ""), overrides)
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc
    return web.json_response({"ok": True, "count": len(overrides)})


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


