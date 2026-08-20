# XYUE H3 Studio TODO

> 目标：完成 `docs/XYUE_H3_Studio_目标架构与重构计划.md`。
>
> 勾选规则：只有通过对应验收条件后才标记 `[x]`。

## A. 当前问题修复

- [x] 分辨率 MP 前缀重复归一化。
- [x] 全局控制器控件顺序修正。
- [x] 阶段生成配置控件顺序修正。
- [x] Sigma 步数、降噪、放大倍率、参考图策略映射修正。
- [x] 旧 Studio 会话的 NaN 数值自动归一化。
- [x] `@` 快速列表在全屏时重新定位。
- [x] Prompt 高亮层使用 ResizeObserver。
- [x] 提示词区域监听检查器和窗口尺寸变化。
- [x] 用干净 ComfyUI 进程确认 `/object_info` 已切换到新 schema。
- [x] 用真实 `/prompt` 提交一次当前目标镜头执行并确认无 validation error（CPU 测试模式模型加载异常不作为生成验收）。

## B. 当前镜头目标执行

- [x] 当前选中镜头作为本次运行目标。
- [x] 已生成镜头保留，不在运行前全量清空。
- [x] 已生成镜头显示“重新生成当前镜头”。
- [x] 增加 `run_stage`、`start_stage`、`execution_stages` 配置。
- [x] 独立切镜只加入当前目标镜头。
- [x] 尾帧 / Motion Context 加入轨道前一个镜头。
- [x] 前镜检查点使用 StageResume 复用。
- [x] Motion Context 从前镜保存视频输入，不再连接前镜生成器半成品 latent。
- [ ] 在真实 ComfyUI 中测试选中镜头 03、保留镜头 01/02、只生成镜头 03。
- [ ] 在真实 ComfyUI 中测试镜头 03 独立切镜且镜头 01/02 不存在。
- [ ] 在真实 ComfyUI 中测试镜头 03 尾帧续接前镜头 02。
- [ ] 在真实 ComfyUI 中测试镜头 03 Motion Context 续接前镜头 02。
- [ ] 处理前镜文件不存在时的精确提示和恢复入口。

## C. 重试和种子

- [x] 增加“沿用上次种子 / 随机种子”状态。
- [x] 随机模式运行前生成新 seed。
- [x] 沿用模式复用当前镜头最近 seed。
- [x] 在报告中写入真实使用 seed。
- [ ] 在历史记录中显示每次重试的 seed。
- [ ] 验证同 seed 重试的输入配置完全一致。

## D. 自动执行开关

- [x] `完成后自动下一镜` 新项目默认关闭。
- [x] `生成后自动合成` 新项目默认关闭。
- [x] 清理旧会话中强制开启的旧默认值策略。
- [x] 验证两个开关关闭时不会隐式提交下一阶段或合成节点。

## E. 动态执行图

- [x] 新建 `core/studio_config.py`。
- [x] 新建动态 Studio 执行器。
- [x] 新建项目配置 schema `xyue-h3/studio-config-v3`。
- [x] 把镜头、素材、采样、衔接、保存策略统一为配置对象。
- [x] 根据目标镜头动态调用 H3 模型链。
- [x] 根据目标镜头动态调用 LoRA 链。
- [x] 根据目标镜头动态调用 Kitchen / Sol-Attn 链。
- [x] 根据目标镜头动态调用双段采样链。
- [x] 根据目标镜头动态调用 latent 放大和条件同步链。
- [x] 根据轨道相邻关系动态调用尾帧链。
- [x] 根据轨道相邻关系动态调用 Motion Context 链。
- [x] 根据目标镜头动态保存阶段结果。
- [x] 根据剪辑配置动态执行最终合成。
- [x] 移除聚合运行时 `load_workflow()`。
- [x] 移除聚合运行时 `configure_workflow()`。
- [x] `/xyue-h3/aggregate/preview` 返回动态执行图。
- [x] 动态执行器按目标镜头直接调用底层能力。
- [x] 动态执行图随项目导出保存为本次实际 JSON。

## F. 模板清理

- [x] 停止把旧循环 / 全程模板作为运行时来源。
- [x] 从 README 移除“运行依赖固定模板”的描述。
- [x] 将固定工作流 JSON 从插件运行资源中移除。
- [x] 删除旧模板构建脚本和运行配置工具。
- [x] 删除插件内旧工作流模板文件。
- [x] 删除用户工作流目录中的旧 `XYUE_H3_*.json` 模板副本。
- [x] 清理 `canonical_workflow_template` 报告字段。

## G. 保存策略

- [x] 新建 `core/save_policy.py`。
- [x] 增加项目名称设置。
- [x] 增加项目输出文件夹设置。
- [x] 增加阶段文件命名模式。
- [x] 增加最终文件命名模式。
- [x] 增加“名称+编号”默认模式。
- [x] 增加阶段名、日期、时间、seed 模板变量。
- [x] 增加自动创建项目文件夹。
- [x] 增加重名递增 / 覆盖 / 阻止三种策略。
- [x] 阶段视频写入项目目录。
- [x] 最终视频写入项目目录。
- [x] 报告 JSON 写入项目目录。
- [x] 所有路径限制在 `ComfyUI/output` 内。
- [x] 保存报告记录实际路径、seed、模型、LoRA、注意力和采样参数。

## H. Studio UI

- [x] 顶部统一显示“当前项目”，不区分单镜 / 多镜模式。
- [x] 显示当前目标镜头。
- [x] 显示本次执行镜头列表。
- [x] 在 Studio 中增加“保存与命名”设置页。
- [x] 显示输出目录设置。
- [x] 显示文件名模板设置。
- [x] 底部轨道排序后刷新前镜关系。
- [x] 轨道显示已生成 / 未生成 / 当前目标状态。
- [ ] Prompt 高亮层补充测试不同字体、缩放和换行。
- [ ] `@` / `<` 列表补充全屏、滚动、边缘位置测试。
- [ ] 中间图片、动画 WebP、MP4 预览分别验证。
- [ ] 预览失败时显示明确回退提示。

## I. 节点清理

- [x] 从公开节点列表移除旧多段配置节点。
- [x] 从公开节点列表移除 StudioController。
- [x] 从公开节点列表移除 StageGenerationProfile。
- [x] 从公开节点列表移除 PromptEditor / PromptEnhancer / PromptOutput。
- [x] 从公开节点列表移除旧 LoRA 全局节点。
- [x] 从公开节点列表移除旧加速控制节点。
- [x] 从公开节点列表移除 VideoBoard / VideoConcat。
- [x] Studio 素材库替代 ImageAsset / VideoAsset / AudioAsset Manager。
- [x] Studio 文档库替代 DocumentAsset / DocumentManager。
- [x] 删除重复 UI 的网页注入代码。
- [x] 保留底层服务函数，不删除真实生成、保存、拼接能力。

## J. 第三方依赖

- [x] 启动时检查 H3 核心能力。
- [x] 检查 `Comfyui_Minimax_h3_latent_Upscaler`。
- [x] 检查 H3 latent 放大权重。
- [x] 检查 `ComfyUI-H3-Motion-Context`。
- [x] 选择 Sol-Attn 时检查 `ComfyUI-SolAttn_triton`。
- [x] 检查 `ComfyUI-KJNodes` 的实时预览能力。
- [x] 缺失依赖时区分“当前模式必需”和“可选功能”。
- [x] README 保持第三方 GitHub / Hugging Face 链接准确。
- [x] 不将第三方源码和权重复制到 XYUE 仓库。

## K. 测试

- [x] Python 编译检查。
- [x] 聚合网页脚本语法检查。
- [x] Studio TypeScript 类型检查。
- [x] Studio Vite 构建。
- [x] 两个现有工作流节点端口检查。
- [x] 目标镜头检查点连线单元测试。
- [x] 动态执行图 1 镜测试。
- [x] 动态执行图 3 镜测试。
- [x] 动态执行图 5 镜测试。
- [ ] 当前镜头独立 cut 测试。
- [ ] 当前镜头尾帧 tail 测试。
- [ ] 当前镜头 Motion Context 测试。
- [ ] 既有视频复用测试。
- [ ] 重试 seed 测试。
- [x] LoRA 开关测试。
- [x] Kitchen Attention 测试。
- [x] Sol-Attn 测试。
- [x] latent 条件同步测试。
- [x] 保存路径和重名测试。
- [x] ComfyUI `/object_info` 对齐测试。
- [x] ComfyUI `/prompt` 实际提交验证（节点校验通过；CPU 模式模型加载不作为生成验收）。
- [x] 干净重启后无旧 schema 测试。

## L. 同步和交付

- [x] 同步运行插件目录。
- [x] 同步纯净包 `ComfyUI/custom_nodes`。
- [x] 同步纯净包 `custom_nodes`。
- [x] 更新 README 安装和依赖说明。
- [x] 更新本地镜头 Skill。
- [x] 更新云端 Skill 的采样字段说明。
- [x] 更新 GitHub 插件仓库工作区。
- [x] 只提交当前有效代码、文档和导出示例。
- [x] 最终检查仓库中没有旧模板运行依赖。
