import { app } from "../../../scripts/app.js";

const TITLE_TEXT = "#f3f4f6";

app.registerExtension({
  name: "XYUE.H3.Theme",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!String(nodeData.name || "").startsWith("XYUE_H3_")) return;
    nodeType.title_text_color = TITLE_TEXT;
  },
});
