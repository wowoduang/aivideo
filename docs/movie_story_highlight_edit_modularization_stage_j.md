# Stage-J：粗剪编排主链选择器迁移收口

## 背景

Stage-H / Stage-I 已经把 `subtitle_first_pipeline.py` 中的旧影视解说链路大部分迁入 `app/services/movie_story/*`，旧入口已退化为兼容编排器。但 `highlight_edit_pipeline.py` 仍然保留大量高光选择、窗口扩展、去重合并和人物锚点逻辑，导致“影视解说主链”和“粗剪编排主链”仍然存在能力分裂。

本阶段目标不是重写高光算法，而是把已经稳定的粗剪选择器逻辑迁入 `movie_story` 能力层，使未来统一剪辑总线能够复用同一套 movie-story selection runtime。

## 本阶段新增模块

### `app/services/movie_story/highlight_edit_selection.py`

职责：

1. 构建 highlight recut selection pool。
2. 保留 score pick / diverse pick / coverage anchor / raw audio anchor / scene anchor / opening anchor / ending anchor / climax anchor / chronology anchor。
3. 保留 peak window 逻辑：subtitle boundary snap、plot boundary snap、dialogue cycle、text completeness、main character window、payoff window。
4. 保留 clip 去重合并逻辑：按 clip id 和时间重叠合并，并保留更具体的 scene 元数据、raw audio 标记、人物、keyframes、selection reasons。
5. 暴露公共函数：
   - `build_highlight_recut_selection_pool`
   - `merge_unique_clips`
   - `clip_overlap_ratio`
   - `detect_main_character_reference`

## 旧文件变化

### `app/services/highlight_edit_pipeline.py`

变化：

- 原文件约 2651 行。
- Stage-J 后约 1484 行。
- 高光 recut selection pool 及其大部分内部辅助函数已迁入 `movie_story/highlight_edit_selection.py`。
- 旧私有函数名仍保留为兼容 shim，例如：
  - `_build_highlight_recut_selection_pool`
  - `_merge_unique_clips`
  - `_clip_overlap_ratio`
  - `_detect_main_character_reference`

保留 shim 的原因：

1. 不破坏现有测试。
2. 不破坏已有内部导入或调试脚本。
3. 允许下一阶段继续将 `highlight_edit_pipeline.py` 降级为更薄的统一剪辑编排器。

## 为什么这是迁移而不是简单搬函数

本阶段把粗剪主链中最复杂、最稳定、最容易复用的选择策略迁入 `movie_story`，原因是：

- 选择器不应该绑定具体 pipeline。
- `movie_story` 已经是新影视解说能力层。
- 未来 `subtitle_first_pipeline.py`、`highlight_edit_pipeline.py`、外部解说剪辑模式都应该共享同一套高光选择和去重合并能力。
- 这样可以避免“movie-story 一套选择，高光剪辑另一套选择”的长期分裂。

## 当前主链定位

当前阶段后，主链定位如下：

```text
movie_story/*
  影视解说 / 剧情理解 / 高光选择 / 解说生成 / 最终门禁能力层

subtitle_first_pipeline.py
  旧字幕优先影视解说兼容入口，继续变薄

highlight_edit_pipeline.py
  未来统一剪辑总线入口，继续变薄

highlight_edit_selection.py
  粗剪高光选择器 runtime，供 highlight_edit 和未来 movie-story composition bridge 复用
```

## 测试覆盖

新增：

- `tests/test_movie_story_highlight_edit_selection.py`

保留并通过：

- `tests/test_highlight_edit_pipeline.py`
- `tests/test_composition_plan_adapter.py`

验证重点：

1. selection pool 的 opening / raw audio / character anchor 保留。
2. merge unique clips 保留更具体 scene metadata。
3. 原 highlight edit pipeline 的 selection pool 行为不变。
4. CompositionPlan adapter 行为不变。

## 下一阶段建议

Stage-K 建议继续迁出 `highlight_edit_pipeline.py` 中剩余的三块：

1. `highlight_edit_candidates.py`：迁出 plot candidate / scene candidate 构建逻辑。
2. `highlight_edit_composition.py`：迁出 CompositionPlan 构建、group shot duration、audio plan。
3. `movie_story_composition_bridge.py`：把 `movie_story` 的 selected highlights / narration evidence 转成统一 `CompositionPlan`，让 `subtitle_first_pipeline.py` 最终也能输出或复用 CompositionPlan。
