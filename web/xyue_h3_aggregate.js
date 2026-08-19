import { app } from "../../../scripts/app.js";

const NODE_TYPE = "XYUE_H3_AggregateWorkflow";
const STUDIO_URL = "/xyue-h3/studio/";
const FRAME_HEIGHT = 860;
const NODE_WIDTH = 1500;
const DEFAULT_CONFIG = {
  schema: "xyue-h3/aggregate-workflow-config-v2",
  workflow: "全程多参考短剧",
  stage_count: 1,
  stage_titles: ["云海问剑"],
  prompts: ["integrated_multimodal_description: [Shot 1] ...\n\noverall_soundscape: ...\n\nnon_diegetic_music: ..."],
  durations: [5],
  transitions: ["cut"],
  acceleration_modes: ["模式2"],
  models: [{
    mode: "文生视频模式",
    base_model: "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    reference_model: "Minimax_H3\\minimax_h3_ref2va_XUELUO_int8_convrot.safetensors",
    language_model: "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    video_vae: "minimax_h3_video_vae_fp16.safetensors",
    audio_vae: "minimax_h3_audio_vae_fp32.safetensors",
    latent_upscale_model: "minimax_h3_latent_upscaler_3d_fp16.safetensors",
    tiny_vae: "none",
  }],
  generation: { global_enabled: false, stages: [{
    aspect: "16:9",
    resolution: "480p（864×480）",
    duration: 5,
    steps: 4,
    audio_steps: 4,
    scheduler: "简单稳定（推荐）",
    seed: 0,
    seed_control: "randomize",
    reference_size: "适配生成画布（省显存）",
    sampling: { sampling_preset: "高品质双段" },
  }] },
};

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

  const widget = node.addDOMWidget("xyue_h3_studio", "xyue_h3_studio", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => FRAME_HEIGHT,
  });
  widget.computeLayoutSize = () => ({ minHeight: FRAME_HEIGHT, minWidth: 1380 });

  const sendConfig = () => {
    const config = readConfig(configWidget);
    frame.contentWindow?.postMessage({
      type: "xyue-h3:aggregate-init",
      config,
      storageKey: config.studio_id || `node-${node.id}`,
    }, window.location.origin);
  };
  const onMessage = (event) => {
    if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
    if (event.data?.type === "xyue-h3:aggregate-ready") sendConfig();
    if (event.data?.type === "xyue-h3:aggregate-config") writeConfig(node, configWidget, event.data.config);
  };

  window.addEventListener("message", onMessage);
  frame.addEventListener("load", sendConfig);
  node.__xyueAggregateStudio = {
    sendConfig,
    destroy: () => window.removeEventListener("message", onMessage),
  };

  const previousRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    node.__xyueAggregateStudio?.destroy();
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
