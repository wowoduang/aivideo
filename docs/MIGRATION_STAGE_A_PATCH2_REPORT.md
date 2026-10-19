# Migration Stage A Patch 2 Report

## 本次目标

本次不评估最终解说词，不调用最终大模型写解说。目标只固定在 Stage A：

- 必须生成 `04_global_story_context`
- 必须生成 `06_scene_evidence_for_narration`
- `06` 必须包含旧项目解说链路需要的 rich evidence 字段
- 验收脚本必须能明确输出达标/未达标

## 修复的问题

### 1. 修复真实运行链路没有生成 04/06 的问题

上一个 Stage A 补丁主要接入了 `subtitle_first_pipeline.py` 分支，但前端真实运行会经过 `movie_story.story_runtime` 与 `timeline_runtime.audit_stage` 这条 active runtime 审计链路。

本次在 `story_runtime.py` 里补齐：

- `04_global_story_context`
- `06_scene_evidence_for_narration`
- `06a_evidence_completeness`

这样即使真实运行只看到 `03_story_candidates` / `05_selected_highlights`，也会在同一条 active runtime 内生成 Stage A 必需产物。

### 2. 修复旧 audit keep 配置隐藏新阶段的问题

用户旧配置可能仍然是：

```text
00c_boundary_summary,01_shot_candidates,02_scene_candidates,03_story_candidates,05_selected_highlights
```

这会导致 04/06 即使代码执行也被审计策略跳过。

本次修改：

- `audit_policy.keep_stages()` 会强制 union Stage A 必需阶段
- `timeline_runtime.audit_stage()` 也会强制保留 Stage A 必需阶段

### 3. 修复 manifest 过于精简导致 verifier 看不到 rich evidence 字段

`manifest.json` 面向表格展示，之前只保留 brief rows。

本次新增：

```text
items_full.json
```

同时 `verify_movie_story_migration_stage.py` 会优先读取 `items_full.json`，这样能检查完整字段：

- `surface_dialogue_meaning`
- `real_narrative_state`
- `conflict_summary`
- `character_motivation`
- `story_function`
- `narration_intent`
- `_global_summary`

### 4. Stage A 默认禁用最终大模型解说

当前阶段只验收 evidence，不验收最终文案。

默认：

```text
movie_story_migration_stage = stage_a
```

如果没有显式设置 narration mode，则最终解说生成模式为：

```text
disabled
```

会输出占位脚本：

```text
[NARRATION_DISABLED_FOR_STAGE_A]
```

避免在 rich evidence 未达标前消耗大量 token。

## 修改文件

- `app/services/movie_story/audit_policy.py`
- `app/services/movie_story/timeline_runtime.py`
- `app/services/movie_story/story_runtime.py`
- `app/services/subtitle_first_pipeline.py`
- `tools/verify_movie_story_migration_stage.py`
- `tests/test_movie_story_runtime_audit_contract.py`

## 验证结果

已执行：

```bash
python -m compileall -q app/services app/api tools
pytest -q \
  tests/test_movie_story_runtime_audit_contract.py \
  tests/test_movie_story_architecture_contract_a.py \
  tests/test_generate_narration_script.py \
  tests/test_plot_understanding.py
```

结果：

```text
10 passed
```

另外执行了 runtime 审计回放验证：

- 输入 3 条模拟宫廷剧情 scene
- 生成 `04_global_story_context`
- 生成 `06_scene_evidence_for_narration`
- `verify_movie_story_migration_stage.py --stage stage_a` 返回 `overall_passed=true`

## 下一步验收

重新运行项目后执行：

```powershell
python tools/verify_movie_story_migration_stage.py `
  --stage stage_a `
  --audit-dir E:\aivideo-v5-workspace\frontend_uploads\video\_movie_story_pipeline_audit_clips\run_xxxxx
```

如果 `overall_passed=true`，才能进入 Stage B：旧项目高光规划逻辑迁移。

如果没通过，继续只修 Stage A 报告里的 `next_targets`，不跳阶段。
