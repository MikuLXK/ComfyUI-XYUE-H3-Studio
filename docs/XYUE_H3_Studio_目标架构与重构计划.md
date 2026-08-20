# XYUE H3 Studio 目标架构与重构计划

> 文档状态：已确认方案，按阶段执行。
>
> 最后更新：2026-08-20
>
> 范围：`ComfyUI-XYUE-H3-Studio`、Studio UI、聚合执行链、纯净包同步。

## 1. 目标

将 XYUE 从“读取固定工作流模板再打补丁”的聚合方式，重构为以 Studio 项目配置为唯一来源、按本次运行动态生成执行图的 H3 工作台。

最终用户流程：

```text
打开 XYUE H3 Studio
→ 创建或打开项目
→ 添加 1-5 个镜头
→ 配置当前镜头
→ 选择要运行的镜头
→ 只执行当前镜头
→ 复用已有镜头结果
→ 按轨道相邻关系决定尾帧 / Motion Context
→ 按保存策略写入项目文件夹
```

## 2. 已确认的设计原则

### 2.1 不再使用运行时模板

以下 JSON 不再作为聚合节点的运行时来源：

```text
workflows/XYUE_H3_多段循环工作流.json
workflows/XYUE_H3_全程多参考短剧工作流.json
```

它们最多只能作为用户主动导出的示例或历史参考，不能决定当前执行图的节点端口、参数顺序或阶段数量。

运行时必须改为：

```text
StudioConfig
→ ExecutionGraphBuilder
→ 当前运行所需的节点和连线
→ ComfyUI /prompt
```

### 2.2 每个镜头都是独立单元

项目只是管理 1-5 个镜头，不存在“单镜项目”和“多镜项目”两种模式，也不因为项目里只有一个镜头就改变执行语义。

统一使用：

```text
当前项目
镜头 01
镜头 02
镜头 03
```

镜头数量只决定当前项目里有多少个可管理的镜头，不决定哪些镜头必须一起执行。每个镜头都可以单独生成、重试、保存、替换和参与最终合成。

### 2.3 每个镜头独立运行

默认运行目标是底部轨道当前选中的镜头，而不是从第一镜跑到最后一镜。

```text
已完成：镜头 01、镜头 02
当前选中：镜头 03
点击运行：只生成镜头 03
```

历史视频、报告和种子必须保留，不得因为运行新镜头而清空其他镜头。

### 2.4 衔接只看轨道相邻关系

对当前镜头 `N`：

- `独立切镜`：不读取轨道前一个镜头；
- `尾帧续接`：读取轨道中当前镜头前一个镜头的视频尾帧；
- `动作音频续接`：读取轨道中当前镜头前一个镜头的视频和音频，通过 Motion Context 携带连续动作。

阶段 ID 不是衔接来源。用户拖动轨道后，前一个轨道项才是实际前镜头。

### 2.5 第三方能力只调用，不内嵌

XYUE 不复制第三方插件源码和权重，只通过 ComfyUI 节点映射或适配器调用：

| 能力 | 来源 | XYUE 责任 |
| --- | --- | --- |
| H3 生成 | ComfyUI H3 核心 | 组装参数和条件 |
| LoRA | ComfyUI 核心 `LoraLoaderModelOnly` | 阶段开关、文件和强度 |
| Kitchen Attention | ComfyUI 核心 `ModelAttentionBackend` | 后端选择 |
| latent 放大 | `Comfyui_Minimax_h3_latent_Upscaler` | 调用和尺寸参数 |
| 条件同步 | 同一 latent upscaler 插件 | 二次采样前同步 positive/negative |
| Motion Context | `ComfyUI-H3-Motion-Context` | 传递前镜视频/音频 |
| Patch Sol-Attn | `ComfyUI-SolAttn_triton` | 可选注意力后端 |
| 实时预览 | `ComfyUI-KJNodes` | 中间帧 / WebP / MP4 |
| 保存、素材、拼接、项目管理 | XYUE 自有代码 | 全部由 Studio 管理 |

## 3. 当前已经完成的部分

以下内容已经落地并通过基础检查：

- latent 放大倍率限制为一位小数；
- Sigma 双段链路和放大后 conditioning 同步；
- LoRA 开关、LoRA 模型、LoRA 强度；
- `MiniMax H3 Kitchen Attention` / `Patch Sol-Attn` 两种模式；
- 基础视频步数、基础音频步数、Sigma 精修步数、降噪程度控件；
- 默认采样值：视频 4、音频 4、Sigma 3、降噪 0.30；
- Motion Context 改为从轨道前一个已保存视频获取；
- 中间预览帧和动画预览通道；
- Studio 独立地址 `/xyue-h3/studio/` 和快捷地址 `/xyue-h3`；
- Prompt 高亮层 ResizeObserver 和全屏快速引用定位；
- 旧会话中 NaN 参数自动归一化；
- MP 分辨率标签重复前缀自动归一化；
- 运行当前镜头、保留其他已生成镜头的第一版执行逻辑；
- 自动下一镜和自动合成默认为关闭；
- 当前镜头重试按钮和随机 / 沿用种子选项第一版；
- 两个工作流 JSON 的控件顺序和当前 schema 已重新构建；
- 纯净包已同步当前插件和 Studio 资源。

## 4. 目标配置模型

计划使用新的配置 schema：

```json
{
  "schema": "xyue-h3/studio-config-v3",
  "project": {
    "name": "三女高光舞台",
    "shot_count": 3
  },
  "shots": [
    {
      "index": 1,
      "name": "开场",
      "prompt": "...",
      "generation_mode": "多参考模式",
      "transition": "cut",
      "resolution": "0.4MP|480p（864×480）",
      "video_steps": 4,
      "audio_steps": 4,
      "sigma_steps": 3,
      "denoise": 0.3,
      "upscale_factor": 1.5,
      "lora": {
        "enabled": true,
        "name": "minimax_h3/...safetensors",
        "strength": 1.0
      },
      "attention_mode": "MiniMax H3 Kitchen Attention",
      "seed": 123,
      "seed_mode": "reuse",
      "materials": []
    }
  ],
  "execution": {
    "target_shot": 3,
    "execution_shots": [3],
    "resume_previous": true
  },
  "save_policy": {
    "project_folder": "xyue_h3/三女高光舞台",
    "stage_pattern": "{name}_{index:02d}",
    "final_pattern": "{name}_最终",
    "collision": "increment",
    "save_stage_videos": true,
    "save_final_video": true,
    "save_report": true
  },
  "composition": {
    "enabled": false,
    "clips": []
  }
}
```

### 4.1 配置约束

- `shot_count` 为当前项目镜头总数，范围 1-5；
- `execution.target_shot` 是本次点击运行的目标镜头；
- `execution.execution_shots` 是本次实际加入执行图的镜头；
- `cut` 只加入目标镜头；
- `tail` / `motion` 至少加入“前一个轨道镜头 + 当前镜头”；
- 既有镜头的 `video`、`report`、`seed` 和保存路径不能因新任务被清空；
- 执行图中没有加入的镜头不应加载模型，也不应触发生成器。

## 5. 动态执行图重构

### 5.1 新模块

新增或拆分：

```text
core/studio_config.py
core/execution_graph.py
core/model_pipeline.py
core/save_policy.py
core/stage_execution.py
```

### 5.2 动态节点组

每次执行按目标镜头生成：

```text
项目级：
  素材读取
  项目控制
  输出设置

镜头级：
  H3 模型选择
  LoRA
  注意力后端
  H3 条件
  基础 Sigma
  Sigma 精修
  第一次采样
  latent 放大
  conditioning sync
  第二次采样
  解码
  阶段保存

衔接级：
  尾帧提取
  Motion Context
  前镜检查点读取

输出级：
  当前镜头预览
  可选合成
  报告
```

### 5.3 移除模板加载

待删除：

```text
load_workflow()
configure_workflow()
_remove_multi_stage_config()
_wire_stage_models() 对模板节点的依赖
_normalize_model_pipeline() 对模板节点的依赖
```

`/xyue-h3/aggregate/preview` 改为返回动态构建结果。

### 5.4 导出当前执行图

Studio 提供：

```text
导出本次执行图 JSON
```

导出内容必须是本次真实目标镜头，不再导出固定五阶段模板。

## 6. 当前镜头独立执行规则

### 6.1 当前镜头执行

每个镜头都是独立可运行单元。项目中的镜头数量只表示当前项目管理的镜头数，不表示执行模式。

独立切镜不要求轨道前面存在已生成视频；只有选择尾帧续接或动作音频续接时，才要求轨道前一个镜头已经生成并可读取。

按钮文案：

```text
未生成：生成当前镜头
已有视频：重新生成当前镜头
```

执行时：

- 只清空当前镜头的运行状态；
- 其他镜头的视频和报告保留；
- 其他镜头不重新加载模型；
- 当前镜头失败不影响前面已经保存的镜头。

### 6.2 尾帧衔接

```text
轨道前一个镜头的视频
→ 尾帧提取
→ 当前镜头首帧或 Ref2VA 参考
```

### 6.3 Motion Context

```text
轨道前一个镜头的阶段保存视频
→ VIDEO 输入
→ Motion Context 适配器
→ 携带连续画面和原声音频
→ 当前镜头
```

不得再把当前镜头前一个生成器的半成品 latent 作为 Motion Context 来源。

## 7. 保存和命名系统

### 7.1 Studio 设置

新增“保存与命名”二级页面：

```text
项目名称
项目输出文件夹
阶段文件命名方式
最终文件命名方式
重名策略
保存阶段视频
保存最终视频
保存报告 JSON
```

### 7.2 默认目录

```text
ComfyUI/output/xyue_h3/<项目名称>/
```

### 7.3 默认文件

```text
三女高光舞台_01.mp4
三女高光舞台_02.mp4
三女高光舞台_最终.mp4
三女高光舞台_报告.json
```

### 7.4 命名模式

```text
名称+编号
名称+阶段名
名称+时间戳
自定义模板
```

模板变量：

```text
{name}
{index}
{stage}
{date}
{time}
{seed}
```

### 7.5 安全和重名

- 所有路径限制在 `ComfyUI/output` 内；
- 项目名称和阶段名称做文件名安全清理；
- 默认重名策略为自动递增；
- 保存报告记录实际完整路径、种子、模型、LoRA、注意力和采样参数。

## 8. UI 任务

### 8.1 Studio 顶部

- 显示项目名称；
- 显示“当前项目”，不区分单镜 / 多镜模式；
- 显示当前目标镜头；
- 显示本次执行是否只跑当前镜头；
- 显示保存目录和命名预览。

### 8.2 底部轨道

- 镜头可拖动排序；
- 排序后前一个镜头关系立即更新；
- 已生成镜头保留绿色完成标记；
- 当前目标镜头有明确高亮；
- “重新生成当前镜头”不影响其他镜头；
- 阶段数量动态显示，不写死“五段”。

### 8.3 提示词区域

- 监听 iframe 和检查器尺寸；
- 高亮层与 textarea 使用同一字体和几何尺寸；
- 全屏时快速引用列表挂到当前 document 根节点；
- `@` 和 `<` 都支持；
- 快速列表不阻塞文本框输入和框选。

### 8.4 自动开关

默认关闭：

```text
完成后自动下一镜：关闭
生成后自动合成：关闭
```

用户手动开启后才改变行为。

## 9. 节点清理

### 9.1 待从公开节点列表移除

```text
XYUE_H3_AggregateWorkflow（保留为 XYUE H3 Studio 入口）
XYUE_H3_MultiStageConfig
XYUE_H3_StudioController
XYUE_H3_StageGenerationProfile
XYUE_H3_PromptEditor
XYUE_H3_PromptEnhancer
XYUE_H3_PromptOutput
XYUE_H3_GlobalLoRAManager
XYUE_H3_GlobalAccelerationManager
XYUE_H3_AccelerationController
XYUE_H3_VideoBoard
XYUE_H3_VideoConcat
```

### 9.2 素材节点清理条件

以下节点在 Studio 可以直接读取 input/output 素材和项目素材库后再移除：

```text
XYUE_H3_ImageAsset
XYUE_H3_VideoAsset
XYUE_H3_AudioAsset
XYUE_H3_ImageManager
XYUE_H3_VideoManager
XYUE_H3_AudioManager
XYUE_H3_MaterialManager
```

### 9.3 保留为内部服务的能力

删除 UI 节点不等于删除底层能力。以下代码需要保留为内部模块：

```text
H3 采样
latent 放大适配
条件同步适配
Motion Context 适配
素材解析
阶段保存
视频拼接
项目报告
```

## 10. 第三方依赖和缺失提示

Studio 启动和运行前检查：

```text
ComfyUI H3 核心
Comfyui_Minimax_h3_latent_Upscaler
ComfyUI-H3-Motion-Context
ComfyUI-SolAttn_triton（选择 Sol-Attn 时必需）
ComfyUI-KJNodes（中间动画预览）
latent_upscale_models 中的 H3 权重
loras 中的所选 LoRA
```

缺失时显示：

```text
依赖名称
用途
安装位置
GitHub / Hugging Face 链接
当前是否阻断本次执行
```

## 11. 验证计划

### 11.1 配置和执行图

- 独立 cut 执行图只有一个生成镜头；
- 选中镜头 03 时，cut 只提交镜头 03；
- tail / motion 提交前一个镜头和当前镜头；
- 已生成前镜通过检查点复用；
- 未加入执行图的镜头不加载模型；
- 节点和链接都来自当前 ComfyUI schema；
- 不再出现固定模板端口错误。

### 11.2 参数

- 分辨率标签重复输入自动归一化；
- 视频步数默认 4；
- 音频步数默认 4；
- Sigma 默认 3；
- 降噪默认 0.30；
- 放大倍率只允许一位小数；
- LoRA 开关关闭时不调用 LoRA；
- Kitchen / Sol-Attn 选择真实改变模型后端。

### 11.3 重试

- 已生成镜头显示“重新生成当前镜头”；
- 沿用种子能复现；
- 随机种子生成新 seed；
- 重试不删除其他镜头文件。

### 11.4 保存

- 项目目录和阶段编号正确；
- 中文名称安全处理；
- 重名自动递增；
- 阶段视频、最终视频、报告内容一致。

### 11.5 UI

- 窗口大小变化后提示词区域无空白；
- 高亮与文本位置一致；
- 全屏可以打开 `@` / `<` 快速列表；
- 中间预览可显示图片、WebP 或 MP4；
- 自动下一镜和自动合成初始为关闭。

## 12. 交付顺序

1. 修复当前分辨率归一化、控件索引和参数验证；
2. 完成当前镜头目标执行和历史镜头复用；
3. 完成轨道前镜尾帧 / Motion Context 解析；
4. 完成重试种子策略；
5. 完成保存策略和项目文件夹；
6. 完成动态执行图构建器；
7. 移除运行时模板加载；
8. 移除重复公共节点；
9. 更新依赖检测、README、纯净包和 GitHub 工作区；
10. 完成全量回归和干净环境验证。

## 13. 非目标

本计划不包含：

- 复制第三方插件源码到 XYUE；
- 复制第三方模型权重到 XYUE；
- 修改 ComfyUI 核心 H3 sampler 以实现真正独立的视频 / 音频采样次数；
- 保留旧模板和旧配置的长期兼容层；
- 在插件外部目录中搜索与挑战无关的用户文件。
