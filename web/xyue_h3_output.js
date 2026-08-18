import { app } from "../../../scripts/app.js";

function promptWidget(node) {
  return (node.widgets || []).find((widget) => widget.name === "prompt");
}

function addOutputTools(node) {
  if (node.__xyueOutputTools) return;
  const source = promptWidget(node);
  if (!source) return;
  node.__xyueOutputTools = true;
  source.inputEl.readOnly = true;
  source.inputEl.style.opacity = "0.85";
  node.addWidget("button", "复制最终提示词", null, () => navigator.clipboard?.writeText(String(source.value || "")));
  node.addWidget("button", "保存为文本", null, () => {
    const blob = new Blob([String(source.value || "")], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "xyue_h3_prompt.txt"; link.click(); URL.revokeObjectURL(link.href);
  });
}

app.registerExtension({
  name: "XYUE.H3.Output",
  nodeCreated(node) { if (node.type === "XYUE_H3_PromptOutput") setTimeout(() => addOutputTools(node), 0); },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "XYUE_H3_PromptOutput") return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () { original?.apply(this, arguments); setTimeout(() => addOutputTools(this), 0); };
  },
});
