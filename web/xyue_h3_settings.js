import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const fields = [
  ["name", "名称", "text"], ["base_url", "Base URL", "url"], ["model", "模型名", "text"],
  ["endpoint_path", "端点路径（可留空）", "text"], ["temperature", "温度", "number"], ["max_output_tokens", "最大输出 tokens", "number"],
  ["timeout_seconds", "超时（秒，留空=无超时）", "number"], ["retries", "重试次数", "number"], ["api_key", "API Key", "password"],
];

async function jsonRequest(path, options = {}) {
  const response = await api.fetchApi(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || body.message || `HTTP ${response.status}`);
  return body;
}

function openManager() {
  const shade = document.createElement("div");
  Object.assign(shade.style, { position: "fixed", inset: 0, zIndex: 10001, background: "#0009", display: "flex", alignItems: "center", justifyContent: "center" });
  const panel = document.createElement("div");
  Object.assign(panel.style, { background: "#20242a", color: "#eee", width: "min(760px, 94vw)", maxHeight: "90vh", overflow: "auto", padding: "18px", borderRadius: "8px", fontFamily: "sans-serif" });
  shade.append(panel); document.body.append(shade);
  const title = document.createElement("h2"); title.textContent = "XYUE H3 / API 配置"; panel.append(title);
  const toolbar = document.createElement("div"); toolbar.style.display = "flex"; toolbar.style.gap = "8px"; panel.append(toolbar);
  const select = document.createElement("select"); select.style.flex = "1"; toolbar.append(select);
  const add = document.createElement("button"); add.textContent = "新增"; toolbar.append(add);
  const remove = document.createElement("button"); remove.textContent = "删除"; toolbar.append(remove);
  const form = document.createElement("div"); Object.assign(form.style, { display: "grid", gridTemplateColumns: "150px 1fr", gap: "8px", marginTop: "14px" }); panel.append(form);
  const controls = {};
  for (const [name, label, type] of fields) {
    const caption = document.createElement("label"); caption.textContent = label; caption.style.alignSelf = "center"; form.append(caption);
    const row = document.createElement("div"); row.style.display = "flex"; row.style.gap = "6px";
    const input = document.createElement("input"); input.name = name; input.type = type; input.style.width = "100%";
    if (name === "endpoint_path") { input.placeholder = "按协议自动使用 /v1/responses 或 /v1/chat/completions"; input.title = "这是 API 路径，不是模型名；留空即可使用协议默认路径。"; }
    if (name === "max_output_tokens") input.placeholder = "64000";
    if (name === "timeout_seconds") input.placeholder = "留空表示无超时";
    row.append(input);
    if (name === "model") {
      const getModels = document.createElement("button"); getModels.type = "button"; getModels.textContent = "一键获取模型"; getModels.title = "先保存 Base URL 和 API Key，再从兼容服务读取 /v1/models";
      getModels.onclick = async () => {
        if (!select.value) { status.textContent = "请先保存 Base URL 和 API Key，再获取模型列表"; return; }
        try {
          status.textContent = "获取模型列表中…";
          const result = await jsonRequest(`/xyue-h3/profiles/${encodeURIComponent(select.value)}/models`);
          const models = result.models || [];
          if (!models.length) { status.textContent = "服务没有返回可选模型"; return; }
          const choice = window.prompt(`可用模型：\n${models.join("\n")}\n\n请输入模型 ID`, input.value || models[0]);
          if (choice !== null) input.value = choice.trim();
          status.textContent = `已获取 ${models.length} 个模型`;
        } catch (error) { status.textContent = `获取模型失败：${error.message}`; }
      };
      row.append(getModels);
    }
    form.append(row); controls[name] = input;
  }
  const protocolLabel = document.createElement("label"); protocolLabel.textContent = "协议"; form.append(protocolLabel);
  const protocol = document.createElement("select"); protocol.innerHTML = '<option value="responses">Responses</option><option value="chat_completions">Chat Completions</option>'; form.append(protocol);
  const headersLabel = document.createElement("label"); headersLabel.textContent = "额外请求头（JSON）"; form.append(headersLabel);
  const headers = document.createElement("textarea"); headers.rows = 3; headers.style.width = "100%"; form.append(headers);
  const status = document.createElement("div"); status.style.gridColumn = "1 / 3"; status.style.minHeight = "24px"; form.append(status);
  const actions = document.createElement("div"); actions.style.display = "flex"; actions.style.gap = "8px"; actions.style.marginTop = "14px"; panel.append(actions);
  const save = document.createElement("button"); save.textContent = "保存配置"; actions.append(save);
  const test = document.createElement("button"); test.textContent = "测试连接"; actions.append(test);
  const upload = document.createElement("button"); upload.textContent = "上传参考文档"; actions.append(upload);
  const close = document.createElement("button"); close.textContent = "关闭"; close.style.marginLeft = "auto"; actions.append(close);
  close.onclick = () => shade.remove();

  let profiles = [];
  const clearForm = () => {
    for (const input of Object.values(controls)) input.value = "";
    controls.temperature.value = "0.2";
    controls.max_output_tokens.value = "64000";
    controls.retries.value = "2";
    controls.timeout_seconds.value = "";
    protocol.value = "responses";
    controls.endpoint_path.placeholder = "/v1/responses（留空使用默认）";
    headers.value = "{}";
  };
  const fill = (profile) => {
    clearForm();
    if (!profile) return;
    for (const [name] of fields) if (name !== "api_key") controls[name].value = profile[name] ?? "";
    controls.max_output_tokens.value = profile.max_output_tokens ?? 64000;
    controls.timeout_seconds.value = profile.timeout_seconds ?? "";
    controls.api_key.placeholder = profile.has_key ? "已保存（留空保持不变）" : "";
    protocol.value = profile.protocol || "responses";
    controls.endpoint_path.placeholder = protocol.value === "responses" ? "/v1/responses（留空使用默认）" : "/v1/chat/completions（留空使用默认）";
    headers.value = JSON.stringify(profile.headers || {}, null, 2);
  };
  const refresh = async () => {
    try {
      profiles = (await jsonRequest("/xyue-h3/profiles")).profiles || [];
      select.innerHTML = "";
      for (const profile of profiles) { const option = document.createElement("option"); option.value = profile.id; option.textContent = `${profile.name} · ${profile.model}`; select.append(option); }
      fill(profiles[0]);
    } catch (error) { status.textContent = `读取失败：${error.message}`; }
  };
  select.onchange = () => fill(profiles.find((profile) => profile.id === select.value));
  protocol.onchange = () => { if (!controls.endpoint_path.value) controls.endpoint_path.placeholder = protocol.value === "responses" ? "/v1/responses（留空使用默认）" : "/v1/chat/completions（留空使用默认）"; };
  add.onclick = () => { select.value = ""; clearForm(); controls.name.focus(); };
  remove.onclick = async () => { if (!select.value || !confirm("删除当前 API 配置？")) return; await jsonRequest(`/xyue-h3/profiles/${encodeURIComponent(select.value)}`, { method: "DELETE" }); await refresh(); };
  save.onclick = async () => {
    try {
      const headersValue = headers.value.trim() ? JSON.parse(headers.value) : {};
      const payload = { id: select.value || undefined, ...Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, input.value])), protocol: protocol.value, headers: headersValue };
      for (const key of ["temperature", "max_output_tokens", "retries"]) if (payload[key] !== "") payload[key] = Number(payload[key]);
      payload.timeout_seconds = payload.timeout_seconds === "" ? null : Number(payload.timeout_seconds);
      const saved = await jsonRequest("/xyue-h3/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      status.textContent = "已保存（密钥只保存在 ComfyUI 服务端）"; await refresh(); select.value = saved.id; fill(saved);
    } catch (error) { status.textContent = `保存失败：${error.message}`; }
  };
  test.onclick = async () => { if (!select.value) { status.textContent = "请先保存配置"; return; } try { status.textContent = "测试中…"; await jsonRequest(`/xyue-h3/profiles/${encodeURIComponent(select.value)}/test`, { method: "POST" }); status.textContent = "连接测试成功"; } catch (error) { status.textContent = `测试失败：${error.message}`; } };
  upload.onclick = () => {
    const input = document.createElement("input"); input.type = "file"; input.accept = ".pdf,.docx,.txt,.md,.json";
    input.onchange = async () => { if (!input.files[0]) return; const body = new FormData(); body.append("file", input.files[0]); try { const result = await jsonRequest("/xyue-h3/documents", { method: "POST", body }); status.textContent = `文档已上传：${result.filename}`; } catch (error) { status.textContent = `上传失败：${error.message}`; } };
    input.click();
  };
  refresh();
}

app.registerExtension({
  name: "XYUE.H3.Settings",
  setup() {
    const settingId = "XYUE.H3.APIProfiles";
    app.ui.settings.addSetting({ id: settingId, name: "XYUE H3 / API 配置", type: "text", defaultValue: "" });

    // ComfyUI's settings registry does not expose a button type in all builds;
    // replace only this setting's editor when the settings dialog renders it.
    const installButton = () => {
      const root = app.ui.settings.element || document.body;
      for (const input of root.querySelectorAll("input")) {
        if (input.dataset.xyueH3ApiButton) continue;
        let row = input.parentElement;
        while (row && row !== root && !row.textContent?.includes("XYUE H3 / API 配置")) row = row.parentElement;
        if (!row || !row.textContent?.includes("XYUE H3 / API 配置")) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "管理 API 配置";
        button.title = "打开后主动管理多个 API 配置；启动时不会自动弹出。";
        button.onclick = openManager;
        input.dataset.xyueH3ApiButton = "true";
        input.replaceWith(button);
      }
    };
    const observer = new MutationObserver(installButton);
    observer.observe(document.body, { childList: true, subtree: true });
    installButton();
  },
});
