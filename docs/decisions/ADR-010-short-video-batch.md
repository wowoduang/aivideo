# ADR-010: 长视频拆多短视频独立链路

**日期**：2026-05-28  
**状态**：Active

## 背景

aivideo 已有 `two_round` / `two_round_visual` 单条影视解说链路，也已有 highlight 相关产物。
但“长视频拆成多个精彩短视频”是独立产品形态：一部长视频需要产出 N 条独立短视频，每条都有自己的标题、主题/情绪句、时间线、后续文案、配音、字幕和成片路径。

当前产品决策：第一阶段先不生成完整解说文案。每条短视频只需要：
- 一个标题
- 一句主题或一句 emo
- 对应原片时间段

## 命名修正

正式代码中不使用 `highlight-like segments` 这种模糊命名。

当前输入统一叫：

```text
source_segments
```

含义是“可以作为短视频候选来源的时间段行”。它的生产者可以是：
- 现有 movie_story highlight artifact
- 用户手动选择的时间段
- 未来 scene/event detector
- 未来批量短视频候选召回器

highlight 只是可能的来源之一，不是这个新链路的正式输入概念。

## 决策

新增独立包：

```text
app/services/movie_story/short_video_batch/
```

MVP 先从 `source_segments` 召回候选，生成：

```text
short_video_candidates.json
short_video_plans.json
```

其中 `short_video_plans.json` 只包含 `title` 和 `theme_or_emo_line`，不包含 `narration` 或 `script`。

## 后续

后续再接：
- 现有 movie_story highlight artifact -> source_segments 的读取适配器
- 可选 LLM 一句话主题/emo 改写
- 每条 short 独立文案
- composition plan
- batch render/export
- 前端 `/projects/:id/shorts`

## 约束

- 不每条 short 重新跑完整 `two_round_visual`
- 不把 `visual_focus_segments` 当最终剪辑片段
- 当前阶段不生成完整解说文案
- 不新增 legacy/native fallback
- 不把 prompt/response/debug/frame 打进用户下载包
- 不继续往超大旧文件里塞新链路

## Round74: 显式 artifact 适配器

新增 `source_segment_adapter.py`，只接受一个显式传入的 movie_story artifact JSON 文件，将其转换为 `source_segments`。

支持的输入根结构：
- list
- dict.items
- dict.segments
- dict.highlights
- dict.script_segments
- dict.narration_segments

该适配器不扫描任务目录，不自动猜测使用哪个文件。API 层或工具层必须明确传入 artifact 文件路径，避免隐式 fallback。

新增手动验证工具：

```text
tools/build_short_video_batch_from_movie_story_artifact.py
```

该工具只生成：

```text
short_video_candidates.json
short_video_plans.json
```

不生成完整解说、不配音、不合成视频。

