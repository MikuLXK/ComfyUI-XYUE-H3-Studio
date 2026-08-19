# ComfyUI-XYUE-H3-Studio

独立的 MiniMax H3 本地生成工作室节点包。所有自有节点使用 `XYUE_H3_` 前缀，分类为 `XYUE/H3 Studio`。

## 相关仓库

- [云端多段式 Skill](https://github.com/MikuLXK/h3-multi-stage-cloud-generation)：生成可粘贴到云端配置节点的多段 JSON。
- [本地多段式 Skill](https://github.com/MikuLXK/h3-multi-stage-generation)：检查画布、配置阶段、续跑并提交本地工作流。
- [MiniMax H3 Prompt Writing Skill](https://github.com/MiniMax-AI/MiniMax-H3)：两个多段式 Skill 使用的官方提示词 Skill。

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

1. 用 Image/Video/Audio Asset 和对应 Manager 聚合启用素材。
2. 将包连接到 Material Manager；Prompt Editor 支持 `@` 和 `<` 引用补全。
3. 在设置页的 `XYUE H3 / API 配置` 保存提示词强化服务配置，密钥只保存在 `ComfyUI/user/default/xyue_h3_studio/api_secrets.json`。
4. 连接模式模型选择、全局生成控制器和生成器；多段工作流可在全局控制器中统一调整分辨率、时长和步数，并在其下方的全局 LoRA 管理器统一选择 LoRA 与强度。
5. 云端部署时，将 `XYUE_多段云端配置` 节点接入多段工作流，粘贴 `xyue.h3.multi-stage-cloud-config/v1` JSON。模型、VAE 和 LoRA 保持工作流预配置。
6. 多段画布会按 `stage_count` 自动将未启用阶段整区 Mute；全局加速模式也会只保留当前分支，其余加速节点自动 Mute。后端仍保留 lazy 分支选择作为执行层安全控制。

## H3 Latent 双段精修

选择“高品质双段”时，XYUE 使用与 [H3 Latent Upscaler 插件](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) 示例一致的流程：低分辨率第一次采样、H3 3D latent 神经网络放大、conditioning 尺寸同步，再进行高分辨率第二次采样。低噪声 sigma 尾段会按余弦曲线加密，参考了 [MinimaxH3 双采样 V2 工作流](https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3) 的 `H3SigmaRefiner → SplitSigmas` 方案。

放大权重来自 [LBH-123-AI/Minimax_h3_latent_Upscaler](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler)，放入 `ComfyUI/models/latent_upscale_models/`。选择“高品质双段”后会增加第二次采样和精修阶段显存占用。

`tiny_vae` 只用于采样过程中的实时预览，不影响最终视频质量。该功能需要已安装的 `ComfyUI-KJNodes`。下拉框会完整读取 `ComfyUI/models/vae_approx/`，默认使用 `none`；若所选解码器的 latent 通道数与 H3 不匹配，KJ 预览器会忽略它并回退到普通预览。

## 加速控制

- T2VA、I2VA、FL2VA、L2VA 使用独立的 `XYUE_H3_LoRASelector`；节点动态读取 ComfyUI 的 LoRA 目录，也可选择“不使用 LoRA”直接旁路。
- `XYUE_H3_AccelerationController` 是加速总开关，默认关闭。关闭时通过懒执行直接选择原始模型，开启后才执行当前选择的加速分支。
- 两个短剧模板提供 `XYUE_H3_GlobalLoRAManager`，可统一控制所有阶段；关闭全局 LoRA 后，各阶段恢复独立选择。
- 多参考模式默认不应用首尾帧专用 LoRA，只有显式开启“允许用于多参考模式”后才会应用。
- 模板默认时长 5 秒、视频步数 12、音频步数 12，种子在每次生成后自动随机。全局控制器开启时统一覆盖所有启用阶段，关闭时由各阶段独立控制。
- 工作流包含可选的分块前馈、低显存注意力和稀疏注意力优化。所有优化都由总开关和模式分支控制，未选中的分支不会执行。
- 使用低步数 LoRA 时，应同步选择匹配的加速模式与采样步数；不要把首尾帧专用 LoRA 应用于多参考模式。

仓库只附带两个短剧工作流：`workflows/XYUE_H3_多段循环工作流.json` 和 `workflows/XYUE_H3_全程多参考短剧工作流.json`。工作流文件名、节点标题、分区和注释均使用中文；节点采用低饱和深色背景与浅灰白标题文字区分区域。

多段短剧流程支持最多 5 条横向阶段轨道：9 张图片、3 个音频和 3 个视频素材槽进入第一阶段；未启用且未上传的槽位不会参与验证或执行。每一段生成后都先由阶段检查点节点独立保存并提供该段即时预览，再由续接选择器输出实际采用的视频；任一后续阶段失败都不会丢失此前视频，也可以在对应续接选择器中读取已保存文件继续。五段视频完成面板负责在整条阶段链完成后统一展示六项阶段/最终结果并完成拼接，预览按上 3 下 3 顺序提供。多段共享一个全局生成控制器，默认每段 5 秒、视频 12 步、音频 12 步；聚合配置和普通多段配置均支持 1-15 秒阶段时长。关闭总开关后，各阶段配置可分别修改。普通多段和全程多参考工作流都内置“XYUE_多段云端配置”和“XYUE_五段视频完成面板”节点。

聚合 UI 的“承接上一镜尾帧”只确定尾帧来源，不会自动切换生成类型。选择多参考模式时，前一镜视频尾帧以 `@尾帧` 加入当前镜头素材包；选择首帧生视频模式时，同一尾帧连接当前镜头硬首帧入口。

音频素材节点使用 ComfyUI 原生音频上传协议，`上传/选择音频` 是可上传的文件下拉框，不是自由文本。声音锚点由“角色/对象名称 + 锚点类型”组成；关闭“启用音频”时允许暂时不上传文件。

分辨率下拉直接显示输出高度和 16:9 对齐尺寸，例如 `480p（864×480）`、`720p（1280×736，32倍数近似）`、`768p（1344×768）` 和 `1080p（1920×1088，32倍数近似，实验）`。其他画面比例按同档像素预算计算，并保持宽高为 32 的倍数。

API 管理器不会在 ComfyUI 启动时弹出，只有点击设置页的“管理 API 配置”按钮才会打开。新配置默认最大输出为 64,000 tokens，超时留空表示无超时；端点路径可以留空，系统会按协议自动使用 `/v1/responses` 或 `/v1/chat/completions`。保存配置后可点击“一键获取模型”读取兼容服务的 `/v1/models` 列表。

## 验证

```powershell
python_embeded\python.exe -m compileall -q ComfyUI\custom_nodes\ComfyUI-XYUE-H3-Studio
python_embeded\python.exe -m pytest ComfyUI\custom_nodes\ComfyUI-XYUE-H3-Studio\tests -q --import-mode=importlib
```
