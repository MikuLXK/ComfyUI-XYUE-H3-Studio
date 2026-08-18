import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const BOARD_TYPE = "XYUE_H3_VideoBoard";
const CHECKPOINT_TYPE = "XYUE_H3_StageCheckpointSave";
const STAGE_COUNT = 5;
const REFRESH_MS = 1200;

function stageIndex(node) {
  const explicit = Number(node?.properties?.xyue_stage_index || 0);
  if (explicit > 0) return explicit;
  const title = String(node?.title || "");
  const match = title.match(/(?:阶段|第)([1-5一二三四五])/);
  if (!match) return 0;
  return Number({ 一: 1, 二: 2, 三: 3, 四: 4, 五: 5 }[match[1]] || match[1]);
}

function resultUrl(result) {
  if (!result?.filename) return "";
  const params = new URLSearchParams({
    filename: String(result.filename),
    subfolder: String(result.subfolder || ""),
    type: String(result.type || "output"),
  });
  params.set("preview", "true");
  params.set("t", String(result.filename).length);
  return `/view?${params.toString()}`;
}

function outputResult(historyItem, nodeId, final = false) {
  const output = historyItem?.outputs?.[String(nodeId)];
  const images = Array.isArray(output?.images) ? output.images : [];
  return images.length ? (final ? images[images.length - 1] : images[0]) : null;
}

function latestHistoryItem(history, promptId, nodeIds) {
  if (promptId && history?.[promptId]) return history[promptId];
  const records = Object.values(history || {});
  return records.find((item) => nodeIds.some((id) => item?.outputs?.[String(id)])) || records[0] || null;
}

function createGallery(node) {
  if (typeof node.addDOMWidget !== "function" || node.__xyueVideoBoardGallery) return;

  const root = document.createElement("div");
  root.style.cssText = [
    "box-sizing:border-box",
    "width:100%",
    "min-height:420px",
    "padding:10px",
    "display:grid",
    "grid-template-columns:repeat(3,minmax(0,1fr))",
    "grid-template-rows:repeat(2,minmax(0,1fr))",
    "gap:10px",
    "background:#111820",
    "border:1px solid #354352",
    "border-radius:6px",
  ].join(";");

  const cells = Array.from({ length: STAGE_COUNT + 1 }, (_, index) => {
    const cell = document.createElement("div");
    cell.style.cssText = "min-width:0;min-height:0;display:flex;flex-direction:column;background:#1c2733;border:1px solid #3b4b5b;border-radius:4px;overflow:hidden";
    const label = document.createElement("div");
    label.textContent = index < STAGE_COUNT ? `阶段${index + 1}` : "最终合成";
    label.style.cssText = "flex:0 0 28px;padding:6px 8px;color:#d7e0ea;font:600 12px sans-serif;background:#263544";
    const body = document.createElement("div");
    body.textContent = "等待视频完成";
    body.style.cssText = "flex:1;min-height:0;display:grid;place-items:center;padding:6px;color:#8794a2;font:12px sans-serif;text-align:center";
    cell.append(label, body);
    root.append(cell);
    return { cell, body, url: "" };
  });

  const widget = node.addDOMWidget("xyue_h3_video_board", "xyue_h3_video_board", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 440,
  });
  widget.computeLayoutSize = () => ({ minHeight: 440, minWidth: 720 });

  let promptId = "";
  let stopped = false;
  let timer = null;

  const checkpointNodes = () => (app.graph?._nodes || [])
    .filter((item) => item.type === CHECKPOINT_TYPE)
    .sort((a, b) => stageIndex(a) - stageIndex(b));

  const renderCell = (slot, result) => {
    const url = resultUrl(result);
    if (!url || url === slot.url) return;
    slot.url = url;
    slot.body.replaceChildren();
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.style.cssText = "width:100%;height:100%;object-fit:contain;background:#090d12";
    slot.body.append(video);
  };

  const refresh = async () => {
    if (stopped || document.hidden) return;
    try {
      const response = await api.fetchApi("/history?max_items=20");
      if (!response.ok) return;
      const history = await response.json();
      const checkpoints = checkpointNodes();
      const ids = [...checkpoints.map((item) => item.id), node.id];
      const record = latestHistoryItem(history, promptId, ids);
      if (!record) return;

      checkpoints.forEach((checkpoint, index) => renderCell(cells[index], outputResult(record, checkpoint.id)));
      renderCell(cells[STAGE_COUNT], outputResult(record, node.id, true));
    } catch (error) {
      console.debug("[XYUE H3] 视频面板刷新失败", error);
    }
  };

  const onExecuting = (event) => {
    const nextPromptId = event?.detail?.prompt_id;
    if (nextPromptId) {
      promptId = String(nextPromptId);
      cells.forEach((slot) => {
        slot.url = "";
        slot.body.textContent = "等待视频完成";
      });
      void refresh();
    }
  };
  const onExecuted = (event) => {
    const detail = event?.detail || {};
    if (detail.prompt_id && promptId && String(detail.prompt_id) !== promptId) return;
    if (detail.prompt_id && !promptId) promptId = String(detail.prompt_id);
    const output = detail.output;
    if (!output) return;
    const checkpoint = checkpointNodes().find((item) => String(item.id) === String(detail.node));
    if (checkpoint) {
      const images = Array.isArray(output.images) ? output.images : [];
      renderCell(cells[Math.max(0, stageIndex(checkpoint) - 1)], images[0]);
    } else if (String(detail.node) === String(node.id)) {
      const images = Array.isArray(output.images) ? output.images : [];
      renderCell(cells[STAGE_COUNT], images[images.length - 1]);
    }
  };
  api.addEventListener("executing", onExecuting);
  api.addEventListener("executed", onExecuted);
  timer = window.setInterval(refresh, REFRESH_MS);
  node.__xyueVideoBoardGallery = { root, stop: () => {
    stopped = true;
    if (timer !== null) window.clearInterval(timer);
    api.removeEventListener("executing", onExecuting);
    api.removeEventListener("executed", onExecuted);
  } };
  node.onRemoved = ((previous) => function (...args) {
    node.__xyueVideoBoardGallery?.stop();
    return previous?.apply(this, args);
  })(node.onRemoved);
  void refresh();
}

app.registerExtension({
  name: "XYUE.H3.VideoBoard",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== BOARD_TYPE) return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      createGallery(this);
      return result;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = onConfigure?.apply(this, args);
      createGallery(this);
      return result;
    };
  },
});
