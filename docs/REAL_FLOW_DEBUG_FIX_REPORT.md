# Real Flow Debug Fix Report

本次修复目标：不再用“卡住就回退”的方式绕开问题，而是让正式高光选择、正式解说生成链路具备可诊断、可复现、可继续修的工程闭环。

## 1. 03 后新增细粒度审计检查点

`subtitle_first_pipeline.py` 在 `03_story_candidates` 后新增正式阶段 before/after/error 标记：

- `04a_llm_highlight_plan_before/after/error`
- `04b_apply_highlight_plan_before/after/error`
- `04c_select_final_story_evidence_before/after/error`
- `04d_collect_existing_scene_cut_points_before/after/error`
- `04e_extract_story_highlights_before/after/error`
- `05a_extract_highlight_frames_before/after/error`
- `05b_build_highlight_narration_evidence_before/after/error`
- `07a_generate_narration_before/after/error`
- `07_narration_generation_error`
- `07_narration_script_raw`

以后如果流程再次停住，看最后一个 `*_before` 目录即可确认具体卡在哪个函数，而不是只看到 03。

## 2. 修复重启任务产物混写问题

`local_job_runner.py` 现在给每个 movie_story_script 任务设置任务级输出路径：

```text
task_dir/<task_id>/movie_story_script.json
```

这样用户第一次运行后停止，再点“重新开始”，新旧线程不会再共用视频 hash 默认脚本路径，也不会把 audit 产物混到同一个目录里。

## 3. 前端/接口高级参数不再丢失

`local_job_runner.py` 新增 `_movie_story_scene_overrides_from_request()`，透传以下高级控制项：

- `movie_story_narration_llm_mode`
- `movie_story_narration_llm_max_segments`
- `movie_story_enable_global_llm`
- `movie_story_enable_segment_llm`
- `movie_story_enable_story_validation_llm`
- `movie_story_enable_highlight_plan_llm`
- `movie_story_enable_narration_validation_llm`
- `movie_story_highlight_plan_max_candidates`
- `movie_story_typed_selector_error_policy`
- audit 相关配置
- 边界和时间匹配配置

## 4. LLM 高光规划仍走正式链路，但做有界压缩

`_safe_plan_story_highlights()` 不再把完整超长剧情对象直接塞给高光 LLM。

现在会：

1. 根据 story score / importance / LLM window / raw voice 等信号排序候选；
2. 默认只取最多 32 个高价值候选进入 LLM 高光规划；
3. 压缩 `global_summary` 和 `full_subtitle_understanding`，只保留高光规划必需字段；
4. typed selector 仍然接收完整证据，不因 LLM prompt 压缩而丢片段。

这不是绕开 LLM，而是避免 03 后被超长 prompt 或无界候选拖死。

## 5. 修复“plot_function 有信息但文本为空时选不出高光”的硬问题

根据用户上传的审计包，`03_story_candidates/manifest.json` 里存在 79 条候选，但很多 `text` 为空，只剩 `plot_function`。

旧 typed classifier 要求必须有文本 snippet，导致这类候选无法形成 typed highlight。

本次修复 `highlight_typing.py`：

- `plot_function` 命中现在视为上游结构化证据；
- 即使字幕文本为空，也可凭 `plot_function=信息揭露/冲突升级/...` 形成 typed candidate；
- replay 用户审计包中的 79 条 03 候选，已能选出 20 条高光。

## 6. typed selector 默认不再偷偷 fallback

`story_runtime.py` 中 typed highlight selector 如果异常，默认抛错并写入 04e error 检查点。

只有显式配置：

```toml
movie_story_typed_selector_error_policy = "fallback"
```

才会使用 score fallback。

## 7. LiteLLM async 调用增加 timeout 约束

`llm_text_completion.py` 的 LiteLLM async 路径现在也会按 `timeout` 执行 `asyncio.wait_for()`，不再只有 requests 路径有超时。

## 8. 验证结果

已执行：

```text
python3 -m compileall -q app/services app/api app/utils
pytest -q tests/test_generate_narration_script.py tests/test_plot_understanding.py tests/test_movie_story_flow_debug_fix.py
```

结果：

```text
10 passed
```

额外验证：

- 最小 SRT + `visual_mode=off` + 无 LLM 配置，流程成功到 `07_narration_script`；
- 审计目录包含新增 before/after 检查点；
- 用户上传的 `03_story_candidates` manifest replay：79 条候选 -> 20 条 selected highlights。

## 9. 下一次如果仍卡住，如何定位

看 audit run 目录中最后一个阶段：

- 有 `04a_llm_highlight_plan_before` 没有 after：卡在高光 LLM 规划；
- 有 `04e_extract_story_highlights_before` 没有 after：卡在 typed selector；
- 有 `06_scene_evidence_for_narration` 和 `07a_generate_narration_before` 没有 after：卡在正式解说生成；
- 有 `07a_generate_narration_error` 或 `07_narration_generation_error`：打开 manifest.json 看错误详情。

这版的目的不是掩盖失败，而是把失败定位到具体函数，继续硬修。
