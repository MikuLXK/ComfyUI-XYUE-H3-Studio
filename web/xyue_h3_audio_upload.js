import { app } from "../../../scripts/app.js";

// ComfyUI's native AUDIOUPLOAD widget expects an AUDIO_UI preview widget.
// Built-in LoadAudio receives it from the core extension; custom audio nodes
// must declare the same native widget explicitly before construction.
app.registerExtension({
  name: "XYUE.H3.AudioUpload",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "XYUE_H3_AudioAsset") return;
    nodeData.input ??= {};
    const required = nodeData.input.required ?? {};
    // AUDIOUPLOAD resolves its preview widget during construction, so the
    // AUDIO_UI entry must precede the injected upload button in object order.
    const ordered = {};
    for (const [name, spec] of Object.entries(required)) {
      if (name === "upload") ordered.audioUI = ["AUDIO_UI", {}];
      ordered[name] = spec;
    }
    if (!ordered.audioUI) ordered.audioUI = ["AUDIO_UI", {}];
    nodeData.input.required = ordered;
  },
});
