"""Configure multi-stage XYUE H3 workflow prompts, durations, and execution mode."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen


PLUGIN_ROOT = Path(__file__).parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.contracts import MAX_STAGES, normalize_acceleration_mode
from core.generation_options import DEFAULT_SAMPLING_PRESET, SAMPLING_PRESETS, resolve_sampling
from core.h3_prompt import validate_prompt  # noqa: E402
from core.materials import build_image_pack  # noqa: E402

DEFAULT_WORKFLOW = PLUGIN_ROOT / "workflows" / "XYUE_H3_多段循环工作流.json"
USER_WORKFLOWS = PLUGIN_ROOT.parents[1] / "user" / "default" / "workflows"
PROMPT_TITLE = "提示词编辑器"
PROFILE_TITLE = "阶段"
ASSET_TYPES = {
    "XYUE_H3_ImageAsset": ("image", "未选择图片"),
    "XYUE_H3_VideoAsset": ("video", "未选择视频"),
    "XYUE_H3_AudioAsset": ("audio", "未选择音频"),
}

APPLY_NODE_TYPES = {
    "XYUE_H3_ImageAsset",
    "XYUE_H3_VideoAsset",
    "XYUE_H3_AudioAsset",
    "XYUE_H3_PromptEditor",
    "XYUE_H3_PromptEnhancer",
    "XYUE_H3_StageGenerationProfile",
    "XYUE_H3_StudioController",
    "XYUE_H3_GlobalLoRAManager",
    "XYUE_H3_GlobalAccelerationManager",
    "XYUE_H3_AccelerationController",
    "XYUE_H3_StageResume",
    "XYUE_H3_LoRASelector",
    "TESpeedMiniMaxH3",
    "ModelPatchTorchSettings",
    "XYUE_H3_ModeModelSelector",
    "XYUE_H3_MultiStageConfig",
    "UniBlockSwap",
}
API_WIDGET_INPUTS = {
    "XYUE_H3_ImageAsset": (
        ("image", 0), ("enabled", 1), ("alias_mode", 2), ("role", 3), ("fit_mode", 4),
    ),
    "XYUE_H3_VideoAsset": (
        ("video", 0), ("enabled", 1), ("alias_mode", 2), ("role", 3),
        ("start_seconds", 4), ("duration_seconds", 5), ("include_audio", 6),
    ),
    "XYUE_H3_AudioAsset": (
        ("audio", 0), ("enabled", 1), ("alias_mode", 2), ("role", 3),
        ("voice_anchor", 4), ("start_seconds", 5), ("duration_seconds", 6),
        ("gain_db", 7), ("normalize_peak", 8),
    ),
    "XYUE_H3_PromptEditor": (("mode", 0), ("duration", 1), ("draft", 2), ("stage_index", 3)),
    "XYUE_H3_PromptEnhancer": (("mode", 0), ("duration", 1), ("profile_id", 2), ("enabled", 3), ("stage_index", 4)),
    "XYUE_H3_StudioController": (
        ("global_enabled", 0), ("aspect", 1), ("resolution", 2), ("duration", 3),
        ("steps", 4), ("audio_steps", 5), ("scheduler", 6), ("seed", 7), ("reference_size", 9),
        ("sampling_preset", 10), ("stage_count", 11),
    ),
    "XYUE_H3_StageGenerationProfile": (
        ("aspect", 0), ("resolution", 1), ("duration", 2), ("steps", 3),
        ("audio_steps", 4), ("scheduler", 5), ("seed", 6), ("reference_size", 8),
        ("sampling_preset", 9), ("stage_name", 10),
    ),
    "XYUE_H3_GenerationProfile": (
        ("aspect", 0), ("resolution", 1), ("duration", 2), ("steps", 3),
        ("audio_steps", 4), ("scheduler", 5), ("seed", 6), ("reference_size", 8),
        ("sampling_preset", 9),
    ),
    "XYUE_H3_GlobalLoRAManager": (
        ("enabled", 0), ("lora_name", 1), ("strength_model", 2), ("apply_to_ref2va", 3),
    ),
    "XYUE_H3_GlobalAccelerationManager": (("mode", 0),),
    "XYUE_H3_LoRASelector": (("lora_name", 0), ("strength_model", 1)),
    "TESpeedMiniMaxH3": (
        ("processing_control_value", 0),
        ("processing_percent_1", 1),
        ("processing_percent_2", 2),
        ("mcs", 3),
        ("device", 4),
        ("mode", 5),
    ),
    "XYUE_H3_StageResume": (
        ("source", 0), ("checkpoint_file", 1), ("stage_name", 2), ("resume_enabled", 3),
    ),
    "XYUE_H3_ModeModelSelector": (
        ("mode", 0), ("base_model", 1), ("reference_model", 2),
        ("language_model", 3), ("video_vae", 4), ("audio_vae", 5),
    ),
    "XYUE_H3_MultiStageConfig": (("config_text", 0),),
}

MODEL_WIDGET_FIELDS = {
    "mode": 0,
    "base_model": 1,
    "reference_model": 2,
    "language_model": 3,
    "video_vae": 4,
    "audio_vae": 5,
}

TE_WIDGET_FIELDS = {
    "processing_control_value": 0,
    "processing_percent_1": 1,
    "processing_percent_2": 2,
    "mcs": 3,
    "device": 4,
    "mode": 5,
}

# 采样参数在 profile 节点 widgets 中相对首采样控件的偏移。
# GenerationProfile/StageGenerationProfile 起始索引 9，StudioController 起始索引 10。
SAMPLING_WIDGET_FIELDS = {
    "sampling_preset": 0,
}

SAMPLING_PRESET_KEYS = {
    "mode": "sampling_mode",
    "coarse_steps": "coarse_steps",
    "upscale_factor": "upscale_factor",
    "refine_pass": "refine_pass",
    "extend_sigmas": "extend_sigmas",
}

ASSET_WIDGET_FIELDS = {
    "image": {
        "type": "XYUE_H3_ImageAsset",
        "fields": {"file": 0, "enabled": 1, "alias_mode": 2, "role": 3, "fit_mode": 4},
    },
    "video": {
        "type": "XYUE_H3_VideoAsset",
        "fields": {
            "file": 0, "enabled": 1, "alias_mode": 2, "role": 3,
            "start_seconds": 4, "duration_seconds": 5, "include_audio": 6,
        },
    },
    "audio": {
        "type": "XYUE_H3_AudioAsset",
        "fields": {
            "file": 0, "enabled": 1, "alias_mode": 2, "role": 3, "voice_anchor": 4,
            "start_seconds": 5, "duration_seconds": 6, "gain_db": 7, "normalize_peak": 8,
        },
    },
}

MANAGER_SLOT_SPECS = {
    "image": ("XYUE_H3_ImageManager", "image_"),
    "video": ("XYUE_H3_VideoManager", "video_"),
    "audio": ("XYUE_H3_AudioManager", "audio_"),
}

MODEL_FOLDERS = {
    "base_model": "diffusion_models",
    "reference_model": "diffusion_models",
    "language_model": "text_encoders",
    "video_vae": "vae",
    "audio_vae": "vae",
}

MODE_KEYS = {
    "文生视频模式": "T2VA",
    "首帧生视频模式": "I2VA",
    "首尾帧生视频模式": "FL2VA",
    "尾帧续写模式": "L2VA",
    "多参考模式": "Ref2VA",
}

# 生成方式 → 每段应使用的生成模式（按段）
GENERATION_MODE_PLANS = {
    "all_reference": ["Ref2VA", "Ref2VA", "Ref2VA"],
    "continuation": ["Ref2VA", "I2VA", "I2VA"],
}

OUTPUT_DIR = PLUGIN_ROOT.parents[1] / "output"
MODELS_DIR = PLUGIN_ROOT.parents[1] / "models"


def _manager_slot_order(workflow: dict, kind: str) -> dict[int, int]:
    """Map physical slot number to source node id using the matching manager links."""

    manager_type, prefix = MANAGER_SLOT_SPECS[kind]
    manager = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == manager_type),
        None,
    )
    if manager is None:
        return {}
    links = {int(link[0]): link for link in workflow.get("links", [])}
    order: dict[int, int] = {}
    for item in manager.get("inputs") or []:
        name = str(item.get("name") or "")
        if not name.startswith(prefix):
            continue
        try:
            slot = int(name[len(prefix):])
        except ValueError:
            continue
        link_id = item.get("link")
        if link_id is not None and int(link_id) in links:
            order[slot] = links[int(link_id)][1]
    return order


def fetch_live_canvas(server: str = "http://127.0.0.1:8188", max_age_seconds: int = 120) -> dict:
    """Read the latest browser-published XYUE H3 canvas snapshot.

    Prefer the live HTTP endpoint when the server is reachable; otherwise fall
    back to the local snapshot file written by the browser extension. A stale
    snapshot (older than max_age_seconds) is rejected instead of being used to
    patch a canvas the browser has already replaced.
    """

    local_snapshot = PLUGIN_ROOT.parents[1] / "user" / "default" / "xyue_h3_studio" / "live_canvas.json"
    snapshot = None
    source = None
    url = server.rstrip("/") + "/userdata/" + quote("xyue_h3_studio/live_canvas.json", safe="/")
    try:
        with urlopen(url, timeout=10) as response:
            snapshot = json.loads(response.read().decode("utf-8-sig"))
            source = "server"
    except HTTPError as error:
        if error.code != 404:
            raise
    except (TimeoutError, OSError, ValueError):
        pass
    if snapshot is None and local_snapshot.exists():
        snapshot = json.loads(local_snapshot.read_text(encoding="utf-8-sig"))
        source = "local"
    if snapshot is None:
        raise ValueError("尚未收到当前画布快照；请刷新一次 ComfyUI 前端页面")
    captured = str(snapshot.get("captured_at") or "")
    age = _snapshot_age(captured)
    if age is not None and age > max_age_seconds:
        raise ValueError(
            f"当前画布快照已过期（{age} 秒前，来源 {source}）；请刷新前端页面后重试"
        )
    workflow = snapshot.get("workflow") if isinstance(snapshot, dict) else None
    if not isinstance(workflow, dict):
        raise ValueError("当前画布快照缺少可用 workflow")
    return snapshot


def _snapshot_age(captured_at: str) -> int | None:
    if not captured_at:
        return None
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age = now - parsed
        if age.total_seconds() < 0:
            return 0
        return int(age.total_seconds())
    except ValueError:
        return None


def _output_videos() -> list[tuple[Path, float]]:
    """List saved videos in the output directory with their modified time."""
    if not OUTPUT_DIR.is_dir():
        return []
    results: list[tuple[Path, float]] = []
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}:
            results.append((path, path.stat().st_mtime))
    return results


def auto_resume_files(workflow: dict, start_stage: int) -> list[str]:
    """Auto-fill resume files from the newest saved stage videos.

    Uses the StageCheckpointSave filename prefixes in the workflow to match
    which stage each output file belongs to. Returns a list aligned with the
    all prebuilt stages; stages before start_stage that have no match are empty.
    """
    prefixes: dict[int, str] = {}
    for node in workflow.get("nodes", []):
        if node.get("type") != "XYUE_H3_StageCheckpointSave":
            continue
        values = node.get("widgets_values") or []
        title = str(node.get("title") or "")
        stage = next(
            (index for index, label in enumerate(
                ["第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段",
                 "第六阶段", "第七阶段", "第八阶段", "第九阶段", "第十阶段"], start=1
            ) if label in title),
            None,
        )
        if stage is None:
            continue
        prefix = str(values[1] if len(values) > 1 else "").replace("\\", "/")
        prefixes[stage] = prefix
    files: list[str] = [""] * max(prefixes, default=0)
    if not prefixes:
        return files
    videos = sorted(_output_videos(), key=lambda item: item[1], reverse=True)
    for stage, prefix in prefixes.items():
        if stage >= start_stage or not prefix:
            continue
        needle = prefix.split("/")[-1]
        match = next((path for path, _ in videos if needle in path.name), None)
        if match is not None:
            rel = str(match.relative_to(OUTPUT_DIR)).replace("\\", "/")
            files[stage - 1] = f"{rel} [output]"
    return files


def report_outputs(workflow: dict) -> dict:
    """Summarize saved stage videos and the final concatenated video."""
    videos = sorted(_output_videos(), key=lambda item: item[1], reverse=True)
    stages: list[dict] = []
    for node in workflow.get("nodes", []):
        if node.get("type") != "XYUE_H3_StageCheckpointSave":
            continue
        values = node.get("widgets_values") or []
        prefix = str(values[1] if len(values) > 1 else "").replace("\\", "/")
        needle = prefix.split("/")[-1]
        match = next((path for path, _ in videos if needle in path.name), None)
        stages.append({
            "stage": str(node.get("title") or ""),
            "prefix": prefix,
            "latest": str(match.relative_to(OUTPUT_DIR)).replace("\\", "/") if match else None,
        })
    final = None
    for node in workflow.get("nodes", []):
        if node.get("type") != "SaveVideo":
            continue
        values = node.get("widgets_values") or []
        prefix = str(values[0] if len(values) > 0 else "").replace("\\", "/")
        needle = prefix.split("/")[-1]
        match = next((path for path, _ in videos if needle in path.name), None)
        if match is not None:
            final = str(match.relative_to(OUTPUT_DIR)).replace("\\", "/")
            break
    return {
        "output_dir": str(OUTPUT_DIR),
        "stages": stages,
        "final_video": final,
        "all_videos": [str(path.relative_to(OUTPUT_DIR)).replace("\\", "/") for path, _ in videos],
    }


def write_pending_apply(workflow: dict, output: Path, auto_queue: bool = False) -> Path:
    """Write a live-canvas patch the browser extension applies in place."""

    payload = {
        "schema": "xyue.h3.pending_apply/v1",
        "version": int(time.time() * 1000),
        "auto_queue": bool(auto_queue),
        "graph_replace": False,
        "workflow": None,
        "nodes": [
            {
                "id": node.get("id"),
                "type": node.get("type"),
                "title": node.get("title"),
                "widgets_values": node.get("widgets_values"),
            }
            for node in workflow.get("nodes", [])
            if node.get("type") in APPLY_NODE_TYPES
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def wait_for_pending_applied(
    server: str,
    pending: Path,
    workflow: dict,
    timeout_seconds: int = 90,
    poll_seconds: float = 3.0,
) -> bool:
    """Poll the live canvas until the pending patch is applied by the browser.

    The browser extension consumes pending_apply.json and republishes a fresh
    snapshot. Compare the snapshot's prompt drafts against the ones in the
    workflow we configured; a match means the patch landed.
    """
    expected_drafts = {
        int(node["id"]): str(node["widgets_values"][2] or "").strip()
        for node in workflow.get("nodes", [])
        if node.get("type") == "XYUE_H3_PromptEditor"
    }
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not pending.exists():
            break
        try:
            snapshot = fetch_live_canvas(server, max_age_seconds=timeout_seconds + 30)
            drafts = {
                int(node["id"]): str(node["widgets_values"][2] or "").strip()
                for node in snapshot.get("workflow", {}).get("nodes", [])
                if node.get("type") == "XYUE_H3_PromptEditor"
            }
            if drafts and all(
                drafts.get(node_id) == draft for node_id, draft in expected_drafts.items()
            ):
                return True
        except ValueError:
            pass
        time.sleep(poll_seconds)
    return not pending.exists()


def inspect_materials(workflow: dict) -> dict:
    """Inspect static workflow asset selections without executing media nodes."""

    entries: list[dict] = []
    active_counts = {"image": 0, "video": 0, "audio": 0}
    for node in workflow.get("nodes", []):
        spec = ASSET_TYPES.get(node.get("type"))
        if spec is None:
            continue
        kind, empty_label = spec
        values = node.get("widgets_values") or []
        selected_file = str(values[0] if len(values) > 0 else "").strip()
        enabled = bool(values[1]) if len(values) > 1 else False
        imported = bool(selected_file and selected_file != empty_label and selected_file.upper() != "UNKNOWN")
        execution_index = None
        if imported and enabled:
            active_counts[kind] += 1
            execution_index = active_counts[kind]
        entries.append({
            "node_id": node.get("id"),
            "title": node.get("title") or node.get("type"),
            "kind": kind,
            "file": selected_file or empty_label,
            "imported": imported,
            "enabled": enabled,
            "active": imported and enabled,
            "execution_index": execution_index,
        })
    return {
        "entries": entries,
        "selected_counts": {
            kind: sum(1 for entry in entries if entry["kind"] == kind and entry["imported"])
            for kind in active_counts
        },
        "active_counts": active_counts,
        "has_any_imported": any(entry["imported"] for entry in entries),
        "has_any_active": any(entry["active"] for entry in entries),
    }


def configure_api_prompt(api_document: dict, workflow: dict) -> dict:
    """Copy configured widget values into an API-format prompt from the same workflow."""

    document = dict(api_document or {})
    prompt = document.get("prompt") if isinstance(document.get("prompt"), dict) else document
    if not isinstance(prompt, dict):
        raise ValueError("API prompt JSON 必须是节点映射或包含 prompt 节点映射")
    updated = 0
    for node in workflow.get("nodes", []):
        node_type = str(node.get("type") or "")
        api_node = prompt.get(str(node.get("id")))
        if not isinstance(api_node, dict) or api_node.get("class_type") != node_type:
            continue
        inputs = api_node.setdefault("inputs", {})
        values = node.get("widgets_values")
        if node_type == "XYUE_H3_AccelerationController":
            enabled = values[0] if isinstance(values, list) else values
            inputs["enabled"] = bool(enabled)
            updated += 1
            continue
        if not isinstance(values, list):
            continue
        for name, index in API_WIDGET_INPUTS.get(node_type, ()):
            if index < len(values):
                inputs[name] = values[index]
                updated += 1
    if updated == 0:
        raise ValueError("API prompt 与目标工作流不匹配，未找到可同步的 XYUE H3 节点")
    return document


def _set_acceleration(workflow: dict, settings: dict, *, require_global: bool = True) -> None:
    if not settings:
        return
    if "enabled" in settings:
        enabled = bool(settings["enabled"])
        for node in workflow.get("nodes", []):
            if node.get("type") != "XYUE_H3_AccelerationController":
                continue
            current = node.get("widgets_values")
            node["widgets_values"] = [enabled] if isinstance(current, list) else enabled
    if "global_mode" in settings:
        mode = normalize_acceleration_mode(settings["global_mode"])
        manager = next(
            (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_GlobalAccelerationManager"),
            None,
        )
        if manager is None:
            if require_global:
                raise ValueError("目标工作流缺少 XYUE_H3_GlobalAccelerationManager")
        else:
            manager["widgets_values"] = [mode]
    mode = normalize_acceleration_mode(settings.get("global_mode", "不启用"))
    te = dict(settings.get("te") or {})
    if te and mode in ("模式1", "模式3"):
        for node in workflow.get("nodes", []):
            if node.get("type") != "TESpeedMiniMaxH3":
                continue
            values = list(node.get("widgets_values") or [])
            values.extend([None] * (6 - len(values)))
            for name, index in TE_WIDGET_FIELDS.items():
                if name in te:
                    values[index] = te[name]
            node["widgets_values"] = values
        te_mode = str(te.get("mode") or "")
        lora_name = str((settings.get("lora") or {}).get("name") or "").lower()
        if te_mode and lora_name:
            mismatch = (
                ("4-step" in te_mode and "4step" not in lora_name and "4_step" not in lora_name)
                or ("8-step" in te_mode and "8step" not in lora_name and "8_step" not in lora_name)
            )
            if mismatch:
                print(f"警告：TE 模式 {te_mode} 与 LoRA 文件名 {lora_name} 的步数不一致，请确认搭配")
    stages = list(settings.get("stages") or [])
    if stages:
        _set_stage_acceleration(workflow, stages)
    lora = dict(settings.get("lora") or {})
    if stages or not lora:
        return
    manager = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_GlobalLoRAManager"),
        None,
    )
    if manager is None:
        if require_global:
            raise ValueError("目标工作流缺少 XYUE_H3_GlobalLoRAManager")
        return
    values = list(manager.get("widgets_values") or [])
    values.extend([None] * (4 - len(values)))
    if "enabled" in lora:
        values[0] = bool(lora["enabled"])
    if "name" in lora:
        values[1] = str(lora["name"])
    if "strength" in lora:
        values[2] = float(lora["strength"])
    if "apply_to_ref2va" in lora:
        values[3] = bool(lora["apply_to_ref2va"])
    manager["widgets_values"] = values


def _set_stage_acceleration(workflow: dict, stages: list[dict]) -> None:
    """Apply per-stage LoRA and TE settings to their own selector/speed nodes."""

    selectors = [node for node in _stage_nodes(workflow, "XYUE_H3_LoRASelector") if "模式3" not in str(node.get("title", ""))]
    speed_nodes = [node for node in _stage_nodes(workflow, "TESpeedMiniMaxH3") if "模式3" not in str(node.get("title", ""))]
    if len(selectors) < len(stages) or len(speed_nodes) < len(stages):
        raise ValueError(f"阶段独立加速需要至少 {len(stages)} 个 LoRASelector 和 TESpeedMiniMaxH3")
    for index, stage in enumerate(stages):
        stage_y = sorted({round(float(node.get("pos", [0, 0])[1]), 3) for node in selectors})[index]
        stage_selectors = [node for node in selectors if round(float(node.get("pos", [0, 0])[1]), 3) == stage_y]
        speed_y = sorted({round(float(node.get("pos", [0, 0])[1]), 3) for node in speed_nodes})[index]
        stage_speed_nodes = [node for node in speed_nodes if round(float(node.get("pos", [0, 0])[1]), 3) == speed_y]
        stage_lora = dict(stage.get("lora") or {})
        if stage_lora:
            for selector in stage_selectors:
                values = list(selector.get("widgets_values") or [])
                values.extend([None] * (2 - len(values)))
                if "name" in stage_lora:
                    values[0] = str(stage_lora["name"])
                if "strength" in stage_lora:
                    values[1] = float(stage_lora["strength"])
                selector["widgets_values"] = values
        stage_te = dict(stage.get("te") or {})
        if stage_te:
            for speed_node in stage_speed_nodes:
                values = list(speed_node.get("widgets_values") or [])
                values.extend([None] * (6 - len(values)))
                for name, widget_index in TE_WIDGET_FIELDS.items():
                    if name in stage_te:
                        values[widget_index] = stage_te[name]
                speed_node["widgets_values"] = values
    manager = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_GlobalLoRAManager"),
        None,
    )
    if manager is None:
        raise ValueError("目标工作流缺少 XYUE_H3_GlobalLoRAManager")
    manager["widgets_values"][0] = False


def _set_material_overrides(workflow: dict, overrides: list[dict]) -> None:
    """Apply explicit physical-slot asset selections from a multi-stage plan."""

    nodes_by_kind = {
        kind: [node for node in workflow.get("nodes", []) if node.get("type") == spec["type"]]
        for kind, spec in ASSET_WIDGET_FIELDS.items()
    }
    for override in overrides:
        kind = str(override.get("kind") or "").strip().lower()
        if kind not in ASSET_WIDGET_FIELDS:
            raise ValueError(f"未知素材类型：{kind or '(空)'}")
        slot = int(override.get("slot", 0))
        order = _manager_slot_order(workflow, kind)
        if order:
            node_id = order.get(slot)
            node = next(
                (candidate for candidate in workflow.get("nodes", []) if candidate.get("id") == node_id),
                None,
            )
            if node is None:
                raise ValueError(f"{kind} 素材槽位 {slot} 未连接到管理器")
        else:
            nodes = sorted(
                nodes_by_kind[kind],
                key=lambda candidate: int(candidate.get("id") or 0),
            )
            if not 1 <= slot <= len(nodes):
                raise ValueError(f"{kind} 素材槽位超出范围：{slot}")
            node = nodes[slot - 1]
        values = list(node.get("widgets_values") or [])
        fields = ASSET_WIDGET_FIELDS[kind]["fields"]
        values.extend([None] * (max(fields.values()) + 1 - len(values)))
        for name, index in fields.items():
            if name in override:
                values[index] = override[name]
        node["widgets_values"] = values


def _seed_control_value(stage_settings: dict, fallback: str = "randomize") -> str:
    return str(stage_settings.get("seed_control") or fallback)


def _remembered_seeds() -> list[int]:
    saved = _read_last_config()
    return [int(value) for value in (saved.get("seeds") or []) if isinstance(value, int)]


def apply_seed_memory(plan: dict, workflow: dict) -> dict:
    """Resolve seed_control=increment/decrement using remembered seeds.

    When a stage uses incremental seed control but does not pin an explicit
    seed, continue from the last remembered seed for that stage. The applied
    seeds are stored back in last_config for the next run.
    """
    generation = dict(plan.get("generation") or {})
    if not generation:
        return plan
    remembered = _remembered_seeds()
    stages = list(generation.get("stages") or [])
    new_seeds: list[int] = []
    changed = False
    for index, stage in enumerate(stages[:10]):
        stage = dict(stage)
        control = _seed_control_value(stage)
        last = remembered[index] if index < len(remembered) else None
        if "seed" not in stage and control in {"increment", "decrement"} and last is not None:
            step = 1 if control == "increment" else -1
            stage["seed"] = last + step
            changed = True
        if "seed" in stage:
            new_seeds.append(int(stage["seed"]))
        stages[index] = stage
    if changed:
        generation["stages"] = stages
        plan = dict(plan)
        plan["generation"] = generation
    return plan


def _set_sampling_widgets(values: list, base: int, sampling: dict) -> None:
    """Write sampling settings into profile node widgets starting at `base`.

    A named preset fills in the widgets it controls so the canvas state matches
    the effective parameters; explicitly provided fields still win.
    """
    sampling = dict(sampling or {})
    preset = str(sampling.get("sampling_preset") or "")
    if preset not in SAMPLING_PRESETS:
        preset = DEFAULT_SAMPLING_PRESET
        sampling["sampling_preset"] = preset
    if preset:
        merged = dict(sampling)
        preset_values = SAMPLING_PRESETS.get(preset)
        if preset_values:
            for key, widget in SAMPLING_PRESET_KEYS.items():
                merged[widget] = preset_values[key]
        sampling = merged
    for name, offset in SAMPLING_WIDGET_FIELDS.items():
        if name in sampling:
            values[base + offset] = sampling[name]


def _set_generation_controls(workflow: dict, settings: dict, profiles: list[dict]) -> None:
    if not settings:
        return
    studio = next(node for node in workflow["nodes"] if node.get("type") == "XYUE_H3_StudioController")
    global_values = list(studio.get("widgets_values") or [])[:12]
    global_values.extend([None] * (12 - len(global_values)))
    global_settings = dict(settings.get("global") or {})
    if "global_enabled" in settings:
        global_values[0] = bool(settings["global_enabled"])
    fields = {
        "aspect": 1,
        "resolution": 2,
        "duration": 3,
        "steps": 4,
        "audio_steps": 5,
        "scheduler": 6,
        "seed": 7,
        "seed_control": 8,
        "reference_size": 9,
    }
    for name, index in fields.items():
        if name in global_settings:
            global_values[index] = global_settings[name]
    _set_sampling_widgets(global_values, 10, dict(global_settings.get("sampling") or {}))
    studio["widgets_values"] = global_values

    stages = list(settings.get("stages") or [])
    for profile, stage_settings in zip(profiles, stages):
        values = list(profile.get("widgets_values") or [])[:11]
        values.extend([None] * (11 - len(values)))
        for name, index in {
            "aspect": 0,
            "resolution": 1,
            "duration": 2,
            "steps": 3,
            "audio_steps": 4,
            "scheduler": 5,
            "seed": 6,
            "seed_control": 7,
            "reference_size": 8,
        }.items():
            if name in stage_settings:
                values[index] = stage_settings[name]
        _set_sampling_widgets(values, 9, dict(stage_settings.get("sampling") or {}))
        profile["widgets_values"] = values


def _set_models(workflow: dict, models: list[dict]) -> None:
    """Apply per-stage model selector values from a multi-stage plan."""
    if not models:
        return
    selectors = _stage_nodes(workflow, "XYUE_H3_ModeModelSelector")
    if len(selectors) < len(models):
        raise ValueError(f"模型配置需要至少 {len(models)} 个 XYUE_H3_ModeModelSelector 节点")
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            continue
        values = list(selectors[index].get("widgets_values") or [])
        values.extend([None] * (max(MODEL_WIDGET_FIELDS.values()) + 1 - len(values)))
        for name, widget_index in MODEL_WIDGET_FIELDS.items():
            if name in model and model[name] is not None:
                values[widget_index] = model[name]
        selectors[index]["widgets_values"] = values


def inspect_models(workflow: dict) -> list[dict]:
    """Inspect per-stage model selector selections from a workflow."""
    entries: list[dict] = []
    for node in _stage_nodes(workflow, "XYUE_H3_ModeModelSelector"):
        values = list(node.get("widgets_values") or [])
        values.extend([None] * (6 - len(values)))
        entries.append({
            "node_id": node.get("id"),
            "title": node.get("title") or node.get("type"),
            "mode": values[0],
            "base_model": values[1],
            "reference_model": values[2],
            "language_model": values[3],
            "video_vae": values[4],
            "audio_vae": values[5],
        })
    return entries


def _sampling_entry(values: list, base: int) -> dict:
    resolved = resolve_sampling(values[base])
    return {"sampling_preset": resolved["preset"], **{key: value for key, value in resolved.items() if key != "preset"}}


def inspect_sampling(workflow: dict) -> dict:
    """Inspect global and per-stage sampling configuration from a workflow."""
    global_entry: dict = {}
    controller = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_StudioController"),
        None,
    )
    if controller is not None:
        values = list(controller.get("widgets_values") or [])
        values.extend([None] * (12 - len(values)))
        global_entry = _sampling_entry(values, 10)
    stages: list[dict] = []
    for node in _stage_nodes(workflow, "XYUE_H3_StageGenerationProfile"):
        values = list(node.get("widgets_values") or [])
        values.extend([None] * (11 - len(values)))
        stages.append({
            "node_id": node.get("id"),
            "title": node.get("title") or node.get("type"),
            **_sampling_entry(values, 9),
        })
    return {"global": global_entry, "stages": stages}


def _model_path(name: str, field: str) -> Path:
    folder = field if field in MODEL_FOLDERS.values() else MODEL_FOLDERS.get(field, "diffusion_models")
    return MODELS_DIR / folder / str(name or "").replace("\\", "/")


def _model_exists(name: str, field: str) -> bool:
    if not name:
        return True
    return _model_path(name, field).is_file()


def _scan_folder(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    values: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".bin"}:
            values.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(values)


def list_available_models() -> dict[str, list[str]]:
    """List all locally available diffusion/text/VAE/LoRA files."""
    return {
        "diffusion_models": _scan_folder(MODELS_DIR / "diffusion_models"),
        "text_encoders": _scan_folder(MODELS_DIR / "text_encoders"),
        "vae": _scan_folder(MODELS_DIR / "vae"),
        "loras": _scan_folder(MODELS_DIR / "loras"),
    }


def validate_lora_files(acceleration: dict | None) -> list[str]:
    """Verify per-stage/global LoRA names exist; return missing descriptions."""
    missing: list[str] = []
    settings = dict(acceleration or {})
    lora = dict(settings.get("lora") or {})
    name = str(lora.get("name") or "")
    if name and name != "不使用 LoRA":
        path = MODELS_DIR / "loras" / name.replace("\\", "/")
        if not path.is_file():
            missing.append(f"全局 LoRA：{name}")
    for index, stage in enumerate(list(settings.get("stages") or [])[:10]):
        stage_lora = dict(stage.get("lora") or {})
        stage_name = str(stage_lora.get("name") or "")
        if stage_name and stage_name != "不使用 LoRA":
            path = MODELS_DIR / "loras" / stage_name.replace("\\", "/")
            if not path.is_file():
                missing.append(f"第{index + 1}段 LoRA：{stage_name}")
    return missing


def validate_model_files(models: list[dict]) -> list[str]:
    """Verify referenced model/VAE files exist; return missing file descriptions."""
    missing: list[str] = []
    for index, model in enumerate(models or []):
        if not isinstance(model, dict):
            continue
        for name, field in MODEL_FOLDERS.items():
            value = model.get(name)
            if value and not _model_exists(value, field):
                missing.append(f"第{index + 1}段 {field}：{value}")
    return missing


def resolve_generation_mode(workflow: dict, generation: dict | None) -> str:
    """Determine workflow generation style: all_reference or continuation."""
    if generation and str(generation.get("generation_mode") or ""):
        mode = str(generation["generation_mode"])
        if mode not in GENERATION_MODE_PLANS:
            raise ValueError(f"未知生成方式：{mode}（可选 {', '.join(GENERATION_MODE_PLANS)}）")
        return mode
    has_continuation = any(
        node.get("type") == "XYUE_H3_ContinuationReference"
        for node in workflow.get("nodes", [])
    )
    return "all_reference" if has_continuation else "continuation"


def validate_mode_plan(models: list[dict] | None, workflow: dict, generation: dict | None) -> list[str]:
    """Check per-stage generation modes match the workflow style."""
    if not models:
        return []
    style = resolve_generation_mode(workflow, generation)
    expected = GENERATION_MODE_PLANS[style]
    warnings: list[str] = []
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            continue
        mode_label = model.get("mode")
        mode_key = MODE_KEYS.get(str(mode_label or ""))
        if mode_key is None:
            continue
        expected_mode = expected[index] if index < len(expected) else expected[-1]
        if mode_key != expected_mode:
            warnings.append(
                f"第{index + 1}段模式 {mode_label} 与工作流生成方式不匹配（应为 {expected_mode}，对应"
                f"{[k for k, v in MODE_KEYS.items() if v == expected_mode][0]}）"
            )
    return warnings


def _stage_nodes(workflow: dict, node_type: str) -> list[dict]:
    nodes = [node for node in workflow.get("nodes", []) if node.get("type") == node_type]
    if node_type in {
        "XYUE_H3_PromptEditor",
        "XYUE_H3_PromptEnhancer",
        "XYUE_H3_LoRASelector",
        "TESpeedMiniMaxH3",
        "XYUE_H3_ModeModelSelector",
    }:
        return sorted(nodes, key=lambda node: float(node.get("pos", [0, 0])[1]))
    if node_type == "XYUE_H3_StageGenerationProfile":
        return sorted(nodes, key=lambda node: int(str(node.get("title", "阶段0")).split("阶段", 1)[1].split("｜", 1)[0]))
    if node_type == "XYUE_H3_StageResume":
        markers = ("第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段", "第六阶段", "第七阶段", "第八阶段", "第九阶段", "第十阶段")
        def stage_number(node):
            title = str(node.get("title", ""))
            for value, marker in enumerate(markers, start=1):
                if marker in title:
                    return value
            for value in range(MAX_STAGES, 0, -1):
                if f"阶段{value}" in title or f"阶段 {value}" in title:
                    return value
            return 99
        return sorted(nodes, key=stage_number)
    return nodes


def _ensure_stage_control_links(workflow: dict) -> None:
    """Migrate stage graphs to the optional-stage control contract."""
    controller = next((node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_StudioController"), None)
    resumes = _stage_nodes(workflow, "XYUE_H3_StageResume")
    concat = next((node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_VideoConcat"), None)
    if controller is None or not resumes or concat is None:
        return

    values = list(controller.get("widgets_values") or [])
    values.extend([None] * (17 - len(values)))
    values[16] = values[16] if values[16] is not None else 3
    controller["widgets_values"] = values
    links = workflow.setdefault("links", [])
    next_link = max((int(link[0]) for link in links), default=0) + 1

    def add_link(source, source_slot, target, target_name, target_type):
        nonlocal next_link
        inputs = target.setdefault("inputs", [])
        existing = next((item for item in inputs if item.get("name") == target_name), None)
        if existing is not None and existing.get("link") is not None:
            return
        slot = inputs.index(existing) if existing is not None else len(inputs)
        link_id = next_link
        next_link += 1
        links.append([link_id, source["id"], source_slot, target["id"], slot, target_type])
        source.setdefault("outputs", [])[source_slot].setdefault("links", []).append(link_id)
        if existing is None:
            inputs.append({"name": target_name, "type": target_type, "link": link_id})
        else:
            existing["type"] = target_type
            existing["link"] = link_id

    for index, resume in enumerate(resumes):
        if index:
            add_link(resumes[index - 1], 0, resume, "fallback_video", "VIDEO")
        add_link(controller, 0, resume, "studio_control", "XYUE_H3_STUDIO_CONTROL")
    add_link(controller, 0, concat, "studio_control", "XYUE_H3_STUDIO_CONTROL")
    workflow["last_link_id"] = next_link - 1
    workflow.setdefault("extra", {}).setdefault("xyue_h3_multi_stage", {})["graph_version"] = 2


def _validate_duration(value: int) -> int:
    duration = int(value)
    if not 1 <= duration <= 15:
        raise ValueError(f"阶段时长必须在 1–15 秒之间，收到：{duration}")
    return duration


def lint_prompts(workflow: dict, prompts: list[str], durations: list[int]) -> list[str]:
    """Sanity-check prompts before execution without the runtime registry.

    H3 accepts natural language, so only enabled-material references are
    checked. Ref2VA picture tokens are bounded by the workflow's enabled image
    assets; keyframe labels (I2VA <Picture 1> etc.) are native input slots and
    allowed.
    """

    editors = _stage_nodes(workflow, "XYUE_H3_PromptEditor")
    entries: list[str] = []
    assets = inspect_materials(workflow)["entries"]
    image_filenames = [
        entry["file"] for entry in assets
        if entry["kind"] == "image" and entry["active"]
    ]
    registry = None
    if image_filenames:
        image_pack, _ = build_image_pack(
            {"filename": name, "enabled": True} for name in image_filenames
        )
        registry = image_pack
    for index, (prompt, duration) in enumerate(zip(prompts, durations)):
        mode_value = editors[index]["widgets_values"][0] if index < len(editors) else "多参考模式"
        mode_key = MODE_KEYS.get(str(mode_value or ""), "")
        if mode_key not in {"T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"}:
            entries.append(f"第{index + 1}段：未知生成模式 {mode_value}")
            continue
        for error in validate_prompt(str(prompt), mode_key, float(duration), registry):
            entries.append(f"第{index + 1}段：{error}")
    return entries


def dry_run_summary(workflow: dict, plan: dict) -> list[str]:
    """Describe planned changes for user confirmation before applying."""
    lines: list[str] = []
    lines.append(f"启用阶段数：前 {int(plan.get('stage_count', 3))} 段（模板最多 {MAX_STAGES} 段）")
    editors = _stage_nodes(workflow, "XYUE_H3_PromptEditor")
    prompts = list(plan.get("prompts") or [])
    durations = list(plan.get("durations") or [])
    for index, (prompt, duration) in enumerate(zip(prompts, durations), start=1):
        current = editors[index - 1]["widgets_values"][2] if index - 1 < len(editors) else ""
        changed = "（已变化）" if current.strip() != str(prompt).strip() else "（未变化）"
        lines.append(f"第{index}段提示词 {changed}")
        lines.append(f"  时长：{duration} 秒")
        if current.strip() != str(prompt).strip():
            lines.append(f"  旧提示词前 60 字：{str(current).strip()[:60]}…")
            lines.append(f"  新提示词前 60 字：{str(prompt).strip()[:60]}…")
    generation = dict(plan.get("generation") or {})
    stage_sampling = list(generation.get("stages") or [])
    if stage_sampling:
        lines.append("每段采样方式：")
        for index, stage in enumerate(stage_sampling[:10], start=1):
            sampling = dict(stage.get("sampling") or {})
            if not sampling:
                continue
            preset = sampling.get("sampling_preset") or "（未指定）"
            detailed = any(
                key in sampling
                for key in ("sampling_mode", "coarse_steps", "upscale_factor", "refine_pass", "extend_sigmas")
            )
            if detailed:
                lines.append(
                    f"  第{index}段：{preset}｜{sampling.get('sampling_mode') or ''}｜粗采样 {sampling.get('coarse_steps')} 步｜放大 {sampling.get('upscale_factor')}x｜精修 {sampling.get('refine_pass')}｜扩展 {sampling.get('extend_sigmas')} 步"
                )
            else:
                lines.append(f"  第{index}段：{preset}（预设档位）")
    global_sampling = dict((generation.get("global") or {}).get("sampling") or {})
    if global_sampling:
        preset = global_sampling.get("sampling_preset") or "（未指定）"
        detailed = any(
            key in global_sampling
            for key in ("sampling_mode", "coarse_steps", "upscale_factor", "refine_pass", "extend_sigmas")
        )
        if detailed:
            lines.append(
                f"全局采样：{preset}｜{global_sampling.get('sampling_mode') or ''}｜粗采样 {global_sampling.get('coarse_steps')} 步｜放大 {global_sampling.get('upscale_factor')}x｜精修 {global_sampling.get('refine_pass')}｜扩展 {global_sampling.get('extend_sigmas')} 步"
            )
        else:
            lines.append(f"全局采样：{preset}（预设档位）")
    model_warnings = validate_mode_plan(list(plan.get("models") or []), workflow, plan.get("generation"))
    if model_warnings:
        lines.append("模型模式警告：")
        lines.extend(f"  - {warning}" for warning in model_warnings)
    missing_models = validate_model_files(list(plan.get("models") or []))
    if missing_models:
        lines.append("模型文件缺失：")
        lines.extend(f"  - {entry}" for entry in missing_models)
    missing_loras = validate_lora_files(plan.get("acceleration"))
    if missing_loras:
        lines.append("LoRA 文件缺失：")
        lines.extend(f"  - {entry}" for entry in missing_loras)
    acceleration = dict(plan.get("acceleration") or {})
    stage_lora = list((acceleration.get("stages") or []))
    if stage_lora:
        lines.append("每段 LoRA 组合：")
        for index, stage in enumerate(stage_lora[:10], start=1):
            lora = dict(stage.get("lora") or {})
            te = dict(stage.get("te") or {})
            lines.append(
                f"  第{index}段：LoRA {lora.get('name') or '（未指定）'}｜强度 {lora.get('strength') or '（默认）'}｜TE {te.get('mode') or '（未指定）'}"
            )
    elif acceleration.get("lora"):
        lora = dict(acceleration["lora"])
        lines.append(f"全局 LoRA：{lora.get('name')}｜强度 {lora.get('strength') or '（默认）'}")
    else:
        lines.append("LoRA：不使用")
    start_stage = int(plan.get("start_stage", 1))
    resume_files = list(plan.get("resume_files") or [])
    if start_stage > 1:
        lines.append(f"续跑：从第 {start_stage} 段开始")
        for index in range(start_stage - 1):
            lines.append(f"  第{index + 1}段续接文件：{resume_files[index] if index < len(resume_files) else '(未提供)'}")
    return lines


def configure_unified_workflow(
    workflow: dict,
    prompt: str,
    duration: int,
    *,
    generation: dict | None = None,
    acceleration: dict | None = None,
    model: dict | None = None,
) -> dict:
    """Configure a single-stage XYUE H3 workflow (unified / one-shot)."""
    duration = _validate_duration(duration)
    editor = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_PromptEditor"),
        None,
    )
    if editor is None:
        raise ValueError("统一工作流必须包含一个 XYUE_H3_PromptEditor")
    editor["widgets_values"] = editor.get("widgets_values") or []
    values = list(editor["widgets_values"])
    values.extend([None] * (3 - len(values)))
    values[1] = float(duration)
    values[2] = str(prompt).strip()
    editor["widgets_values"] = values
    editor["title"] = f"{PROMPT_TITLE}｜{duration}秒"

    enhancer = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_PromptEnhancer"),
        None,
    )
    if enhancer is not None:
        enhancer_values = list(enhancer.get("widgets_values") or [])
        enhancer_values.extend([None] * (2 - len(enhancer_values)))
        enhancer_values[1] = float(duration)
        enhancer["widgets_values"] = enhancer_values

    profile = next(
        (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_GenerationProfile"),
        None,
    )
    if profile is not None:
        profile_values = list(profile.get("widgets_values") or [])[:10]
        profile_values.extend([None] * (10 - len(profile_values)))
        settings = dict((generation or {}).get("global") or {})
        for name, index in {
            "aspect": 0,
            "resolution": 1,
            "duration": 2,
            "steps": 3,
            "audio_steps": 4,
            "scheduler": 5,
            "seed": 6,
            "seed_control": 7,
            "reference_size": 8,
        }.items():
            if name in settings:
                profile_values[index] = settings[name]
        if "duration" not in settings:
            profile_values[2] = duration
        _set_sampling_widgets(profile_values, 9, dict(settings.get("sampling") or {}))
        profile["widgets_values"] = profile_values

    if model:
        selector = next(
            (node for node in workflow.get("nodes", []) if node.get("type") == "XYUE_H3_ModeModelSelector"),
            None,
        )
        if selector is None:
            raise ValueError("统一工作流必须包含一个 XYUE_H3_ModeModelSelector")
        selector_values = list(selector.get("widgets_values") or [])
        selector_values.extend([None] * (6 - len(selector_values)))
        for name, widget_index in MODEL_WIDGET_FIELDS.items():
            if name in model and model[name] is not None:
                selector_values[widget_index] = model[name]
        selector["widgets_values"] = selector_values
        missing_models = validate_model_files([model])
        if missing_models:
            raise ValueError("模型文件不存在：\n" + "\n".join(f"  - {item}" for item in missing_models))

    _set_acceleration(workflow, dict(acceleration or {}), require_global=False)
    missing_loras = validate_lora_files(acceleration)
    if missing_loras:
        raise ValueError("LoRA 文件不存在：\n" + "\n".join(f"  - {item}" for item in missing_loras))
    workflow.setdefault("extra", {})["xyue_h3_multi_stage"] = {
        "unified": True,
        "durations": [duration],
        "duration_reasons": [],
        "start_stage": 1,
        "queue_requested": False,
        "materials": inspect_materials(workflow),
        "generation_overrides": dict(generation or {}),
        "acceleration_overrides": dict(acceleration or {}),
        "material_overrides": [],
        "models": [model] if model else [],
    }
    return workflow


def configure_workflow(
    workflow: dict,
    prompts: list[str],
    durations: list[int],
    *,
    start_stage: int = 1,
    resume_files: list[str] | None = None,
    queue: bool = False,
    generation: dict | None = None,
    acceleration: dict | None = None,
    duration_reasons: list[str] | None = None,
    material_overrides: list[dict] | None = None,
    models: list[dict] | None = None,
    stage_count: int = 3,
) -> dict:
    if len(prompts) != len(durations) or not 1 <= len(prompts) <= MAX_STAGES:
        raise ValueError(f"必须提供 1-{MAX_STAGES} 段提示词和对应时长")
    if start_stage < 1 or start_stage > MAX_STAGES:
        raise ValueError(f"start_stage 只能是 1-{MAX_STAGES}")
    durations = [_validate_duration(value) for value in durations]
    stage_count = int(stage_count)
    if not 1 <= stage_count <= len(durations):
        raise ValueError(f"当前工作流阶段数必须在 1–{len(durations)} 之间")
    reasons = [str(reason).strip() for reason in (duration_reasons or [])]
    if reasons and len(reasons) != len(prompts):
        raise ValueError("duration_reasons 必须与提示词段数一致")

    editors = _stage_nodes(workflow, "XYUE_H3_PromptEditor")
    enhancers = _stage_nodes(workflow, "XYUE_H3_PromptEnhancer")
    profiles = _stage_nodes(workflow, "XYUE_H3_StageGenerationProfile")
    resumes = _stage_nodes(workflow, "XYUE_H3_StageResume")
    if len(editors) < len(prompts) or len(enhancers) < len(prompts) or len(profiles) < len(prompts) or len(resumes) < len(prompts):
        raise ValueError("目标工作流的阶段槽位少于计划段数")

    _set_material_overrides(workflow, list(material_overrides or []))

    studio = next(node for node in workflow["nodes"] if node.get("type") == "XYUE_H3_StudioController")
    studio["widgets_values"] = list(studio.get("widgets_values") or [])[:12]
    studio["widgets_values"][0] = False
    while len(studio["widgets_values"]) <= 11:
        studio["widgets_values"].append(None)
    studio["widgets_values"][11] = stage_count
    for index, (editor, enhancer, profile, duration, prompt) in enumerate(
        zip(editors, enhancers, profiles, durations, prompts), start=1
    ):
        editor["widgets_values"][1] = float(duration)
        editor["widgets_values"][2] = str(prompt).strip()
        enhancer["widgets_values"][1] = float(duration)
        profile["widgets_values"][2] = duration
        profile_values = list(profile.get("widgets_values") or [])[:11]
        profile_values.extend([None] * (11 - len(profile_values)))
        profile_values[10] = f"第{index}阶段"
        profile["widgets_values"] = profile_values
        editor["title"] = f"{PROMPT_TITLE}｜第{index}段｜{duration}秒"
        profile["title"] = f"{PROFILE_TITLE}{index}｜独立参数｜{duration}秒"

    _set_generation_controls(workflow, dict(generation or {}), profiles)
    _set_acceleration(workflow, dict(acceleration or {}))
    _set_models(workflow, list(models or []))
    _ensure_stage_control_links(workflow)

    missing_models = validate_model_files(list(models or []))
    if missing_models:
        raise ValueError("模型文件不存在：\n" + "\n".join(f"  - {item}" for item in missing_models))
    missing_loras = validate_lora_files(acceleration)
    if missing_loras:
        raise ValueError("LoRA 文件不存在：\n" + "\n".join(f"  - {item}" for item in missing_loras))
    mode_warnings = validate_mode_plan(list(models or []), workflow, generation)
    for warning in mode_warnings:
        print(f"警告：{warning}")

    files = list(resume_files or [])
    files.extend([""] * (len(resumes) - len(files)))
    for index, resume in enumerate(resumes, start=1):
        should_resume = index < start_stage
        resume["widgets_values"][0] = "跳过当前阶段，从保存视频续接" if should_resume else "运行当前阶段并保存"
        resume["widgets_values"][1] = files[index - 1] or "未选择阶段视频"
        resume["widgets_values"][3] = should_resume

    workflow.setdefault("extra", {})["xyue_h3_multi_stage"] = {
        "durations": durations,
        "duration_reasons": reasons,
        "start_stage": start_stage,
        "stage_count": stage_count,
        "graph_version": 2,
        "queue_requested": bool(queue),
        "materials": inspect_materials(workflow),
        "generation_overrides": dict(generation or {}),
        "acceleration_overrides": dict(acceleration or {}),
        "material_overrides": list(material_overrides or []),
        "models": list(models or []),
    }
    return workflow


def _read_last_config() -> dict:
    """Read the last used generation/models configuration from the project config."""
    config_file = PLUGIN_ROOT.parents[2] / ".h3-multi-stage.json"
    if not config_file.exists():
        return {}
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        return dict(data.get("last_config") or {})
    except (OSError, json.JSONDecodeError):
        return {}


def _write_last_config(plan: dict, configured: dict) -> None:
    """Persist the effective generation/models settings for future reuse."""
    config_file = PLUGIN_ROOT.parents[2] / ".h3-multi-stage.json"
    if not config_file.exists():
        return
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    previous = dict(data.get("last_config") or {})
    generation = dict(plan.get("generation") or {})
    if generation:
        previous["generation"] = generation
    models = list(plan.get("models") or [])
    if models:
        previous["models"] = models
    seeds = [int(stage.get("seed")) for stage in (generation.get("stages") or []) if isinstance(stage.get("seed"), int)]
    if seeds:
        previous["seeds"] = seeds
    data["last_config"] = previous
    try:
        config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def apply_last_config_defaults(plan: dict) -> dict:
    """Merge persisted last_config into a plan's missing fields."""
    saved = _read_last_config()
    if not saved:
        return plan
    result = dict(plan)
    saved_models = list(saved.get("models") or [])
    if not result.get("models") and saved_models:
        result["models"] = saved_models
    saved_generation = dict(saved.get("generation") or {})
    if not result.get("generation") and saved_generation:
        result["generation"] = saved_generation
    return result


def _load_plan(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    prompts = data.get("prompts")
    if prompts is None:
        stage_indices = [
            index for index in range(1, 11)
            if isinstance(data.get(f"stage{index}"), dict)
        ]
        count = max(stage_indices, default=3)
        prompts = [data.get(f"stage{index}", {}).get("prompt", "") for index in range(1, count + 1)]
    durations = data.get("durations")
    if durations is None:
        count = len(prompts) if prompts is not None else 3
        durations = [data.get(f"stage{index}", {}).get("duration", 5) for index in range(1, count + 1)]
    unified = bool(data.get("unified"))
    plan: dict = {
        "prompts": prompts,
        "durations": durations,
        "duration_reasons": list(data.get("duration_reasons") or []),
        "start_stage": int(data.get("start_stage", 1)),
        "resume_files": list(data.get("resume_files") or []),
        "queue": bool(data.get("queue", False)),
        "generation": dict(data.get("generation") or {}),
        "acceleration": dict(data.get("acceleration") or {}),
        "material_overrides": list(data.get("material_overrides") or []),
        "models": list(data.get("models") or []),
        "stage_count": int(data.get("stage_count", len(prompts) or 3)),
    }
    if unified:
        plan["unified"] = True
        plan["prompt"] = str(data.get("prompt") or "")
        plan["duration"] = int(data.get("duration", 5))
        plan["model"] = data.get("model") if isinstance(data.get("model"), dict) else None
        plan.pop("prompts", None)
        plan.pop("durations", None)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, help="多阶段计划 JSON")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW, help="输入工作流 JSON")
    parser.add_argument("--output", type=Path, help="输出工作流；默认写入 ComfyUI 用户工作流目录")
    parser.add_argument("--queue", action="store_true", help="显式请求排队；仍需提供 API 格式 prompt JSON")
    parser.add_argument("--api-prompt", type=Path, help="已导出的 ComfyUI API 格式 prompt JSON")
    parser.add_argument("--server", default="http://127.0.0.1:8188", help="ComfyUI 服务地址")
    parser.add_argument("--inspect", action="store_true", help="输出素材选择/启用状态、模型选择；可不提供计划")
    parser.add_argument("--live-canvas", action="store_true", help="读取浏览器当前打开的 XYUE H3 画布")
    parser.add_argument("--apply-live", action="store_true", help="将配置写入浏览器可自动应用的待应用补丁")
    parser.add_argument("--dry-run", action="store_true", help="只预览将要写入的变化，不写任何文件")
    parser.add_argument("--lint", action="store_true", help="校验各阶段提示词结构，不写任何文件")
    parser.add_argument("--wait-applied", action="store_true", help="应用后轮询画布，等待前端消费待应用补丁")
    parser.add_argument("--report-outputs", action="store_true", help="扫描输出目录，报告已保存的阶段视频与最终视频")
    parser.add_argument("--list-models", action="store_true", help="列出本地可用的扩散模型、语言模型、VAE 与 LoRA 文件")
    parser.add_argument("--no-last-config", action="store_true", help="不读取也不写回 .h3-multi-stage.json 的 last_config")
    args = parser.parse_args()

    if args.list_models:
        print(json.dumps(list_available_models(), ensure_ascii=False, indent=2))
        return 0

    workflow = fetch_live_canvas(args.server)["workflow"] if args.live_canvas else json.loads(args.workflow.read_text(encoding="utf-8-sig"))
    if args.inspect:
        report = inspect_materials(workflow)
        report["models"] = inspect_models(workflow)
        report["sampling"] = inspect_sampling(workflow)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.plan is None:
            return 0
    if args.report_outputs:
        print(json.dumps(report_outputs(workflow), ensure_ascii=False, indent=2))
        return 0
    if args.plan is None:
        raise ValueError("配置工作流时必须提供 --plan")
    plan = _load_plan(args.plan)
    plan["queue"] = bool(args.queue or plan["queue"])
    if not args.no_last_config:
        plan = apply_last_config_defaults(plan)
    plan = apply_seed_memory(plan, workflow)
    unified = bool(plan.get("unified"))

    if args.lint:
        if unified:
            print("提示：统一工作流提示词 lint 需生成模式信息；请用 --dry-run 预览")
            return 0
        for entry in lint_prompts(workflow, list(plan.get("prompts") or []), list(plan.get("durations") or [])):
            print(entry)
        return 0
    if args.dry_run:
        if unified:
            print(f"统一工作流：时长 {plan.get('duration')} 秒")
            if plan.get("model"):
                print(f"  生成模式：{plan['model'].get('mode')}")
            acceleration = dict(plan.get("acceleration") or {})
            lora = dict(acceleration.get("lora") or {})
            if lora.get("name"):
                print(f"  LoRA：{lora['name']}｜强度 {lora.get('strength') or '（默认）'}")
            else:
                print("  LoRA：不使用")
            return 0
        for line in dry_run_summary(workflow, plan):
            print(line)
        return 0

    if unified:
        configured = configure_unified_workflow(
            workflow,
            str(plan.get("prompt") or ""),
            int(plan.get("duration", 5)),
            generation=dict(plan.get("generation") or {}),
            acceleration=dict(plan.get("acceleration") or {}),
            model=dict(plan.get("model") or {}) if plan.get("model") else None,
        )
    else:
        start_stage = int(plan.get("start_stage", 1))
        resume_files = list(plan.get("resume_files") or [])
        if start_stage > 1 and len(resume_files) < start_stage - 1:
            plan["resume_files"] = auto_resume_files(workflow, start_stage)
        configured = configure_workflow(workflow, **plan)
        lint_issues = lint_prompts(configured, list(plan.get("prompts") or []), list(plan.get("durations") or []))
        if lint_issues:
            print("提示词校验问题：", file=sys.stderr)
            for entry in lint_issues:
                print(f"  {entry}", file=sys.stderr)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(configured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.output)
    elif not args.apply_live:
        output = USER_WORKFLOWS / "XYUE_H3_技能生成_多段短剧.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(configured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output)

    if args.apply_live:
        pending = PLUGIN_ROOT.parents[1] / "user" / "default" / "xyue_h3_studio" / "pending_apply.json"
        write_pending_apply(configured, pending, auto_queue=plan["queue"])
        print(pending)
        if not args.no_last_config:
            _write_last_config(plan, configured)
        if args.wait_applied:
            applied = wait_for_pending_applied(args.server, pending, configured)
            if applied:
                print("前端已应用配置")
            else:
                print("等待超时：前端可能未应用配置；请检查 ComfyUI 页面", file=sys.stderr)
                return 1
        if plan["queue"]:
            print("auto_queue 已写入待应用补丁；由前端扩展自动应用并排队")
            return 0

    if not plan["queue"]:
        return 0
    if args.api_prompt is None:
        raise ValueError("排队前必须提供由 ComfyUI 导出的 API 格式 prompt JSON；普通工作流 JSON 不能直接提交")
    from urllib.request import Request, urlopen

    api_document = json.loads(args.api_prompt.read_text(encoding="utf-8-sig"))
    configured_api = configure_api_prompt(api_document, configured)
    prompt_payload = configured_api.get("prompt") if isinstance(configured_api.get("prompt"), dict) else configured_api
    payload = json.dumps({"prompt": prompt_payload}).encode("utf-8")
    request = Request(args.server.rstrip("/") + "/prompt", data=payload, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        print(response.read().decode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
