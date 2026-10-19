# Movie Story Migration Stage A Report

## 本轮固定目标

本轮不修最终解说词，不以“是否像台词复述”为验收目标。

本轮只完成旧项目强项的第一层迁移：

1. 生成正式 `04_global_story_context`。
2. 在局部证据和高光解说证据里补齐旧项目需要的 rich evidence 字段。
3. 给每条 evidence 写入 `evidence_completeness`。
4. 增加自动跟踪脚本，明确本阶段哪些达标、哪些未达标。

## 新增/修改文件

- `app/services/movie_story/evidence_enrichment.py`
  - `build_global_story_context()`：把旧项目的全局剧情理解能力转成新项目稳定上下文字段。
  - `enrich_evidence_items()`：补齐局部剧情理解、冲突、人物动机、剧情功能、narration_intent。
  - `evaluate_evidence_items()`：计算 rich evidence 达标率。

- `app/services/subtitle_first_pipeline.py`
  - 增加 `04_global_story_context` 审计产物。
  - 在 `add_local_understanding` 后强制补齐 local evidence。
  - 在 `validate_story_segments` 后二次补齐 local evidence。
  - 在 `05b_build_highlight_narration_evidence` 后强制补齐最终给 narration 的 rich evidence。
  - 写入 `06a_evidence_completeness` 检查点。

- `app/services/movie_story/audit_policy.py`
  - 将 `04_global_story_context`、`06a_evidence_completeness` 加入生产审计阶段。

- `tools/verify_movie_story_migration_stage.py`
  - 新增阶段跟踪脚本。
  - 当前支持 `stage_a`，检查旧项目剧情理解/evidence 层是否移植达标。

- `tests/test_movie_story_architecture_contract_a.py`
  - 新增阶段 A 单元测试。

## 阶段 A 验收标准

`tools/verify_movie_story_migration_stage.py --stage stage_a` 会检查：

1. 是否存在 `04_global_story_context`。
2. `global_story_context` 是否包含：
   - `main_conflict`
   - `story_theme`
   - `genre`
   - `main_characters`
   - `timeline_summary`
3. 是否存在 `06_scene_evidence_for_narration`。
4. 每条 evidence 是否包含：
   - `subtitle_text`
   - `surface_dialogue_meaning`
   - `real_narrative_state`
   - `conflict_summary`
   - `character_motivation`
   - `story_function`
   - `plot_function`
   - `importance_level`
   - `narration_intent`
   - `_global_summary`
5. 默认 90% 以上 evidence 通过，阶段 A 才算通过。

## 跟踪脚本用法

```bash
python tools/verify_movie_story_migration_stage.py \
  --stage stage_a \
  --audit-dir /path/to/_movie_story_pipeline_audit_clips/run_YYYYMMDD_HHMMSS
```

或：

```bash
python tools/verify_movie_story_migration_stage.py \
  --stage stage_a \
  --audit-json /path/to/movie_story_audit.json
```

如果未达标，脚本会输出 `next_targets`，下一轮只修这些未达标项，不跳阶段。

## 本轮验证

已执行：

```bash
python3 -m compileall -q app/services/movie_story app/services/subtitle_first_pipeline.py tools/verify_movie_story_migration_stage.py
pytest -q tests/test_movie_story_architecture_contract_a.py tests/test_generate_narration_script.py tests/test_plot_understanding.py
```

结果：

```text
9 passed
```

使用用户上传的旧审计包 `run_20260502_180430` 做基线检查：

- 基线：未达标，因为旧 run 没有 `04_global_story_context` 和 `06_scene_evidence_for_narration`。
- 用本轮 Stage-A enrichment 对该 run 的 `03_story_candidates + 05_selected_highlights` 做回放：
  - global context：通过。
  - rich evidence：32 / 32 通过，pass_rate = 1.0。

## 下一步

只有用户重新跑本补丁，并且 `tools/verify_movie_story_migration_stage.py --stage stage_a` 通过后，才进入下一阶段。

下一阶段建议是：

**阶段 B：旧项目高光规划逻辑迁移**

目标：让 `05_selected_highlights` 不只是 typed selector 选片段，而是带有旧项目式的：

- `selection_reason`
- `story_role`
- `highlight_type`
- `score_breakdown`
- 与 `global_story_context` 的关系
- 高光多样性检查
