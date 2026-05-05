# Stage-M：影视解说链路统一输出 CompositionPlan

## 背景

Stage-H/I 已经把 `subtitle_first_pipeline.py` 从旧仓库字幕优先影视解说大文件，逐步拆成 `movie_story` 能力层。Stage-J/K/L 又把 `highlight_edit_pipeline.py` 的粗剪候选、选择、合成和输出写盘拆入 `movie_story`。

但 Stage-L 后仍存在一个架构分裂：

- 粗剪主链输出 `CompositionPlan`，再由 `composition_plan_adapter` 转成旧 `script_items`。
- 影视解说主链仍先输出旧 `script_items`，没有统一的 `CompositionPlan` 产物。

这会导致 WebUI、渲染、任务历史、审计和后续新项目迁移继续维护两套结果格式。

## 本轮升级

新增：

- `app/services/movie_story/composition_bridge.py`
- `tests/test_movie_story_composition_bridge.py`

更新：

- `app/services/subtitle_first_pipeline.py`
- `app/services/composition_plan_adapter.py`
- `app/models/highlight_edit_schema.py`
- `app/services/movie_story/README.md`

## 新模块职责

`composition_bridge.py` 负责把影视解说最终脚本转成统一 `CompositionPlan`：

1. 以 `script_items` 的 `start/end` 作为权威视频时间窗。
2. 匹配 `narration_evidence` 与 `story_highlights`，补齐来源、剧情类型、选择理由、语义窗和校验元数据。
3. 根据 `OST`、raw voice 标记和 narration 文本推导 `audio_mode`：`raw` / `ducked_raw` / `tts` / `mute`。
4. 构建连续 `timeline_start/timeline_end`，不让 TTS 时长反向裁剪视频片段。
5. 输出轻量 `validate_composition_plan` 报告，写入审计阶段 `08_movie_story_composition_plan`。

## 主链变化

`subtitle_first_pipeline.py` 现在仍保留旧 API，但返回结果新增：

- `composition_plan`
- `composition_plan_path`
- `composition_plan_report`
- `composition_plan_ready`

同时仍保留旧字段：

- `script_items`
- `script_path`
- `highlight_script_path`
- `highlight_narration_segments_path`

所以旧调用方不会断，新调用方可以直接消费 `CompositionPlan`。

## 架构意义

Stage-M 后，两条主链的输出方向统一：

```text
highlight_edit_pipeline
  → CompositionPlan
  → script_items adapter

subtitle_first_pipeline
  → finalized movie_story script_items
  → movie_story CompositionPlan bridge
  → CompositionPlan + legacy script_items
```

短期仍允许两条入口并存，长期目标是让 WebUI、渲染器、任务历史和审计统一消费 `CompositionPlan`。

## 不做的事

本轮不删除 `subtitle_first_pipeline.py`，也不把成熟旧解说生成器重写成 CompositionPlan-first。原因是旧解说器已经在生成质量、反字幕复读、语义窗锁定方面较稳定。本轮只建立安全桥接层，降低架构分裂风险。
