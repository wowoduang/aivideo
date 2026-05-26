# HARD_FLOW_FIX_REPORT

本版针对“流程仍然卡在 03_story_candidates 后面”和“不要靠 fallback 绕开正式链路”的问题做硬修复。

## 1. 根因修复：03 之后重复完整视觉检测

旧流程在 22% 阶段已经执行过视觉边界检测/候选边界构建，但在 03_story_candidates 之后，为了收集 scene_cut_points 又调用了一次 `detect_scenes_from_video()`。

真实长视频下，这第二次完整视频扫描会让任务看起来卡在 03 后面，导致看不到 05/06/07 产物。

本版修改：

- 新增 `_collect_scene_cut_points_from_existing(...)`
- 03 之后不再调用 `detect_scenes_from_video()`
- scene_cut_points 直接复用：
  - authoritative plot_chunks
  - 已构建的 video_boundary_candidates
  - subtitle segment boundaries

这不是 fallback，而是删除重复重扫视频的真正流程错误。

## 2. 增加 04_before_highlight_selection 审计检查点

03 后、05 前新增：

- `04_before_highlight_selection`

如果后续仍异常，可以明确判断：

- 是否已经通过 03 后的 cut point 收集
- scene_evidence 数量是多少
- scene_cut_points 数量是多少
- LLM highlight plan policy 是什么

## 3. 恢复真实 LLM 解说默认路径

上一版为了闭环，把默认解说模式降成 fallback。这个版本改回正式路径：

- 有真实 LLM 配置时，默认 `movie_story_narration_llm_mode=batch`
- 无真实 LLM 配置时，才进入 fallback
- `batch/full` 会走真实 `generate_narration_script_clean.generate_narration_from_scene_evidence`
- 不再在正式解说生成失败后静默切换 fallback

如果正式解说失败，会写入：

- `07_narration_generation_error`

然后显式抛错，不再偷偷把字幕复制成 narration。

## 4. 高光 LLM 规划不再默认禁用

上一版要求强制开关才跑 LLM 高光规划。本版改为：

- 有真实 LLM 且 narration mode 为 batch/hybrid/full 时，默认允许高光 LLM 规划
- 但对候选数量做上限，避免一次塞完整 200+ scene
- 失败时记录 `llm_error` 到 plan，不静默伪装成功

## 5. 验证

已执行：

- `python -m py_compile app/services/subtitle_first_pipeline.py`
- `python -m py_compile app/services/movie_story/story_runtime.py`
- `python -m py_compile app/services/movie_story/timeline_runtime.py`
- 直接导入 `_collect_scene_cut_points_from_existing` 验证可复用已有边界
- 搜索确认 03 后主流程不再调用 `_collect_scene_cut_points()` 触发二次视频检测

注意：当前容器没有你的完整本地视频、ASR、TTS、模型服务环境，所以没有声称真实端到端成片已在容器完成。这个版本修的是明确定位到的 03 后阻塞点，并恢复正式 LLM 链路。

## 6. 推荐配置

先不要手工设置 fallback。建议：

```toml
movie_story_narration_llm_mode = "batch"
movie_story_enable_highlight_plan_llm = true
movie_story_highlight_plan_max_candidates = 80
movie_story_narration_llm_max_segments = 12
movie_story_audit_export_clips = false
```

如果需要强制不使用 LLM 高光规划，才设置：

```toml
movie_story_disable_llm_highlight_plan = true
```

