# ComfyUI-XYUE-H3-Studio

## H3 双段采样与聚合剪辑

每个镜头设置画面比例、初始分辨率、基础视频/音频步数、Sigma 精修步数、降噪程度和潜空间放大倍率。Studio 动态执行 H3+Sigma+潜空间放大双段链路：基础 Sigma 调度 → Sigma 强化 → 第一次采样 → 视频 latent 放大（音频不放大）→ conditioning 同步 → 第二次采样。

Studio 顶栏的“进入剪辑”会打开独立二级剪辑页。剪辑页支持预览、逐帧定位、入点/出点、分割、复制、移除、排序、音量和静音，并通过 FFmpeg 导出实际成片。操作是非破坏性的，不修改阶段源文件。

## Motion Context 说明

“动作音频续接”已接入 H3 Motion Context，和“尾帧续接”是两种独立能力：尾帧续接只引用上一镜最后一帧；动作音频续接会携带上一镜末尾连续 22 帧和约 1 秒原声音频。若上一镜最终 latent 与本镜初始 latent 尺寸一致，XYUE 直接传递最终 AV latent；经过 latent 放大导致尺寸不一致时，则自动使用上一镜最终画面和声音，由 Motion Context 按本镜初始画布编码，不会错误使用第一次高 Sigma 采样产生的半成品 latent。

动作音频续接会在新镜开头生成一段固定上下文，并在解码后同步裁掉重复画面和对应音频。相邻镜头应保持相同初始比例和分辨率；普通独立切镜不加载 Motion Context。使用该模式前必须安装下方第三方节点并重启 ComfyUI。

参考插件：[ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)

独立的 MiniMax H3 本地生成工作室节点包。生成入口只有 `XYUE H3 Studio`，Studio 素材库直接读取 ComfyUI input/output 素材；内部执行器按当前项目配置直接调用 ComfyUI 核心和已安装的第三方节点适配器。

## 相关仓库

- [云端多段式 Skill](https://github.com/MikuLXK/h3-multi-stage-cloud-generation)：生成可粘贴到云端配置节点的多段 JSON。
- [本地多段式 Skill](https://github.com/MikuLXK/h3-multi-stage-generation)：检查画布、配置阶段、续跑并提交本地工作流。
- [MiniMax H3 Prompt Writing Skill](https://github.com/MiniMax-AI/MiniMax-H3)：两个多段式 Skill 使用的官方提示词 Skill。

## 项目计划

- [目标架构与重构计划](docs/XYUE_H3_Studio_目标架构与重构计划.md)
- [TODO](TODO.md)

## 安装

在 ComfyUI 的 `custom_nodes` 目录执行：

```powershell
git clone https://github.com/MikuLXK/ComfyUI-XYUE-H3-Studio.git
```

首次安装文档解析依赖：

```powershell
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-XYUE-H3-Studio\requirements.txt
```

重启 ComfyUI 后，节点会从当前安装的 `diffusion_models`、`text_encoders` 和 `vae` 动态读取模型下拉框，不在代码中固定模型文件名。

## 使用顺序

1. 在 Studio 素材台导入或选择 Image/Video/Audio 素材。
2. 在提示词框输入 `@` 或 `<`，从快速列表选择引用。
3. 在设置页的 `XYUE H3 / API 配置` 保存提示词强化服务配置，密钥只保存在 `ComfyUI/user/default/xyue_h3_studio/api_secrets.json`。
4. 在 Studio 中配置当前镜头；初始画布由分辨率决定，二次采样画布由 latent 放大倍率自动推导。每个镜头可以分别设置 LoRA 开关、LoRA 文件、强度和注意力后端（`MiniMax H3 Kitchen Attention` / `Patch Sol-Attn`）。
5. 云端部署时直接输出 `xyue.h3.multi-stage-cloud-config/v1` JSON；本地 Studio 使用 `xyue-h3/studio-config-v3`，不再依赖配置节点或固定工作流模板。
6. Studio 只执行当前目标镜头；前镜结果按轨道关系复用。每个镜头的 LoRA 和注意力后端在执行器内真实调用。

## H3 Latent 双段精修

XYUE 的双段流程与 `H3+sigma强化+潜空间放大.json` 一致：基础视频/音频步数、Sigma 精修步数和降噪程度分开保存。默认是基础视频 `4`、基础音频 `4`、Sigma 精修 `3`、降噪 `0.30`；H3 的音画是联合 latent，实际共享基础采样次数取视频/音频步数的较大值。基础调度器生成 Sigma 后，Sigma 精修强化低 Sigma 尾段，分出高/低 Sigma；第一次采样后只放大视频 latent，保留原音频 latent，随后使用 `H3 Latent Cond Sync (3D)` 同步图像、首帧、尾帧和多参考 conditioning 到放大后尺寸，再以 CFG=1 的正/负条件完成第二次采样。参考文件使用 `0.4MP（864×480）→ 1.5x → 1296×720`；UI 只允许以一位小数调整 `1.0–4.0x` 倍率，例如 `1.4x`、`1.5x`、`1.6x`，不接受 `1.55x` 这类两位小数。

放大权重来自 [Minimax_h3_latent_Upscaler（Hugging Face）](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler)，适配节点来自 [Comfyui_Minimax_h3_latent_Upscaler（GitHub）](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)，放大权重放入 `ComfyUI/models/latent_upscale_models/`。双段流程会增加第二次采样和精修阶段显存占用。

`tiny_vae` 只用于采样过程中的实时预览，不影响最终视频质量。该功能需要已安装的 `ComfyUI-KJNodes`。下拉框会完整读取 `ComfyUI/models/vae_approx/`，默认使用 `none`；若所选解码器的 latent 通道数与 H3 不匹配，KJ 预览器会忽略它并回退到普通预览。

## LoRA 与注意力后端

- Studio 每个镜头都有“启用 LoRA”开关、LoRA 文件和强度。开关打开后先对 H3 主模型执行 `LoraLoaderModelOnly`，再应用所选注意力后端；关闭时不会加载 LoRA。
- 注意力后端提供两个选项：`MiniMax H3 Kitchen Attention` 使用 ComfyUI 核心 `ModelAttentionBackend`，`Patch Sol-Attn` 使用 [ComfyUI-SolAttn_triton（GitHub）](https://github.com/kijai/ComfyUI-SolAttn_triton)。当前本机 Kitchen Attention 可用。
- 聚合 Studio 不再包含孤立的全局 LoRA 或旧加速控制器。公开执行入口将当前配置交给内部执行器，执行器再调用已安装的 ComfyUI 核心和第三方能力。

直接访问 Studio：`http://127.0.0.1:8188/xyue-h3/studio/`；也可以访问 `http://127.0.0.1:8188/xyue-h3` 自动跳转。页面嵌入 ComfyUI 或直接打开都支持实时生成状态。

### 必需的第三方节点与模型

| 项目 | 用途 | 链接 |
| --- | --- | --- |
| ComfyUI-SolAttn_triton | `SolAttnPatch` 加速节点 | [GitHub](https://github.com/kijai/ComfyUI-SolAttn_triton) |
| Comfyui_Minimax_h3_latent_Upscaler | H3 3D latent 放大节点 | [GitHub](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) |
| Minimax_h3_latent_Upscaler | latent 放大权重 | [Hugging Face](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler) |
| ComfyUI-H3-Motion-Context | 连续动作帧与原声音频续接 | [GitHub](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) |
| ComfyUI-KJNodes（可选） | `tiny_vae` 实时预览 | [GitHub](https://github.com/kijai/ComfyUI-KJNodes) |

实时预览使用 KJ Preview Override：采样过程中会发送中间 latent 的预览帧；配置为多帧预览时会发送动画 WebP 或 MP4，Studio 监看器会直接播放。最终视频仍以阶段完成后的 H3 解码结果为准。

聚合 Studio 不依赖固定工作流 JSON。每次运行根据当前项目和目标镜头动态构建执行图；用户可以从 Studio 导出本次真实执行图 JSON。插件仓库不再把旧的单镜、循环或五阶段模板作为运行资源。

Studio 支持 1-5 个独立镜头轨道：每个镜头可以单独生成、重试、保存和参与合成。独立切镜不需要前镜结果；尾帧续接和 Motion Context 只读取轨道上当前镜头前面的镜头。阶段视频、最终视频和报告按项目保存策略写入 `ComfyUI/output/xyue_h3/<项目名称>/`。

聚合 UI 的“承接上一镜尾帧”只确定尾帧来源，不会自动切换生成类型。选择多参考模式时，前一镜视频尾帧以 `@尾帧` 加入当前镜头素材包；选择首帧生视频模式时，同一尾帧连接当前镜头硬首帧入口。

音频素材节点使用 ComfyUI 原生音频上传协议，`上传/选择音频` 是可上传的文件下拉框，不是自由文本。声音锚点由“角色/对象名称 + 锚点类型”组成；关闭“启用音频”时允许暂时不上传文件。

分辨率下拉直接显示输出高度和 16:9 对齐尺寸，例如 `0.4MP|480p（864×480）`、`0.9MP|720p（1280×736，32倍数近似）`、`1.0MP|768p（1344×768）` 和 `2.0MP|1080p（1920×1088，32倍数近似，实验）`。其他画面比例按同档像素预算计算，并保持宽高为 32 的倍数。

API 管理器不会在 ComfyUI 启动时弹出，只有点击设置页的“管理 API 配置”按钮才会打开。新配置默认最大输出为 64,000 tokens，超时留空表示无超时；端点路径可以留空，系统会按协议自动使用 `/v1/responses` 或 `/v1/chat/completions`。保存配置后可点击“一键获取模型”读取兼容服务的 `/v1/models` 列表。

## 验证

```powershell
python_embeded\python.exe -m compileall -q ComfyUI\custom_nodes\ComfyUI-XYUE-H3-Studio
python_embeded\python.exe -m pytest ComfyUI\custom_nodes\ComfyUI-XYUE-H3-Studio\tests -q --import-mode=importlib
```
