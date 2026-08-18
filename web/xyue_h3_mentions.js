import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const ASSET_TYPES = {
  XYUE_H3_ImageAsset: ["图片", "@图片", "<Picture"],
  XYUE_H3_VideoAsset: ["视频", "@视频", "<Video"],
  XYUE_H3_AudioAsset: ["音频", "@音频", "<Audio"],
};

function widget(node, name) {
  return (node.widgets || []).find((item) => item.name === name);
}

function filenameStem(value) {
  const name = String(value || "").replaceAll("\\", "/").split("/").pop() || "素材";
  return name.replace(/\.[^.]*$/, "").replace(/[^\w\u3400-\u9fff.-]+/gu, "_").replace(/^[_\.]+|[_\.]+$/g, "") || "素材";
}

function imagePreviewUrl(value) {
  const annotated = String(value || "");
  const match = annotated.match(/\s+\[(input|output|temp)\]$/i);
  const type = match?.[1]?.toLowerCase() || "input";
  const clean = annotated.replace(/\s+\[(input|output|temp)\]$/i, "").replaceAll("\\", "/");
  const parts = clean.split("/").filter(Boolean);
  const filename = parts.pop();
  if (!filename) return "";
  const params = new URLSearchParams({ filename, type, subfolder: parts.join("/") });
  return api.apiURL(`/view?${params.toString()}`);
}

function collectAssets() {
  const counts = { 图片: 0, 视频: 0, 音频: 0 };
  const used = new Set();
  const result = [];
  for (const node of app.graph?._nodes || []) {
    const spec = ASSET_TYPES[node.type];
    if (!spec || widget(node, "enabled")?.value === false) continue;
    const kind = spec[0];
    const index = ++counts[kind];
    const file = widget(node, kind === "图片" ? "image" : kind === "视频" ? "video" : "audio")?.value || "素材";
    const mode = widget(node, "alias_mode")?.value || "";
    let alias = mode.includes("N") ? `@${kind}${index}` : `@${filenameStem(file)}`;
    const base = alias;
    let suffix = 2;
    while (used.has(alias)) alias = `${base}_${suffix++}`;
    used.add(alias);
    const role = kind === "音频"
      ? [widget(node, "anchor_name")?.value, widget(node, "anchor_type")?.value].filter(Boolean).join("｜")
      : widget(node, "role")?.value || "";
    const preview = kind === "图片" ? (node.imgs?.[node.imageIndex || 0]?.src || imagePreviewUrl(file)) : "";
    result.push({ kind, alias, filename: String(file), token: `<${kind === "图片" ? "Picture" : kind === "视频" ? "Video" : "Audio"} ${index}>`, role, preview });
  }
  return result;
}

function collectKeyframePlaceholders(node) {
  const mode = String(widget(node, "mode")?.value || "");
  if (mode === "I2VA" || mode.includes("首帧生视频")) {
    return [{ kind: "关键帧", alias: "@上一段尾帧", filename: "运行时由上一阶段尾帧提供", token: "<Picture 1>", role: "原生首帧占位", preview: "" }];
  }
  if (mode === "FL2VA" || mode.includes("首尾帧生视频")) {
    return [
      { kind: "关键帧", alias: "@首帧", filename: "运行时由首帧输入提供", token: "<Picture 1>", role: "原生首帧占位", preview: "" },
      { kind: "关键帧", alias: "@尾帧", filename: "运行时由尾帧输入提供", token: "<Picture 2>", role: "原生尾帧占位", preview: "" },
    ];
  }
  if (mode === "L2VA" || mode.includes("尾帧续写")) {
    return [{ kind: "关键帧", alias: "@尾帧", filename: "运行时由尾帧输入提供", token: "<Picture 1>", role: "原生尾帧占位", preview: "" }];
  }
  return [];
}

function closeMenu(menu) {
  menu?.remove();
}

function placeBelowInput(menu, input) {
  const host = input.offsetParent || input.parentElement;
  if (!host) return document.body.append(menu);
  const hostStyle = getComputedStyle(host);
  if (hostStyle.position === "static") host.style.position = "relative";
  if (hostStyle.overflow !== "visible") host.style.overflow = "visible";
  const inputRect = input.getBoundingClientRect();
  menu.style.left = `${input.offsetLeft}px`;
  menu.style.top = `${input.offsetTop + input.offsetHeight + 4}px`;
  menu.style.width = `${Math.max(380, inputRect.width)}px`;
  host.append(menu);
}

function assetFileWidget(node) {
  const name = node.type === "XYUE_H3_ImageAsset" ? "image" : node.type === "XYUE_H3_VideoAsset" ? "video" : "audio";
  return widget(node, name);
}

function installAssetPicker(node) {
  if (node.__xyueAssetPickerAttached) return;
  const fileWidget = assetFileWidget(node);
  const input = fileWidget?.inputEl;
  if (!input) return;
  node.__xyueAssetPickerAttached = true;
  let menu = null;
  const kind = node.type === "XYUE_H3_ImageAsset" ? "图片" : node.type === "XYUE_H3_VideoAsset" ? "视频" : "音频";
  const values = () => {
    const candidates = fileWidget.options?.values || fileWidget.options?.options || [];
    return [...new Set(candidates.length ? candidates : [fileWidget.value])].filter(Boolean);
  };
  const close = () => { menu?.remove(); menu = null; };
  const show = () => {
    close();
    menu = document.createElement("div");
    menu.className = "xyue-h3-asset-menu";
    Object.assign(menu.style, {
      position: "absolute", zIndex: 10000, minWidth: "380px", maxWidth: "560px", maxHeight: "360px",
      overflowY: "auto", padding: "6px", background: "#24282d", border: "1px solid #555d66",
      borderRadius: "6px", boxShadow: "0 8px 24px #0008", boxSizing: "border-box",
    });
    values().forEach((value) => {
      const row = document.createElement("button");
      row.type = "button";
      Object.assign(row.style, { display: "flex", alignItems: "center", gap: "10px", width: "100%", border: 0, borderRadius: "6px", padding: "7px 8px", background: value === fileWidget.value ? "#3d444c" : "transparent", color: "#e2e5e8", textAlign: "left", cursor: "pointer" });
      const preview = document.createElement("div");
      Object.assign(preview.style, { width: "56px", height: "56px", flex: "0 0 56px", display: "grid", placeItems: "center", overflow: "hidden", borderRadius: "5px", background: "#17191c", color: "#8d949c", fontSize: "12px" });
      if (kind === "图片") {
        const image = document.createElement("img");
        image.src = imagePreviewUrl(value);
        image.alt = value;
        Object.assign(image.style, { width: "100%", height: "100%", objectFit: "cover", display: "block" });
        image.onerror = () => { image.remove(); preview.textContent = kind; };
        preview.append(image);
      } else preview.textContent = kind;
      const label = document.createElement("div");
      label.textContent = value;
      Object.assign(label.style, { minWidth: "0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });
      row.append(preview, label);
      row.onclick = () => {
        fileWidget.value = value;
        fileWidget.callback?.(value);
        node.setDirtyCanvas?.(true, true);
        close();
      };
      menu.append(row);
    });
    placeBelowInput(menu, input);
  };
  input.addEventListener("mousedown", (event) => { event.preventDefault(); event.stopPropagation(); show(); });
  document.addEventListener("mousedown", (event) => { if (menu && !menu.contains(event.target) && event.target !== input) close(); }, { passive: true });
}

function attachEditor(node) {
  if (node.__xyueMentionAttached) return;
  const input = widget(node, "draft")?.inputEl;
  if (!input) return;
  node.__xyueMentionAttached = true;
  input.wrap = "soft";
  Object.assign(input.style, { whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: "1.55" });
  let menu;
  let selected = 0;

  const show = (trigger) => {
    closeMenu(menu);
    const placeholders = collectKeyframePlaceholders(node);
    const mode = String(widget(node, "mode")?.value || "");
    const assets = placeholders.length
      ? placeholders
      : (mode === "Ref2VA" || mode.includes("多参考") ? collectAssets() : []);
    const query = input.value.slice(0, input.selectionStart).split(trigger).pop().toLowerCase();
    const rows = trigger === "<" ? assets.filter((item) => item.token.toLowerCase().includes(query)) : assets.filter((item) => `${item.alias} ${item.filename}`.toLowerCase().includes(query));
    if (!rows.length) return;
    menu = document.createElement("div");
    menu.className = "xyue-h3-mention-menu";
    Object.assign(menu.style, {
      position: "absolute",
      zIndex: 10000,
      background: "#24282d",
      border: "1px solid #555d66",
      borderRadius: "6px",
      padding: "6px",
      minWidth: "380px",
      maxWidth: "560px",
      maxHeight: "360px",
      overflowY: "auto",
      color: "#d7dadd",
      boxShadow: "0 8px 24px #0008",
      boxSizing: "border-box",
    });
    selected = 0;
    rows.forEach((item, index) => {
      const row = document.createElement("button");
      row.type = "button";
      row.dataset.index = String(index);
      Object.assign(row.style, { display: "flex", alignItems: "center", gap: "10px", width: "100%", border: 0, borderRadius: "6px", textAlign: "left", padding: "7px 8px", background: index === 0 ? "#3d444c" : "transparent", color: "inherit", cursor: "pointer" });
      const preview = document.createElement("div");
      Object.assign(preview.style, { width: "56px", height: "56px", flex: "0 0 56px", borderRadius: "5px", overflow: "hidden", background: "#17191c", display: "grid", placeItems: "center", color: "#8d949c", fontSize: "12px" });
      if (item.preview) {
        const image = document.createElement("img");
        image.src = item.preview;
        image.alt = item.filename;
        Object.assign(image.style, { width: "100%", height: "100%", objectFit: "cover", display: "block" });
        image.onerror = () => { preview.textContent = item.kind; image.remove(); };
        preview.append(image);
      } else preview.textContent = item.kind;
      const text = document.createElement("div");
      text.style.minWidth = "0";
      const primary = document.createElement("div");
      primary.textContent = `${item.alias}  →  ${item.token}`;
      Object.assign(primary.style, { fontWeight: "600", color: "#e2e5e8" });
      const secondary = document.createElement("div");
      secondary.textContent = [item.filename, item.role].filter(Boolean).join(" · ");
      Object.assign(secondary.style, { marginTop: "3px", color: "#9da4ab", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });
      text.append(primary, secondary);
      row.append(preview, text);
      row.onclick = () => insert(rows[index], trigger);
      menu.append(row);
    });
    placeBelowInput(menu, input);
  };

  const insert = (item, trigger) => {
    const end = input.selectionStart;
    const before = input.value.slice(0, end);
    const start = before.lastIndexOf(trigger);
    const replacement = trigger === "@" ? item.alias : item.token;
    input.value = `${input.value.slice(0, start)}${replacement}${input.value.slice(end)}`;
    input.selectionStart = input.selectionEnd = start + replacement.length;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    closeMenu(menu);
    input.focus();
  };

  input.addEventListener("input", () => {
    const prefix = input.value.slice(0, input.selectionStart);
    const at = Math.max(prefix.lastIndexOf("@"), prefix.lastIndexOf("<"));
    const char = prefix[at];
    if (char === "@" || char === "<") show(char);
  });
  input.addEventListener("keydown", (event) => {
    if (!menu) return;
    const rows = [...menu.querySelectorAll("button")];
    if (event.key === "Escape") { event.preventDefault(); closeMenu(menu); menu = null; }
    else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      selected = (selected + (event.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length;
      rows.forEach((row, i) => row.style.background = i === selected ? "#3d444c" : "transparent");
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      rows[selected]?.click();
    }
  });
  document.addEventListener("mousedown", (event) => { if (menu && !menu.contains(event.target) && event.target !== input) { closeMenu(menu); menu = null; } }, { passive: true });
}

app.registerExtension({
  name: "XYUE.H3.Mentions",
  nodeCreated(node) {
    if (node.type === "XYUE_H3_PromptEditor") setTimeout(() => attachEditor(node), 0);
    if (ASSET_TYPES[node.type]) setTimeout(() => installAssetPicker(node), 0);
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "XYUE_H3_PromptEditor") {
      const original = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () { original?.apply(this, arguments); setTimeout(() => attachEditor(this), 0); };
    }
    if (ASSET_TYPES[nodeData.name]) {
      const original = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () { original?.apply(this, arguments); setTimeout(() => installAssetPicker(this), 0); };
    }
  },
});
