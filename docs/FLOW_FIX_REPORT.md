# FLOW COMPLETE FIX REPORT

本补丁针对“流程只跑到 02_scene_candidates，后续没有 03/05/07”的问题做闭环修复。

## 修复重点

1. `subtitle_first_pipeline.py` 不再因为缺少 LLM 配置直接中断。
   - 无有效 `text_api_key/text_model` 时自动进入本地 fallback 模式。
   - 示例/占位密钥会被识别为无效密钥。

2. 新增解说生成模式：
   - `fallback`：不调用 LLM，保证流程跑完。
   - `hybrid`：有 LLM 时默认混合模式，只对有限高光段调用 LLM。
   - `full`：全量 LLM 模式，质量更高但耗时更长。

3. 默认关闭耗时逐段 LLM：
   - `movie_story_enable_segment_llm=false`
   - `movie_story_enable_story_validation_llm=false`
   - `movie_story_enable_highlight_plan_llm=false`

4. 修复权威时间线锁误报。
   - 剧情边界吸附后会刷新 runtime 的 authoritative plot map。
   - 避免合法边界对齐后在 `select_final_story_evidence` 阶段报 timing mismatch。

5. `visual_mode=off` 时跳过 timeline_runtime 内部视觉边界检测。
   - 不再调用 ffmpeg/pyscenedetect 做视觉切点。

6. 审计阶段默认写 manifest，不导出 mp4 clips。
   - 默认仍能看到 `03_story_candidates`、`05_selected_highlights`、`06_scene_evidence_for_narration`、`07_narration_script`。
   - 需要视频片段时再设置 `movie_story_audit_export_clips=true`。

## 推荐先跑通配置

```toml
movie_story_narration_llm_mode = "fallback"
movie_story_enable_full_subtitle_llm = false
movie_story_enable_global_llm = false
movie_story_enable_segment_llm = false
movie_story_enable_story_validation_llm = false
movie_story_enable_highlight_plan_llm = false
movie_story_audit_export_clips = false
```

## 推荐质量配置

```toml
movie_story_narration_llm_mode = "hybrid"
movie_story_narration_llm_max_segments = 12
movie_story_enable_full_subtitle_llm = true
movie_story_enable_global_llm = false
movie_story_enable_segment_llm = false
movie_story_enable_story_validation_llm = false
movie_story_enable_highlight_plan_llm = false
movie_story_audit_export_clips = false
```

## 高质量慢速配置

```toml
movie_story_narration_llm_mode = "full"
movie_story_enable_full_subtitle_llm = true
movie_story_enable_global_llm = true
movie_story_enable_segment_llm = true
movie_story_enable_story_validation_llm = true
movie_story_enable_highlight_plan_llm = true
movie_story_audit_export_clips = false
```

## 已验证

- `app/services/subtitle_first_pipeline.py` 语法检查通过。
- `app/services/movie_story/timeline_runtime.py` 语法检查通过。
- `app/services/movie_story/story_runtime.py` 语法检查通过。
- 最小 SRT + `visual_mode=off` + 无 LLM 配置能返回 `success=True`。
- 审计目录能够推进到：
  - `03_story_candidates`
  - `05_selected_highlights`
  - `06_scene_evidence_for_narration`
  - `07_narration_script`

说明：当前容器没有你的完整真实模型、ASR、TTS 和视频合成运行环境，因此没有声称“真实长视频最终成片导出”已完整验证。
