"""Submit the current live canvas snapshot to ComfyUI as an API prompt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen


PLUGIN_ROOT = Path(__file__).parents[1]
LIVE_CANVAS = PLUGIN_ROOT.parents[1] / "user" / "default" / "xyue_h3_studio" / "live_canvas.json"


def load_live_workflow(path: Path = LIVE_CANVAS) -> dict:
    snapshot = json.loads(path.read_text(encoding="utf-8-sig"))
    workflow = snapshot.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("当前画布快照缺少可用 workflow")
    return workflow


def fetch_object_info(server: str) -> dict:
    with urlopen(server.rstrip("/") + "/object_info", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _input_spec(object_info: dict, node_type: str, name: str):
    node_spec = object_info.get(node_type) or {}
    inputs = node_spec.get("input") or {}
    for group in ("required", "optional"):
        item = (inputs.get(group) or {}).get(name)
        if item is not None:
            return item
    return None


def workflow_to_api_prompt(workflow: dict, object_info: dict) -> dict:
    """Convert a serialized frontend workflow to ComfyUI API-format prompt."""

    nodes = list(workflow.get("nodes") or [])
    links = {int(link[0]): link for link in workflow.get("links") or []}
    prompt: dict = {}
    for node in nodes:
        node_type = str(node.get("type") or "")
        node_id = str(node.get("id"))
        node_spec = object_info.get(node_type)
        if node_spec is None:
            if node_type == "Note":
                continue
            raise ValueError(f"节点类型未注册：{node_type}")
        order = (node_spec.get("input_order") or {})
        names = list(order.get("required") or []) + list(order.get("optional") or [])
        connected: dict[str, list] = {}
        for item in node.get("inputs") or []:
            link_id = item.get("link")
            if link_id is None:
                continue
            link = links.get(int(link_id))
            if link is None:
                continue
            connected[str(item.get("name"))] = [str(link[1]), link[2]]
        widget_values = list(node.get("widgets_values") or [])
        widget_index = 0
        inputs: dict = {}
        for name in names:
            if name in connected:
                inputs[name] = connected[name]
                continue
            spec = _input_spec(object_info, node_type, name)
            if spec is None or len(spec) != 2 or not isinstance(spec[1], dict):
                continue
            if widget_index < len(widget_values):
                inputs[name] = widget_values[widget_index]
            widget_index += 1
            if isinstance(spec[1], dict) and spec[1].get("control_after_generate"):
                widget_index += 1
        prompt[node_id] = {"class_type": node_type, "inputs": inputs}
    return prompt


def submit(server: str, prompt: dict, dry_run: bool = False) -> dict:
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    if dry_run:
        return {"dry_run": True, "nodes": len(prompt)}
    request = Request(
        server.rstrip("/") + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--snapshot", type=Path, default=LIVE_CANVAS)
    parser.add_argument("--dry-run", action="store_true", help="只生成 API prompt，不提交")
    parser.add_argument("--output", type=Path, help="可选：把 API prompt 保存到文件")
    args = parser.parse_args()

    workflow = load_live_workflow(args.snapshot)
    object_info = fetch_object_info(args.server)
    prompt = workflow_to_api_prompt(workflow, object_info)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(prompt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = submit(args.server, prompt, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
