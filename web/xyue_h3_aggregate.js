import { app } from "../../../scripts/app.js";

const NODE_TYPE = "XYUE_H3_AggregateWorkflow";
// Bump this when the embedded Studio bundle changes so an old iframe cannot hide new controls.
const STUDIO_URL = "/xyue-h3/studio/?v=B4Zo_uyt";
const FRAME_HEIGHT = 860;
const NODE_WIDTH = 1500;
const MATERIAL_LIMITS = { image: 9, video: 3, audio: 3 };
const DEFAULT_CONFIG = {
  schema: "xyue-h3/studio-config-v3",
  stage_count: 1,
  stage_titles: ["云海问剑"],
  prompts: ["integrated_multimodal_description: [Shot 1] ...\n\noverall_soundscape: ...\n\nnon_diegetic_music: ..."],
  durations: [5],
  transitions: ["cut"],
  models: [{
    mode: "文生视频模式",
    base_model: "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    reference_model: "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors",
    language_model: "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    video_vae: "minimax_h3_video_vae_fp16.safetensors",
    audio_vae: "minimax_h3_audio_vae_fp32.safetensors",
    latent_upscale_model: "minimax_h3_latent_upscaler_3d_fp16.safetensors",
    tiny_vae: "none",
    lora_enabled: true,
    lora_name: "minimax_h3\\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
    lora_strength: 1,
    attention_mode: "MiniMax H3 Kitchen Attention",
  }],
  generation: { global_enabled: false, stages: [{
    aspect: "16:9",
    resolution: "0.4MP|480p（864×480）",
    duration: 5,
    video_steps: 4,
    audio_steps: 4,
    scheduler: "简单稳定（推荐）",
    seed: 0,
    seed_control: "randomize",
    reference_size: "适配生成画布（省显存）",
    sampling: { upscale_factor: 1.5, sigma_steps: 3, denoise: 0.3 },
  }] },
};

function ensureAdvancedConfig(config) {
  const stages = Array.isArray(config?.generation?.stages) ? config.generation.stages : [];
  return {
    ...config,
    generation: {
      ...(config?.generation || {}),
      stages: stages.map((stage) => {
        const { first_sampling: _first, second_sampling: _second, steps: _steps, ...clean } = stage || {};
        const sampling = stage?.sampling || {};
        return {
          ...clean,
          video_steps: Number(stage?.video_steps ?? stage?.steps ?? 4),
          audio_steps: Number(stage?.audio_steps ?? 4),
          sampling: {
            upscale_factor: Number(sampling.upscale_factor ?? 1.5),
            sigma_steps: Number(sampling.sigma_steps ?? 3),
            denoise: Number(sampling.denoise ?? 0.3),
          },
        };
      }),
    },
    composition: { ...(config?.composition || {}) },
  };
}

function hideWidget(widget) {
  if (!widget || widget.__xyueAggregateHidden) return;
  widget.__xyueAggregateHidden = true;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.computedHeight = 0;
}

function readConfig(widget) {
  try {
    const parsed = JSON.parse(String(widget?.value || ""));
    if (parsed && typeof parsed === "object") return parsed;
  } catch {
    // A malformed saved value is replaced when Studio emits its first valid config.
  }
  return DEFAULT_CONFIG;
}

function writeConfig(node, widget, config) {
  if (!widget || !config || typeof config !== "object") return;
  const value = JSON.stringify(config);
  if (widget.value === value) return;
  widget.value = value;
  widget.callback?.(value);
  node.graph?.setDirtyCanvas?.(true, true);
}

function widgetValue(node, name) {
  return (node.widgets || []).find((item) => item.name === name)?.value;
}

function materialSelection(node) {
  node.properties ||= {};
  node.properties.xyue_material_selection ||= {};
  return node.properties.xyue_material_selection;
}

function canvasMaterialOverrides(node) {
  const graph = app.graph;
  const nodes = graph?._nodes || [];
  const links = graph?.links || {};
  const managers = new Map();
  for (const node of nodes) {
    const kind = node.type === "XYUE_H3_ImageManager" ? "image"
      : node.type === "XYUE_H3_VideoManager" ? "video"
      : node.type === "XYUE_H3_AudioManager" ? "audio" : "";
    if (kind) managers.set(kind, node);
  }
  const specs = [
    ["XYUE_H3_ImageAsset", "image", "未选择图片"],
    ["XYUE_H3_VideoAsset", "video", "未选择视频"],
    ["XYUE_H3_AudioAsset", "audio", "未选择音频"],
  ];
  const overrides = [];
  const assets = [];
  for (const [type, kind, empty] of specs) {
    const candidates = nodes.filter((node) => node.type === type);
    const manager = managers.get(kind);
    const slotByNode = new Map();
    for (const input of manager?.inputs || []) {
      const match = String(input.name || "").match(new RegExp(`^${kind}_(\\d+)$`));
      const link = input.link == null ? null : links[input.link];
      if (match && link) slotByNode.set(String(link.origin_id ?? link.originId), Number(match[1]));
    }
    candidates.forEach((node, index) => {
      const file = String(widgetValue(node, kind) || empty);
      const selected = file && file !== empty && file.toUpperCase() !== "UNKNOWN";
      const slot = slotByNode.get(String(node.id)) || index + 1;
      const enabled = widgetValue(node, "enabled") !== false;
      const aliasMode = String(widgetValue(node, "alias_mode") || `@${kind === "image" ? "图片" : kind === "video" ? "视频" : "音频"}N`);
      const prefix = kind === "image" ? "图片" : kind === "video" ? "视频" : "音频";
      const alias = aliasMode.includes("N") ? `@${prefix}${slot}` : `@${file.replace(/\\.[^.]+$/, "")}`;
      const token = `<${kind === "image" ? "Picture" : kind === "video" ? "Video" : "Audio"} ${slot}>`;
      assets.push({ kind, slot, file, alias, token, enabled, imported: selected });
      if (!selected && !enabled) return;
      const override = {
        kind,
        slot,
        file,
        enabled,
        alias_mode: aliasMode,
        role: String(widgetValue(node, kind === "audio" ? "anchor_type" : "role") || ""),
      };
      if (kind === "image") override.fit_mode = String(widgetValue(node, "fit_mode") || "保持原图");
      if (kind === "video") {
        override.start_seconds = Number(widgetValue(node, "start_time") || 0);
        override.duration_seconds = Number(widgetValue(node, "duration") || 0);
        override.include_audio = Boolean(widgetValue(node, "include_audio"));
      }
      if (kind === "audio") {
        override.voice_anchor = String(widgetValue(node, "anchor_name") || "");
        override.start_seconds = Number(widgetValue(node, "start_time") || 0);
        override.duration_seconds = Number(widgetValue(node, "duration") || 0);
        override.gain_db = Number(widgetValue(node, "gain_db") || 0);
        override.normalize_peak = Boolean(widgetValue(node, "normalize"));
      }
      overrides.push(override);
    });
  }
  const selected = materialSelection(node);
  const library = node.__xyueComfyMaterials || [];
  for (const kind of ["image", "video", "audio"]) {
    const existingFiles = new Set(assets.filter((item) => item.kind === kind && item.imported).map((item) => item.file.toLowerCase()));
    const usedSlots = new Set(assets.filter((item) => item.kind === kind && item.imported).map((item) => item.slot));
    const freeSlots = Array.from({ length: MATERIAL_LIMITS[kind] }, (_, index) => index + 1).filter((slot) => !usedSlots.has(slot));
    let cursor = 0;
    for (const source of library.filter((item) => item.kind === kind)) {
      if (existingFiles.has(String(source.file).toLowerCase())) continue;
      const key = `${kind}:${source.file}`;
      const enabled = Boolean(selected[key]) && cursor < freeSlots.length;
      const slot = enabled ? freeSlots[cursor++] : 0;
      const prefix = kind === "image" ? "图片" : kind === "video" ? "视频" : "音频";
      const asset = {
        kind,
        slot,
        file: String(source.file),
        alias: `@${prefix}${slot || ""}`,
        token: `<${kind === "image" ? "Picture" : kind === "video" ? "Video" : "Audio"} ${slot || "-"}>`,
        enabled,
        imported: true,
        source: "library",
      };
      assets.push(asset);
      if (!enabled) continue;
      const role = kind === "image" ? "未指定" : kind === "video" ? "动作节奏样片" : "角色声纹锚点";
      const override = { kind, slot, file: asset.file, enabled: true, alias_mode: `@${prefix}N`, role };
      if (kind === "image") override.fit_mode = "保持原图";
      if (kind === "video") Object.assign(override, { start_seconds: 0, duration_seconds: 0, include_audio: false });
      if (kind === "audio") Object.assign(override, { voice_anchor: `声音${slot}`, start_seconds: 0, duration_seconds: 0, gain_db: 0, normalize_peak: false });
      overrides.push(override);
    }
  }
  for (const kind of ["image", "video", "audio"]) {
    const active = assets.filter((item) => item.kind === kind && item.imported && item.enabled).sort((left, right) => left.slot - right.slot);
    active.forEach((item, index) => {
      const executionIndex = index + 1;
      const prefix = kind === "image" ? "图片" : kind === "video" ? "视频" : "音频";
      const label = kind === "image" ? "Picture" : kind === "video" ? "Video" : "Audio";
      item.alias = `@${prefix}${executionIndex}`;
      item.token = `<${label} ${executionIndex}>`;
    });
  }
  return { assets, material_overrides: overrides };
}

function promptValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function addReference(input, reference) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? start;
  promptValue(input, `${input.value.slice(0, start)}${reference}${input.value.slice(end)}`);
  input.focus();
  input.selectionStart = input.selectionEnd = start + reference.length;
}

function materialPreviewUrl(item) {
  if (item.kind !== "image") return "";
  const annotated = String(item.file || "");
  const match = annotated.match(/\s+\[(input|output|temp)\]$/i);
  const type = match?.[1]?.toLowerCase() || "input";
  const clean = annotated.replace(/\s+\[(input|output|temp)\]$/i, "").replaceAll("\\", "/");
  const parts = clean.split("/").filter(Boolean);
  const filename = parts.pop();
  if (!filename) return "";
  return `/view?${new URLSearchParams({ filename, type, subfolder: parts.join("/") })}`;
}

function referenceColor(kind) {
  return kind === "image" ? "#2f6feb" : kind === "video" ? "#a244cf" : "#b46600";
}

function renderPromptHighlight(document, input, materials) {
  const host = input.parentElement;
  if (!host) return;
  const signature = `${input.value}\u0000${materials.map((item) => `${item.kind}:${item.alias}:${item.token}`).join("\u001f")}`;
  if (input.__xyueHighlightSignature === signature) {
    input.__xyueRefreshHighlight?.();
    return;
  }
  input.__xyueHighlightSignature = signature;
  input.__xyueReferenceMaterials = materials;
  host.style.position = "relative";
  let mirror = host.querySelector(".xyue-prompt-highlight");
    if (!mirror) {
    mirror = document.createElement("div");
    mirror.className = "xyue-prompt-highlight";
    mirror.setAttribute("aria-hidden", "true");
    host.insertBefore(mirror, input);
    input.style.position = "relative";
    input.style.zIndex = "1";
    input.style.background = "transparent";
    input.style.color = "transparent";
    input.style.caretColor = "#1f2428";
    input.addEventListener("scroll", () => {
      mirror.scrollTop = input.scrollTop;
      mirror.scrollLeft = input.scrollLeft;
    });
    input.addEventListener("input", () => {
      renderPromptHighlight(document, input, input.__xyueReferenceMaterials || []);
    });
  }
  const style = getComputedStyle(input);
  const syncGeometry = () => {
    const hostRect = host.getBoundingClientRect();
    const inputRect = input.getBoundingClientRect();
    Object.assign(mirror.style, {
      left: `${inputRect.left - hostRect.left}px`,
      top: `${inputRect.top - hostRect.top}px`,
      width: `${inputRect.width}px`,
      height: `${inputRect.height}px`,
    });
  };
  input.__xyueRefreshHighlight = syncGeometry;
  Object.assign(mirror.style, {
    position: "absolute",
    zIndex: "0",
    pointerEvents: "none",
    boxSizing: "border-box",
    left: "0px",
    top: "0px",
    width: "0px",
    height: "0px",
    padding: style.padding,
    border: "1px solid transparent",
    borderRadius: style.borderRadius,
    overflow: "hidden",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    font: style.font,
    lineHeight: style.lineHeight,
    letterSpacing: "0",
    wordSpacing: style.wordSpacing,
    textAlign: style.textAlign,
    textIndent: style.textIndent,
    tabSize: style.tabSize,
    color: "#252a2f",
    background: style.backgroundColor === "rgba(0, 0, 0, 0)" ? "#fff" : style.backgroundColor,
  });
  mirror.replaceChildren();
  const aliases = new Map(materials.flatMap((item) => [[item.alias, item.kind], [item.token, item.kind]]));
  const pattern = /(@[\w\u3400-\u9fff.\-]+|<\s*(?:Picture|Video|Audio)\s+\d+\s*>)/giu;
  let cursor = 0;
  for (const match of input.value.matchAll(pattern)) {
    mirror.append(document.createTextNode(input.value.slice(cursor, match.index)));
    const value = match[0];
    const canonical = value.startsWith("<")
      ? value.replace(/<\s*(picture|video|audio)\s+(\d+)\s*>/i, (_, kind, index) => `<${kind[0].toUpperCase()}${kind.slice(1).toLowerCase()} ${index}>`)
      : value;
    const kind = aliases.get(canonical) || (canonical.startsWith("<Picture") ? "image" : canonical.startsWith("<Video") ? "video" : canonical.startsWith("<Audio") ? "audio" : "");
    const span = document.createElement("span");
    span.textContent = value;
    span.style.cssText = kind
      ? `color:${referenceColor(kind)};font-weight:700;background:${referenceColor(kind)}18;border-radius:3px`
      : "color:#c33;font-weight:700;text-decoration:underline wavy #c33";
    mirror.append(span);
    cursor = match.index + value.length;
  }
  mirror.append(document.createTextNode(input.value.slice(cursor)));
  syncGeometry();
  mirror.scrollTop = input.scrollTop;
  mirror.scrollLeft = input.scrollLeft;
  if (!input.__xyueHighlightObserver) {
    const observer = new ResizeObserver(() => input.__xyueRefreshHighlight?.());
    observer.observe(input);
    observer.observe(host);
    input.__xyueHighlightObserver = observer;
    document.defaultView?.addEventListener("resize", input.__xyueRefreshHighlight);
  }
}

function renderCanvasAssetDock(document, materials, onToggle) {
  const list = document.querySelector(".asset-list");
  if (!list) return;
  const signature = materials.map((item) => `${item.kind}:${item.slot}:${item.file}:${item.alias}:${item.token}:${item.enabled}`).join("\u001f");
  if (list.__xyueAssetSignature === signature) return;
  list.__xyueAssetSignature = signature;
  list.querySelectorAll(".xyue-canvas-asset").forEach((node) => node.remove());
  list.querySelectorAll(".asset-row:not(.xyue-canvas-asset)").forEach((node) => { node.style.display = "none"; });
  const empty = list.querySelector(".asset-empty");
  if (empty) empty.style.display = materials.length ? "none" : "";
  materials.forEach((item) => {
    const row = document.createElement("div");
    row.className = "asset-row xyue-canvas-asset";
    row.style.opacity = item.enabled ? "1" : ".62";
    const button = document.createElement("div");
    button.className = "asset-select";
    const preview = document.createElement("span");
    preview.className = `asset-preview asset-${item.kind}`;
    const url = materialPreviewUrl(item);
    if (url) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      preview.append(image);
    } else {
      preview.textContent = item.kind === "image" ? "P" : item.kind === "video" ? "V" : "A";
      preview.style.color = referenceColor(item.kind);
      preview.style.fontWeight = "800";
    }
    const copy = document.createElement("span");
    copy.className = "asset-copy";
    const name = document.createElement("strong");
    name.textContent = item.file;
    const meta = document.createElement("small");
    meta.textContent = "来自当前 ComfyUI 画布";
    const alias = document.createElement("em");
    alias.textContent = `${item.alias}  ${item.token}`;
    alias.style.color = referenceColor(item.kind);
    copy.append(name, meta, alias);
    button.append(preview, copy);
    const stateButton = document.createElement("button");
    stateButton.type = "button";
    stateButton.className = `asset-state ${item.enabled ? "is-on" : ""}`;
    stateButton.title = item.enabled ? "停用素材" : "启用素材";
    stateButton.onclick = () => onToggle(item);
    row.append(button, stateButton);
    list.append(row);
  });
  const addButton = document.querySelector("button.add-asset");
  if (addButton) {
    addButton.disabled = true;
    addButton.title = "请在 ComfyUI 画布的 XYUE 素材节点中导入文件";
    addButton.textContent = "素材由当前 ComfyUI 画布同步";
  }
}

function installMentionPicker(document, input, getMaterials) {
  if (input.__xyueMentionPicker) return;
  input.__xyueMentionPicker = true;
  let menu;
  let selected = 0;

  const close = () => {
    menu?.remove();
    menu = undefined;
    input.__xyueMentionPickerRefresh = undefined;
  };
  const referenceAtCursor = () => {
    const cursor = input.selectionStart ?? 0;
    const prefix = input.value.slice(0, cursor);
    const start = Math.max(prefix.lastIndexOf("@"), prefix.lastIndexOf("<"));
    if (start < 0) return null;
    const trigger = prefix[start];
    const query = prefix.slice(start + 1);
    if (/\n/.test(query) || (trigger === "@" && /\s/.test(query)) || (trigger === "<" && />/.test(query))) return null;
    return { cursor, start, trigger, query: query.toLowerCase() };
  };
  const choose = (item, reference) => {
    const match = referenceAtCursor();
    if (!match) return;
    promptValue(input, `${input.value.slice(0, match.start)}${reference}${input.value.slice(match.cursor)}`);
    input.selectionStart = input.selectionEnd = match.start + reference.length;
    input.focus();
    close();
  };
  const show = () => {
    const match = referenceAtCursor();
    if (!match) {
      close();
      return;
    }
    const materials = getMaterials().assets.filter((item) => item.imported && item.enabled);
    const rows = materials.filter((item) => {
      const value = match.trigger === "@" ? `${item.alias} ${item.file}` : `${item.token} ${item.file}`;
      return value.toLowerCase().includes(match.query);
    });
    if (!rows.length) {
      close();
      return;
    }
    close();
    selected = 0;
    menu = document.createElement("div");
    menu.className = "xyue-mention-picker";
    const rect = input.getBoundingClientRect();
    Object.assign(menu.style, {
      position: "fixed",
      zIndex: "20000",
      left: `${rect.left}px`,
      top: `${rect.bottom + 4}px`,
      width: `${rect.width}px`,
      maxHeight: "300px",
      overflowY: "auto",
      padding: "5px",
      border: "1px solid #aeb6bd",
      borderRadius: "5px",
      background: "#fff",
      boxShadow: "0 10px 24px #1f242833",
      boxSizing: "border-box",
    });
    const reposition = () => {
      if (!menu) return;
      const current = input.getBoundingClientRect();
      menu.style.left = `${Math.max(4, current.left)}px`;
      menu.style.top = `${Math.min(document.documentElement.clientHeight - 8, current.bottom + 4)}px`;
      menu.style.width = `${current.width}px`;
    };
    menu.__xyueReposition = reposition;
    reposition();
    rows.forEach((item, index) => {
      const reference = match.trigger === "@" ? item.alias : item.token;
      const row = document.createElement("button");
      row.type = "button";
      row.dataset.index = String(index);
      Object.assign(row.style, {
        display: "grid",
        gridTemplateColumns: "52px minmax(0, 1fr)",
        alignItems: "center",
        gap: "10px",
        width: "100%",
        minHeight: "58px",
        padding: "4px 7px",
        border: "0",
        borderRadius: "4px",
        background: index === 0 ? "#e9f1fb" : "transparent",
        color: "#252a2f",
        cursor: "pointer",
        textAlign: "left",
      });
      const preview = document.createElement("span");
      Object.assign(preview.style, {
        width: "52px",
        height: "52px",
        display: "grid",
        placeItems: "center",
        overflow: "hidden",
        borderRadius: "4px",
        background: "#eef1f3",
        color: referenceColor(item.kind),
        fontWeight: "800",
      });
      const url = materialPreviewUrl(item);
      if (url) {
        const image = document.createElement("img");
        image.src = url;
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        Object.assign(image.style, { width: "100%", height: "100%", objectFit: "cover" });
        preview.append(image);
      } else {
        preview.textContent = item.kind === "image" ? "P" : item.kind === "video" ? "V" : "A";
      }
      const copy = document.createElement("span");
      copy.style.minWidth = "0";
      const name = document.createElement("strong");
      name.textContent = reference;
      Object.assign(name.style, { display: "block", color: referenceColor(item.kind), fontSize: "12px" });
      const filename = document.createElement("small");
      filename.textContent = item.file;
      Object.assign(filename.style, { display: "block", marginTop: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#697078" });
      copy.append(name, filename);
      row.append(preview, copy);
      row.onmousedown = (event) => event.preventDefault();
      row.onclick = () => choose(item, reference);
      menu.append(row);
    });
    document.documentElement.append(menu);
    input.__xyueMentionPickerRefresh = reposition;
  };

  input.addEventListener("input", show);
  input.addEventListener("click", show);
  input.addEventListener("focus", show);
  document.defaultView?.addEventListener("resize", () => menu?.__xyueReposition?.());
  document.defaultView?.addEventListener("scroll", () => menu?.__xyueReposition?.(), { passive: true });
  input.addEventListener("keydown", (event) => {
    if (!menu) return;
    const rows = [...menu.querySelectorAll("button")];
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      selected = (selected + (event.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length;
      rows.forEach((row, index) => { row.style.background = index === selected ? "#e9f1fb" : "transparent"; });
      rows[selected]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      rows[selected]?.click();
    }
  });
  document.addEventListener("mousedown", (event) => {
    if (menu && event.target !== input && !menu.contains(event.target)) close();
  }, { passive: true });
}

function mountIframeReferenceTools(frame, getMaterials, onToggle) {
  let timer;
  let observer;
  const install = () => {
    const document = frame.contentDocument;
    if (!document?.body) return;
    const input = document.querySelector("textarea.prompt-editor");
    if (!input) return;
    const allMaterials = getMaterials().assets.filter((item) => item.imported);
    const materials = allMaterials.filter((item) => item.enabled);
    renderCanvasAssetDock(document, allMaterials, onToggle);
    renderPromptHighlight(document, input, materials);
    installMentionPicker(document, input, getMaterials);
    if (!observer) {
      observer = new ResizeObserver(() => {
        renderPromptHighlight(document, input, input.__xyueReferenceMaterials || materials);
        input.__xyueMentionPickerRefresh?.();
      });
      observer.observe(input);
      observer.observe(document.body);
    }
  };
  timer = window.setInterval(install, 800);
  install();
  return () => { window.clearInterval(timer); observer?.disconnect(); };
}

function mountStudio(node) {
  const configWidget = node.widgets?.find((widget) => widget.name === "config_text");
  hideWidget(configWidget);

  if (node.__xyueAggregateStudio) {
    node.__xyueAggregateStudio.sendConfig();
    return;
  }
  if (typeof node.addDOMWidget !== "function") return;

  const root = document.createElement("div");
  root.style.cssText = [
    "box-sizing:border-box",
    "width:100%",
    `height:${FRAME_HEIGHT}px`,
    "overflow:hidden",
    "border:1px solid #c7cdd1",
    "border-radius:7px",
    "background:#e9edf0",
  ].join(";");

  const frame = document.createElement("iframe");
  frame.src = STUDIO_URL;
  frame.title = "XYUE H3 Studio";
  frame.allow = "fullscreen";
  frame.style.cssText = "display:block;width:100%;height:100%;border:0;background:#e9edf0";
  root.append(frame);

  let advancedState = ensureAdvancedConfig(readConfig(configWidget));
  const mergeAdvanced = (config) => {
    const incoming = ensureAdvancedConfig(config);
    const currentStages = advancedState.generation?.stages || [];
    const incomingStages = incoming.generation?.stages || [];
    advancedState = ensureAdvancedConfig({
      ...incoming,
      generation: {
        ...incoming.generation,
        stages: incomingStages.map((stage, index) => ({
          ...stage,
          sampling: { upscale_factor: Number(stage?.sampling?.upscale_factor ?? currentStages[index]?.sampling?.upscale_factor ?? 1.5) },
        })),
      },
      composition: { ...(advancedState.composition || {}), ...(incoming.composition || {}) },
    });
    return advancedState;
  };
  const widget = node.addDOMWidget("xyue_h3_studio", "xyue_h3_studio", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => FRAME_HEIGHT,
  });
  widget.computeLayoutSize = () => ({ minHeight: FRAME_HEIGHT, minWidth: 1380 });

  const sendConfig = async () => {
    const config = { ...mergeAdvanced(readConfig(configWidget)), ...canvasMaterialOverrides(node) };
    const studioId = config.studio_id || `node-${node.id}`;
    try {
      await fetch("/xyue-h3/materials/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ studio_id: studioId, material_overrides: config.material_overrides }),
      });
    } catch {
      // The backend may still be restarting; the next Studio sync retries.
    }
    frame.contentWindow?.postMessage({
      type: "xyue-h3:aggregate-init",
      config,
      storageKey: studioId,
    }, window.location.origin);
  };
  const installFetchBridge = () => {
    const windowRef = frame.contentWindow;
    if (!windowRef || windowRef.__xyueAggregateFetchBridge) return;
    const originalFetch = windowRef.fetch.bind(windowRef);
    windowRef.fetch = (input, init = {}) => {
      const url = typeof input === "string" ? input : String(input?.url || "");
      if (url.includes("/xyue-h3/aggregate/preview") && init?.body) {
        try {
          const payload = JSON.parse(String(init.body));
          const config = mergeAdvanced(payload);
          init = { ...init, body: JSON.stringify({ ...payload, ...config }) };
        } catch {
          // Let the Studio surface its normal submission error.
        }
      }
      return originalFetch(input, init);
    };
    windowRef.__xyueAggregateFetchBridge = true;
  };
  const onMessage = (event) => {
    if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
    if (event.data?.type === "xyue-h3:aggregate-ready") sendConfig();
    if (event.data?.type === "xyue-h3:aggregate-config") {
      const materials = canvasMaterialOverrides(node);
      mergeAdvanced(event.data.config);
      writeConfig(node, configWidget, {
        ...advancedState,
        ...materials,
      });
    }
  };

  window.addEventListener("message", onMessage);
  frame.addEventListener("load", sendConfig);
  frame.addEventListener("load", installFetchBridge);
  const toggleLibraryMaterial = (item) => {
    const selected = materialSelection(node);
    const key = `${item.kind}:${item.file}`;
    const next = !selected[key];
    if (next) {
      const current = canvasMaterialOverrides(node).assets.filter((entry) => entry.kind === item.kind && entry.enabled);
      if (current.length >= MATERIAL_LIMITS[item.kind]) return;
    }
    selected[key] = next;
    node.graph?.setDirtyCanvas?.(true, true);
    node.__xyueAggregateStudio?.sendConfig();
  };
  const removeReferenceTools = mountIframeReferenceTools(
    frame,
    () => canvasMaterialOverrides(node),
    toggleLibraryMaterial,
  );
  fetch("/xyue-h3/materials", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : { materials: [] })
    .then((payload) => {
      node.__xyueComfyMaterials = Array.isArray(payload.materials) ? payload.materials : [];
      node.__xyueAggregateStudio?.sendConfig();
    })
    .catch(() => {});
  node.__xyueAggregateStudio = {
    sendConfig,
    destroy: () => window.removeEventListener("message", onMessage),
  };

  const previousRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    node.__xyueAggregateStudio?.destroy();
    removeReferenceTools();
    delete node.__xyueAggregateStudio;
    return previousRemoved?.apply(this, args);
  };

  const width = Math.max(Number(node.size?.[0] || 0), NODE_WIDTH);
  const height = Math.max(Number(node.size?.[1] || 0), FRAME_HEIGHT + 50);
  node.setSize?.([width, height]);
}

app.registerExtension({
  name: "XYUE.H3.AggregateStudio",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      mountStudio(this);
      return result;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = onConfigure?.apply(this, args);
      mountStudio(this);
      return result;
    };
  },
});
