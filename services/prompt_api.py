"""OpenAI Responses and Chat Completions compatible transport adapters."""

from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from ..core.h3_prompt import system_instruction
except ImportError:  # direct test import from the plugin root
    from core.h3_prompt import system_instruction
from .document_parser import extract_text


def _endpoint(profile: dict[str, Any]) -> str:
    path = profile.get("endpoint_path") or ("/v1/responses" if profile.get("protocol") == "responses" else "/v1/chat/completions")
    return f"{str(profile['base_url']).rstrip('/')}/{str(path).lstrip('/')}"


def _document_parts(documents: list[dict[str, Any]], budget: int) -> tuple[str, list[dict[str, Any]]]:
    if not documents:
        return "", []
    text_parts: list[str] = []
    files: list[dict[str, Any]] = []
    each = max(1, budget // len(documents))
    for item in documents:
        path = Path(str(item.get("path", "")))
        if not path.exists():
            continue
        try:
            extracted, report = extract_text(path, each)
        except Exception as exc:
            extracted, report = "", {"error": str(exc), "filename": path.name}
        text_parts.append(f"\n[Document: {path.name}]\n{extracted}")
        files.append({"path": str(path), "report": report})
    return "".join(text_parts), files


def _responses_content(prompt: str, mode: str, registry: dict[str, Any], document_text: str, files: list[dict[str, Any]], include_files: bool) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if include_files:
        for item in files:
            path = Path(item["path"])
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            content.append({"type": "input_file", "filename": path.name, "file_data": f"data:{mime};base64,{encoded}"})
    content.append({"type": "input_text", "text": _user_text(prompt, mode, registry, document_text)})
    return content


def _user_text(prompt: str, mode: str, registry: dict[str, Any], document_text: str) -> str:
    return (
        f"Generation mode: {mode}\n"
        f"Active material registry:\n{json.dumps(registry, ensure_ascii=False, indent=2)}\n"
        f"Reference document excerpts:\n{document_text or 'N/A'}\n\n"
        f"User draft:\n{prompt}"
    )


def _extract_response(payload: dict[str, Any], protocol: str) -> str:
    if protocol == "responses":
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"].strip()
        chunks = []
        for output in payload.get("output", []) or []:
            for content in output.get("content", []) or []:
                if isinstance(content.get("text"), str):
                    chunks.append(content["text"])
        return "\n".join(chunks).strip()
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    return str(content).strip()


def request_prompt(profile: dict[str, Any], prompt: str, mode: str, registry: dict[str, Any], documents: list[dict[str, Any]], document_budget: int = 80_000) -> tuple[str, dict[str, Any]]:
    protocol = str(profile.get("protocol") or "responses")
    document_text, files = _document_parts(documents, document_budget)
    body: dict[str, Any] = {"model": profile["model"], "temperature": profile.get("temperature", 0.2), "max_output_tokens": profile.get("max_output_tokens", 64000)}
    if protocol == "responses":
        body["input"] = [{"role": "developer", "content": [{"type": "input_text", "text": system_instruction(mode)}]}, {"role": "user", "content": _responses_content(prompt, mode, registry, document_text, files, True)}]
    elif protocol == "chat_completions":
        body["messages"] = [{"role": "system", "content": system_instruction(mode)}, {"role": "user", "content": _user_text(prompt, mode, registry, document_text)}]
    else:
        raise ValueError(f"不支持的 API 协议：{protocol}")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {profile.get('api_key', '')}", **(profile.get("headers") or {})}
    request = Request(_endpoint(profile), data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    retries = int(profile.get("retries", 2))
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            timeout = profile.get("timeout_seconds")
            with urlopen(request, timeout=None if timeout in (None, "", 0, "0") else int(timeout)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = _extract_response(payload, protocol)
            if not result:
                raise ValueError("API 返回了空提示词")
            return result, {"protocol": protocol, "documents": [item.get("report", {}) for item in files], "response": payload}
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"提示词 API 请求失败：{last_error}") from last_error
