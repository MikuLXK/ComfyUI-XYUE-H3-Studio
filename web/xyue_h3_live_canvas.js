import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SNAPSHOT_FILE = "xyue_h3_studio/live_canvas.json";
const PENDING_FILE = "xyue_h3_studio/pending_apply.json";
const ASSET_TYPES = new Set([
  "XYUE_H3_ImageAsset",
  "XYUE_H3_VideoAsset",
  "XYUE_H3_AudioAsset",
]);

function widget(node, name) {
  return (node?.widgets || []).find((item) => item.name === name);
}

function assetState(node) {
  const kind = node.type === "XYUE_H3_ImageAsset" ? "image" : node.type === "XYUE_H3_VideoAsset" ? "video" : "audio";
  const fileWidget = kind === "image" ? "image" : kind === "video" ? "video" : "audio";
  const file = String(widget(node, fileWidget)?.value || "").trim();
  const empty = new Set(["", "未选择图片", "未选择视频", "未选择音频", "UNKNOWN"]);
  const imported = !empty.has(file);
  const serialized = Array.isArray(node.widgets_values) ? node.widgets_values : [];
  const enabled = serialized.length > 1 ? serialized[1] !== false : widget(node, "enabled")?.value !== false;
  return {
    id: node.id,
    type: node.type,
    title: node.title || node.type,
    kind,
    file,
    imported,
    enabled,
    active: imported && enabled,
    alias_mode: String(widget(node, "alias_mode")?.value || ""),
    role: String(widget(node, "role")?.value || ""),
  };
}

function setWidgetValue(node, index, value) {
  const item = node.widgets?.[index];
  if (!item) return false;
  try {
    item.value = value;
    if (typeof item.callback === "function") item.callback(value);
  } catch (error) {
    console.warn("[XYUE H3] 应用画布配置失败", node.id, index, error);
  }
  return true;
}

function migrateWidgetValues(node) {
  const values = Array.isArray(node.widgets_values) ? node.widgets_values : null;
  if (!values) return false;
  let migrated = null;
  if (node.type === "XYUE_H3_StageGenerationProfile" && values.length >= 15) {
    const title = String(node.title || "");
    const stageName = typeof values[15] === "string" && !["单次采样", "双段采样"].includes(values[15])
      ? values[15]
      : (title.match(/第\d+段|阶段\d+/)?.[0] || "第一阶段");
    migrated = [...values.slice(0, 10), stageName];
  } else if (node.type === "XYUE_H3_StudioController" && values.length >= 17) {
    migrated = [...values.slice(0, 11), values[16] ?? 3];
  } else if (node.type === "XYUE_H3_GenerationProfile" && values.length >= 15) {
    migrated = values.slice(0, 10);
  }
  if (!migrated) return false;
  node.widgets_values = migrated;
  migrated.forEach((value, index) => setWidgetValue(node, index, value));
  return true;
}

function migrateGraphWidgets() {
  let changed = false;
  for (const node of app.graph?._nodes || []) changed = migrateWidgetValues(node) || changed;
  if (changed) app.graph?.setDirtyCanvas?.(true, true);
  return changed;
}

const MULTI_STAGE_SCHEMA = "xyue.h3.multi-stage-cloud-config/v1";
const MAX_STAGES = 5;
const STAGE_AUTO_STATE = "xyue_h3_auto_mode_state";
let syncingControlModes = false;

function graphNodes() {
  return app.graph?._nodes || [];
}

function groupNodes(group) {
  group.recomputeInsideNodes?.();
  const children = group._children ? Array.from(group._children) : (group._nodes || []);
  return children.filter((node) => node && typeof node.mode === "number");
}

function stageIndexFromGroup(group) {
  const explicit = Number(group.properties?.xyue_stage_index || 0);
  if (explicit > 0) return explicit;
  const title = String(group.title || "");
  const numeric = title.match(/(?:^|阶段\s*)(\d+)/);
  if (numeric) return Number(numeric[1]);
  const match = title.match(/第([一二三四五六七八九十]+)阶段/);
  const markers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  return match ? markers.indexOf(match[1]) + 1 : 0;
}

function parseMultiStageConfig(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  try {
    const config = JSON.parse((fenced ? fenced[1] : text).trim());
    return config?.schema === MULTI_STAGE_SCHEMA ? config : null;
  } catch (error) {
    return null;
  }
}

function controlState() {
  const nodes = graphNodes();
  const controller = nodes.find((node) => node.type === "XYUE_H3_StudioController");
  const acceleration = nodes.find((node) => node.type === "XYUE_H3_GlobalAccelerationManager");
  const configNode = nodes.find((node) => node.type === "XYUE_H3_MultiStageConfig");
  const config = parseMultiStageConfig(widget(configNode, "config_text")?.value);
  const serializedController = Array.isArray(controller?.widgets_values) ? controller.widgets_values : [];
  const configuredStageCount = Number(widget(controller, "stage_count")?.value ?? serializedController[11] ?? serializedController[16] ?? 3);
  const configuredAcceleration = String(widget(acceleration, "mode")?.value || acceleration?.widgets_values?.[0] || "不启用");
  return {
    stageCount: Math.max(1, Math.min(MAX_STAGES, Number(config?.stage_count || configuredStageCount || 3))),
    accelerationMode: String(config?.acceleration?.global_mode || configuredAcceleration || "不启用"),
  };
}

const STAGE_MARKERS = ["第一阶段", "第二阶段", "第三阶段", "第四阶段", "第五阶段"];
let applyingConfigToCanvas = false;
let lastAppliedConfigSignature = "";

function stageNodes(type) {
  return graphNodes()
    .filter((node) => node.type === type)
    .sort((a, b) => Number(a.properties?.xyue_stage_index || 0) - Number(b.properties?.xyue_stage_index || 0));
}

function setWidget(node, name, value) {
  const item = widget(node, name);
  if (!item || value === undefined || value === null) return false;
  if (item.value === value) return false;
  item.value = value;
  const index = node.widgets?.indexOf(item) ?? -1;
  if (index >= 0 && Array.isArray(node.widgets_values)) node.widgets_values[index] = value;
  if (typeof item.callback === "function") item.callback(value);
  return true;
}

function applyProfileWidgets(node, values) {
  let changed = false;
  for (const [name, value] of Object.entries(values || {})) {
    changed = setWidget(node, name, value) || changed;
  }
  return changed;
}

function applyMultiStageConfigToCanvas({ notify = false } = {}) {
  if (applyingConfigToCanvas || !app.graph) return false;
  const configNode = graphNodes().find((node) => node.type === "XYUE_H3_MultiStageConfig");
  const config = parseMultiStageConfig(widget(configNode, "config_text")?.value);
  if (!config) {
    lastAppliedConfigSignature = "";
    return false;
  }
  const signature = JSON.stringify(config);
  if (signature === lastAppliedConfigSignature) return false;

  applyingConfigToCanvas = true;
  let changed = false;
  try {
    const generation = config.generation || {};
    const stages = Array.isArray(generation.stages) ? generation.stages : [];
    const global = generation.global || {};
    const editors = stageNodes("XYUE_H3_PromptEditor");
    const enhancers = stageNodes("XYUE_H3_PromptEnhancer");
    const profiles = stageNodes("XYUE_H3_StageGenerationProfile");

    editors.forEach((node, index) => {
      const stage = { ...global, ...(stages[index] || {}) };
      changed = applyProfileWidgets(node, {
        duration: stage.duration,
        draft: config.prompts?.[index],
        stage_index: index + 1,
      }) || changed;
    });
    enhancers.forEach((node, index) => {
      const stage = { ...global, ...(stages[index] || {}) };
      changed = applyProfileWidgets(node, {
        duration: stage.duration,
        enabled: false,
        stage_index: index + 1,
      }) || changed;
    });

    profiles.forEach((node, index) => {
      const stage = { ...global, ...(stages[index] || {}) };
      const sampling = stage.sampling || {};
      changed = applyProfileWidgets(node, {
        aspect: stage.aspect,
        resolution: stage.resolution,
        duration: stage.duration,
        steps: stage.steps,
        audio_steps: stage.audio_steps,
        scheduler: stage.scheduler,
        reference_size: stage.reference_size,
        sampling_preset: sampling.sampling_preset || stage.sampling_preset,
        stage_name: STAGE_MARKERS[index],
      }) || changed;
    });

    const controller = graphNodes().find((node) => node.type === "XYUE_H3_StudioController");
    if (controller) {
      changed = setWidget(controller, "stage_count", config.stage_count) || changed;
      if (typeof generation.global_enabled === "boolean") {
        changed = setWidget(controller, "global_enabled", generation.global_enabled) || changed;
      }
      changed = applyProfileWidgets(controller, {
        aspect: global.aspect,
        resolution: global.resolution,
        duration: global.duration,
        steps: global.steps,
        audio_steps: global.audio_steps,
        scheduler: global.scheduler,
        reference_size: global.reference_size,
        sampling_preset: global.sampling?.sampling_preset || global.sampling_preset,
      }) || changed;
    }

    const acceleration = graphNodes().find((node) => node.type === "XYUE_H3_GlobalAccelerationManager");
    if (acceleration) {
      changed = setWidget(acceleration, "mode", config.acceleration?.global_mode) || changed;
    }
    changed = syncControlModes() || changed;
    lastAppliedConfigSignature = signature;
    if (changed) {
      app.graph.setDirtyCanvas?.(true, true);
      scheduleSnapshot();
      if (notify) showToast("success", "XYUE H3 多段配置已同步到画布", `已更新 ${config.stage_count} 个阶段`);
    }
    return changed;
  } finally {
    applyingConfigToCanvas = false;
  }
}

function setAutomaticMute(node, reason, muted) {
  const properties = node.properties || (node.properties = {});
  const state = properties[STAGE_AUTO_STATE] || {};
  let changed = false;
  if (muted) {
    if (!state[reason]) {
      state[reason] = true;
      if (state.original_mode == null) state.original_mode = node.mode;
      changed = true;
    }
    if (node.mode !== 2) {
      node.mode = 2;
      changed = true;
    }
  } else if (state[reason]) {
    delete state[reason];
    changed = true;
    const hasOtherReason = Object.keys(state).some((key) => key !== "original_mode");
    if (!hasOtherReason) {
      const restored = state.original_mode == null ? 0 : state.original_mode;
      if (node.mode !== restored) node.mode = restored;
      delete properties[STAGE_AUTO_STATE];
    }
  }
  if (Object.keys(state).some((key) => key !== "original_mode")) properties[STAGE_AUTO_STATE] = state;
  return changed;
}

function syncControlModes() {
  if (syncingControlModes || !app.graph) return false;
  syncingControlModes = true;
  let changed = false;
  try {
    const state = controlState();
    for (const node of graphNodes()) {
      const stageIndex = Number(node.properties?.xyue_stage_index || 0);
      if (stageIndex) {
        changed = setAutomaticMute(node, "stage", stageIndex > state.stageCount) || changed;
      }
    }
    for (const group of app.graph._groups || []) {
      const stageIndex = stageIndexFromGroup(group);
      if (!stageIndex) continue;
      for (const node of groupNodes(group)) {
        if (!node.properties?.xyue_stage_index) {
          changed = setAutomaticMute(node, "stage", stageIndex > state.stageCount) || changed;
        }
      }
    }
    for (const node of graphNodes()) {
      const modes = node.properties?.xyue_acceleration_modes;
      if (!Array.isArray(modes) || !modes.length) continue;
      changed = setAutomaticMute(node, "acceleration", !modes.includes(state.accelerationMode)) || changed;
    }
  } finally {
    syncingControlModes = false;
  }
  if (changed) app.graph.setDirtyCanvas?.(true, true);
  return changed;
}

let appliedVersion = 0;

function showToast(severity, summary, detail) {
  try {
    app.extensionManager?.toast?.add({
      severity,
      summary,
      detail: detail || "",
      lifespan: 5000,
    });
  } catch (error) {
    console.info(`[XYUE H3] ${summary} ${detail || ""}`);
  }
}

async function applyPending() {
  let response;
  try {
    response = await api.getUserData(PENDING_FILE);
  } catch (error) {
    return;
  }
  if (response?.status !== 200) return;
  let payload;
  try {
    payload = JSON.parse(await response.text());
  } catch (error) {
    return;
  }
  const version = Number(payload?.version || 0);
  if (!version || version <= appliedVersion) return;
  let changed = false;
  let graphReplaced = false;
  if (payload.graph_replace && payload.workflow && typeof app.loadGraphData === "function") {
    try {
      await app.loadGraphData(payload.workflow);
      graphReplaced = true;
      changed = true;
    } catch (error) {
      console.warn("[XYUE H3] 结构化工作流迁移失败，回退到节点属性应用", error);
    }
  }
  if (!graphReplaced) {
    for (const item of payload.nodes || []) {
      const node = (app.graph?._nodes || []).find(
        (candidate) => String(candidate.id) === String(item.id) && candidate.type === item.type
      );
      if (!node) continue;
      if (Array.isArray(item.widgets_values)) {
        item.widgets_values.forEach((value, index) => {
          if (setWidgetValue(node, index, value)) changed = true;
        });
      }
      if (typeof item.title === "string" && item.title) {
        node.title = item.title;
        changed = true;
      }
    }
  }
  if (changed) {
    changed = syncControlModes() || changed;
    app.graph?.setDirtyCanvas?.(true, true);
    scheduleSnapshot();
  }
  appliedVersion = version;
  try {
    await api.deleteUserData(PENDING_FILE);
  } catch (error) {
    console.warn("[XYUE H3] 清理待应用配置失败", error);
  }
  const appliedCount = changed
    ? (payload.nodes || []).filter((item) => (app.graph?._nodes || []).some(
        (node) => String(node.id) === String(item.id) && node.type === item.type
      )).length
    : 0;
  showToast(
    changed ? "success" : "info",
     `XYUE H3 多段配置已应用${payload.auto_queue ? "并排队" : ""}`,
    `更新 ${appliedCount} 个节点`
  );
  if (payload.auto_queue) {
    try {
      if (typeof app.queuePrompt === "function") {
        await app.queuePrompt(0, 1);
      } else {
        const prompt = await app.graphToPrompt();
        await api.queuePrompt(0, prompt?.output ?? prompt);
      }
      console.info("[XYUE H3] 配置已应用并自动排队");
      showToast("success", "XYUE H3 已开始排队生成", "生成任务已提交到队列");
    } catch (error) {
      console.warn("[XYUE H3] 自动排队失败，请手动点击排队", error);
      showToast("error", "XYUE H3 自动排队失败", "请手动点击 Queue");
    }
  }
}

function buildSnapshot() {
  const assets = (app.graph?._nodes || []).filter((node) => ASSET_TYPES.has(node.type)).map(assetState);
  const counts = { image: 0, video: 0, audio: 0 };
  for (const asset of assets) {
    asset.execution_index = asset.active ? ++counts[asset.kind] : null;
  }
  return {
    schema: "xyue.h3.live_canvas/v1",
    captured_at: new Date().toISOString(),
    workflow: app.graph?.serialize?.() || null,
    assets,
    active_counts: counts,
  };
}

let timer = null;
let lastPayload = "";

async function publishSnapshot() {
  timer = null;
  const payload = JSON.stringify(buildSnapshot());
  if (payload === lastPayload) return;
  try {
    await api.storeUserData(SNAPSHOT_FILE, payload, {
      overwrite: true,
      stringify: false,
      throwOnError: true,
    });
    lastPayload = payload;
  } catch (error) {
    console.warn("[XYUE H3] 当前画布快照写入失败", error);
  }
}

function scheduleSnapshot() {
  if (timer !== null) clearTimeout(timer);
  timer = setTimeout(() => void publishSnapshot(), 250);
}

app.registerExtension({
  name: "XYUE.H3.LiveCanvas",
  setup() {
    const graph = app.graph;
    if (!graph || graph.__xyueH3LiveCanvasInstalled) return;
    graph.__xyueH3LiveCanvasInstalled = true;
    const previous = graph.onAfterChange;
    graph.onAfterChange = function (...args) {
      const result = previous?.apply(this, args);
      migrateGraphWidgets();
      applyMultiStageConfigToCanvas({ notify: true });
      syncControlModes();
      scheduleSnapshot();
      return result;
    };
    syncControlModes();
    applyMultiStageConfigToCanvas();
    scheduleSnapshot();
    window.addEventListener("focus", scheduleSnapshot);
    setInterval(() => {
      if (!document.hidden) {
        migrateGraphWidgets();
        applyMultiStageConfigToCanvas({ notify: true });
        syncControlModes();
        void applyPending();
      }
    }, 2000);
    setInterval(() => scheduleSnapshot(), 30000);
  },
});
