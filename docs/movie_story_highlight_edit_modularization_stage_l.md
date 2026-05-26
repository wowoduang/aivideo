# Stage-L：粗剪运行上下文与输出写盘迁入 `movie_story`

## 背景

Stage-J / Stage-K 已经将 `highlight_edit_pipeline.py` 中最重的粗剪选择器、候选构建和 `CompositionPlan` 生成逻辑迁入 `app/services/movie_story/`。Stage-K 后，旧 pipeline 仍然残留几类胶水逻辑：

- 视觉信号模式配置：`off` / `auto` / `boost`。
- 可选 AI 高光选择与解说匹配适配。
- 高光 profile 能力探测、解析和候选加权。
- 音频信号上下文构建与候选注入。
- 输出文件写盘和返回结构拼装。

这些逻辑不应长期留在 `highlight_edit_pipeline.py`，否则粗剪主链仍然会继续膨胀。

## 本轮新增模块

### `app/services/movie_story/highlight_edit_context.py`

负责粗剪运行上下文和外部可选能力适配：

- `resolve_visual_signal_config`：统一视觉模式配置。
- `try_ai_highlight_selection`：可选 AI 高光选择适配，失败降级为空选择。
- `try_ai_narration_matching`：可选 AI 解说匹配适配，失败降级为空匹配。
- `select_clips_by_ids`：按 AI 返回 id 选片并标注 `ai_selected` / `raw_audio_keep`。
- `refresh_narration_matches_from_planned`：时间线规划后刷新解说匹配片段。
- `selection_duration`：选择结果总时长统计。
- `detect_highlight_capabilities` / `resolve_highlight_profile_context` / `apply_highlight_profile_context`：profile 能力、解析和应用。
- `build_shared_audio_signal_context` / `annotate_audio_signal_context`：音频信号上下文构建和候选打分。

模块原则：

- 不做文件写盘。
- 不构建候选片段。
- 不生成 `CompositionPlan`。
- 所有可选依赖均包在函数内部，失败时返回可继续运行的安全 fallback。

### `app/services/movie_story/highlight_edit_outputs.py`

负责粗剪输出与响应结构：

- `write_outputs`：保存 `CompositionPlan` 和 script items。
- `build_success_response`：组装稳定的成功返回结构。
- `build_error_response`：组装稳定的错误返回结构。

模块原则：

- 只处理文件输出与公开 response shape。
- 不做候选选择、AI 调用、音频分析或合成计划生成。

## `highlight_edit_pipeline.py` 新定位

Stage-L 后，`highlight_edit_pipeline.py` 继续保留公开入口：

```python
run_highlight_edit_pipeline(...)
```

但它的职责进一步收窄为：

1. 参数校验。
2. 调用字幕 / 场景 / plot chunk 基础服务。
3. 调用 `movie_story.highlight_edit_candidates` 构建候选。
4. 调用 `movie_story.highlight_edit_context` 注入运行上下文、profile、音频、AI 结果。
5. 调用 `movie_story.highlight_edit_selection` 做多池选择。
6. 调用 `highlight_timeline_planner` 做时间线规划。
7. 调用 `movie_story.highlight_edit_composition` 生成 `CompositionPlan`。
8. 调用 `movie_story.highlight_edit_outputs` 写盘和组装返回值。

## 文件瘦身

```text
highlight_edit_pipeline.py
约 737 行 → 约 462 行
```

## 兼容策略

保留旧私有函数名作为 compatibility alias：

- `_resolve_visual_signal_config`
- `_try_ai_highlight_selection`
- `_try_ai_narration_matching`
- `_select_clips_by_ids`
- `_refresh_narration_matches_from_planned`
- `_selection_duration`
- `_detect_highlight_capabilities`
- `_resolve_highlight_profile_context`
- `_apply_highlight_profile_context`
- `_annotate_audio_signal_context`
- `_write_outputs`

这样旧测试和旧内部调用不会因为模块化迁移而断掉。

## 验证

本轮新增测试：

- `tests/test_movie_story_highlight_edit_context_outputs.py`

验证点：

- 视觉模式 fallback。
- AI 选片 id 映射和 raw audio 标记。
- planned clip 刷新 narration match。
- 输出文件写盘。
- 成功响应结构稳定。

已验证测试集合：

```text
26 passed:
- test_highlight_edit_pipeline.py
- test_movie_story_highlight_edit_selection.py
- test_movie_story_highlight_edit_candidates.py
- test_movie_story_highlight_edit_composition.py
- test_movie_story_highlight_edit_context_outputs.py
- test_composition_plan_adapter.py

43 passed:
- subtitle_first / movie_story A-D/H / generate_narration / selector / timeline 回归
```

## 后续建议

下一轮 Stage-M 不应继续拆 `highlight_edit_pipeline.py` 内部小函数，而应开始做桥接收口：

1. `movie_story_composition_bridge.py`：把 movie-story selected highlights / narration evidence 转为统一 `CompositionPlan`。
2. 让 `/movie-story-script` 和 `/highlight-script` 输出逐步统一到 `CompositionPlan`。
3. 把 `subtitle_first_pipeline.py` 的最终脚本输出和 `highlight_edit_pipeline.py` 的合成计划输出做同构适配。
