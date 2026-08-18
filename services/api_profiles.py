"""Server-side storage for XYUE prompt-enhancement API profiles."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any


def _profile_dir() -> Path:
    root = Path(__file__).resolve().parents[3] / "user" / "default" / "xyue_h3_studio"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read(name: str, default: Any) -> Any:
    path = _profile_dir() / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(name: str, value: Any) -> None:
    path = _profile_dir() / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def list_profiles() -> list[dict[str, Any]]:
    profiles = _read("api_profiles.json", [])
    secrets_map = _read("api_secrets.json", {})
    return [{**profile, "has_key": bool(secrets_map.get(profile.get("id", "")))} for profile in profiles]


def get_profile(profile_id: str) -> dict[str, Any]:
    profile = next((item for item in list_profiles() if item.get("id") == profile_id), None)
    if profile is None:
        raise ValueError(f"API 配置不存在：{profile_id}")
    profile["api_key"] = _read("api_secrets.json", {}).get(profile_id, "")
    return profile


def save_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(payload.get("id") or secrets.token_hex(8))
    profiles = _read("api_profiles.json", [])
    secret_map = _read("api_secrets.json", {})
    old = next((item for item in profiles if item.get("id") == profile_id), {})
    record = {
        "id": profile_id,
        "name": str(payload.get("name") or profile_id),
        "base_url": str(payload.get("base_url") or "").strip().rstrip("/"),
        "protocol": str(payload.get("protocol") or "responses"),
        "endpoint_path": str(payload.get("endpoint_path") or "").strip(),
        "model": str(payload.get("model") or ""),
        "headers": payload.get("headers") if isinstance(payload.get("headers"), dict) else {},
        "temperature": float(payload.get("temperature", 0.2)),
        "max_output_tokens": int(payload.get("max_output_tokens") or 64000),
        "timeout_seconds": _timeout_value(payload.get("timeout_seconds")),
        "retries": int(payload.get("retries", 2)),
    }
    if not record["base_url"] or not record["model"]:
        raise ValueError("API 配置必须填写 Base URL 和模型名")
    api_key = str(payload.get("api_key") or "")
    if api_key:
        secret_map[profile_id] = api_key
    elif old.get("id") != profile_id:
        secret_map.pop(profile_id, None)
    profiles = [item for item in profiles if item.get("id") != profile_id]
    profiles.append(record)
    _write("api_profiles.json", profiles)
    _write("api_secrets.json", secret_map)
    return {**record, "has_key": bool(secret_map.get(profile_id))}


def _timeout_value(value: Any) -> int | None:
    """Use None for an explicitly unlimited request timeout."""
    if value in (None, "", 0, "0"):
        return None
    timeout = int(value)
    if timeout < 0:
        raise ValueError("超时必须为正数，或留空表示无超时")
    return timeout


def delete_profile(profile_id: str) -> None:
    profiles = [item for item in _read("api_profiles.json", []) if item.get("id") != profile_id]
    secret_map = _read("api_secrets.json", {})
    secret_map.pop(profile_id, None)
    _write("api_profiles.json", profiles)
    _write("api_secrets.json", secret_map)
