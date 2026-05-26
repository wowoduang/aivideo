# Movie Story Pipeline Stage-I Modularization

本轮目标不是新增一套平行解说链路，而是把 Stage-H 后仍滞留在 `subtitle_first_pipeline.py` 的稳定生产能力继续抽入 `movie_story`，让旧入口退化为兼容编排器。

## 已迁出模块

| 模块 | 从旧大文件迁出的职责 | 新定位 |
|---|---|---|
| `movie_story/runtime_options.py` | 目标时长、视觉模式、LLM 配置解析、迁移阶段、解说 LLM 模式、阶段 trace | 所有 movie-story 入口的统一运行参数层 |
| `movie_story/audit_runtime.py` | 阶段 marker、manifest、CSV、items_full、可选 clips 导出、保留最近运行目录 | 统一审计输出层 |
| `movie_story/scene_alignment.py` | 复用已有边界池收集 cut points、语义窗对齐、时间窗解析 | 剧情高光/解说片段的时间边界对齐层 |
| `movie_story/highlight_runtime.py` | bounded LLM 高光规划、fallback global summary、story candidates、typed selector fallback、最终 evidence guard | 旧 AIVideoGPT 高光规划与最终 evidence 选择运行层 |
| `movie_story/quality_gate.py` | pipeline 质量门禁、最终 audit payload 构建 | 统一质量验收层 |

## 旧入口现状

`app/services/subtitle_first_pipeline.py` 仍保留 `run_subtitle_first_pipeline(...)` 兼容入口，但本轮后它从约 2035 行降到约 997 行。它现在主要负责：

1. 接收旧 API 参数；
2. 调用字幕、故事窗口、证据增强、高光选择、代表帧、解说运行、最终校验模块；
3. 写出脚本、高光、审计产物；
4. 返回旧调用方兼容结果。

原则：后续新增影视解说能力必须进入 `movie_story/*`，不能继续塞回 `subtitle_first_pipeline.py`。

## 与 A-G/H 的关系

- A-G 已迁入 `movie_story` 的能力继续保留；
- Stage-H 已把抽样解说校验收口为正式 `narration_finalize.py`；
- Stage-I 继续把剩余运行参数、审计、场景对齐、高光运行和质量门禁从旧大文件移出；
- 这不是重启迁移，而是在现有 `movie_story` 新架构上继续收口。

## 验证

本轮至少需要通过以下测试：

```bash
python -m py_compile app/services/subtitle_first_pipeline.py app/services/movie_story/*.py
pytest -q \
  tests/test_subtitle_first_pipeline_prologue.py \
  tests/test_movie_story_narration_finalize.py \
  tests/test_movie_story_migration_stage_a.py \
  tests/test_movie_story_migration_stage_b.py \
  tests/test_movie_story_migration_stage_c.py \
  tests/test_movie_story_migration_stage_d.py \
  tests/test_generate_narration_script_clean.py \
  tests/test_highlight_edit_pipeline.py \
  tests/test_composition_plan_adapter.py \
  tests/test_highlight_selector.py \
  tests/test_highlight_timeline_planner.py \
  tests/test_movie_story_flow_debug_fix.py
```

当前本轮局部验证结果：58 passed。

## 下一轮建议

下一轮重点不再继续拆小 helper，而是收敛两个入口的关系：

1. 将 `movie_story` 输出逐步适配为 `CompositionPlan`；
2. 让 `highlight_edit_pipeline.py` 在 `mode="movie_story"` 时复用 `movie_story` 的 evidence/highlight/narration runtime；
3. `subtitle_first_pipeline.py` 最终只保留旧接口兼容和结果格式转换。
