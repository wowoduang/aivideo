# Stage-K：粗剪候选构建与 CompositionPlan 迁入 movie_story

## 目标

Stage-J 已经把 `highlight_edit_pipeline.py` 里的粗剪选择器迁入 `movie_story.highlight_edit_selection`。Stage-K 继续收口剩余粗剪主链，把候选构建和合成计划构建拆出，让 `highlight_edit_pipeline.py` 进一步退化为编排器。

本轮交付为补丁包形式，适用于 Stage-J 版本源码。

## 新增模块

### `app/services/movie_story/highlight_edit_candidates.py`

职责：

- plot chunks → candidate clips
- scene segments → scene refined candidates
- scene 与 plot chunk 的最佳父块匹配
- scene 内字幕 speaker / turn / exchange 信号提取
- boundary candidates 挂载
- candidate stats 汇总
- narrated mode candidate pool 构建
- narration matches → clips 收集

该模块是纯逻辑模块：不做文件 I/O，不调用 LLM，不写进度。

### `app/services/movie_story/highlight_edit_composition.py`

职责：

- planned clips / narration matches → CompositionPlan dict
- narrated group shot 展开
- intra-scene subshots 切分
- narration 文本按 shot 拆分
- group shot duration planning
- raw / ducked_raw / tts audio plan 决策
- timeline cursor 分配

该模块同样保持纯逻辑，便于后续把 `highlight_edit_pipeline.py` 替换成更薄的 edit bus。

## `highlight_edit_pipeline.py` 变化

本轮把以下原内部函数迁出：

- `_build_candidate_clips`
- `_build_scene_candidates`
- `_build_candidate_stats`
- `_build_narrated_clip_pool`
- `_collect_matched_clips`
- `_build_composition_plan`
- `_plan_group_shot_durations`
- `_decide_group_audio_plan`
- 以及相关 scene/candidate/composition helper

旧函数名仍作为 compatibility alias 保留，确保既有测试和旧 import 不断。

## 结果

- `highlight_edit_pipeline.py`：约 1484 行 → 约 739 行
- 新增候选构建 runtime：`highlight_edit_candidates.py`
- 新增合成计划 runtime：`highlight_edit_composition.py`
- 修复了 narrated pool 里潜在的 `_select_diverse_clips` 未定义风险，改由 `movie_story.highlight_edit_selection` runtime 统一提供。

## 验证

已执行：

```bash
python -m compileall -q app/services/highlight_edit_pipeline.py \
  app/services/movie_story/highlight_edit_candidates.py \
  app/services/movie_story/highlight_edit_composition.py

pytest -q \
  tests/test_highlight_edit_pipeline.py \
  tests/test_movie_story_highlight_edit_selection.py \
  tests/test_movie_story_highlight_edit_candidates.py \
  tests/test_movie_story_highlight_edit_composition.py \
  tests/test_composition_plan_adapter.py

pytest -q \
  tests/test_subtitle_first_pipeline_prologue.py \
  tests/test_movie_story_narration_finalize.py \
  tests/test_movie_story_migration_stage_a.py \
  tests/test_movie_story_migration_stage_b.py \
  tests/test_movie_story_migration_stage_c.py \
  tests/test_movie_story_migration_stage_d.py \
  tests/test_generate_narration_script_clean.py \
  tests/test_highlight_selector.py \
  tests/test_highlight_timeline_planner.py \
  tests/test_movie_story_flow_debug_fix.py \
  tests/test_highlight_edit_pipeline.py \
  tests/test_movie_story_highlight_edit_selection.py \
  tests/test_movie_story_highlight_edit_candidates.py \
  tests/test_movie_story_highlight_edit_composition.py \
  tests/test_composition_plan_adapter.py
```

结果：`64 passed`。

## 下一轮建议

Stage-L 建议继续拆：

1. `highlight_edit_signals.py`：字幕、视觉边界、scene、plot chunks 构建和 audio/profile annotation。
2. `highlight_edit_runtime.py`：把 `_run` 中 narrated/highlight 两条分支收成可测试 runtime。
3. `movie_story_composition_bridge.py`：把 movie-story selected highlights / narration evidence 转成统一 CompositionPlan，让解说链路和粗剪链路最终共用输出契约。
