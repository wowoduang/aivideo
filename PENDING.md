# PENDING.md — aivideo 待完成任务

> 本文件是给 ChatGPT / Claude Code / Cursor 的任务队列。开始任务前先阅读 `CLAUDE.md`、相关 ADR、设计文档和目标文件 `__CONTEXT__`。

## 🟡 中优先级

### [PEND-201] 更新 two_round 第二轮提示词与剪辑契约对齐

**状态**：待分析

**背景**：

当前 `WRITER_PROMPT_TEMPLATE` 会让第二轮从整集范围内选择片段。后续需要确认第二轮输出片段如何与剪辑合成模块对齐。

**注意**：

不要把第一轮前的 `visual_focus_segments` 当作第二轮必须采用的片段。大模型两轮链负责最终文案和片段选择。

---

## [PEND-STAGE2-VISUAL-TIMELINE]
- Goal: migrate deterministic shot/scene segmentation and budgeted visual focus segment selection into `two_round_visual`.
- Status: completed by `apply_stage2_two_round_visual_timeline_patch.py` (initial implementation).
- Follow-up:
  - verify real end-to-end behavior on project videos
  - tune frame budgets
  - optionally add stronger speaker-name context integration

## [PEND-STAGE3B-CODE-RULE-CLEANUP]
- Status: applied by `fix_stage3b_focus_selector_order_and_audit_v1.py`.
- Reason: stage3b selector tests exposed a design bug in coverage-first selection for tiny budgets.
- Guard: `tools/audit_two_round_visual_code_rules.py` added to catch syntax/header/length/forbidden-pattern mistakes before business tests.
- Next: run compileall, focused pytest, and audit before any further feature patch.

## [PEND-STAGE3B-SELECTOR-AUDIT-V2]
- Status: applied by `fix_stage3b_selector_and_audit_v2.py`.
- Reason: previous audit script had an unterminated string literal and selector referenced an undefined helper.
- Scope: overwrite `visual_focus_segments.py` with a complete hybrid selector and repair `tools/audit_two_round_visual_code_rules.py`.
- Rule: no further business task should run until compileall, audit, and focused pytest all pass.

## [PEND-STAGE3C-PROMPT-HEADING-AND-RULE-CLEANUP]
- Status: applied by `rename_visual_prompt_headings_and_remove_extra_rules_v1.py`.
- Scope: two_round_visual prompt-facing text only.
- Changed headings:
  - `【视觉重点片段（仅用于详细抽帧，不是最终剪辑片段）】` -> `【视觉片段抽帧】`
  - `【视觉重点片段详细关键帧】` -> `【视觉片段详细抽帧】`
- Removed: `【two_round_visual 额外规则】` appended first-round prompt block.
- Not changed: base two_round prompts, internal visual_focus_segments data name, selector logic.

## DONE-012 active/support docstrings round15

- 为 `two_round_narration.py`、`visual_focus_segments.py`、`two_round_visual_input_packager.py` 中缺少职责说明的 active/support 函数补 docstring。
- 新增 `tests/movie_story/test_active_support_docstrings.py`，保护视觉增强第一轮前边界、字幕时间锚点边界、基础双轮不接旧 fallback 的注释约束。
- 本轮只补注释，不改提示词、不改业务逻辑、不删除旧模块。

## DONE-013 active/support docstrings round15 fix

- 修复 `tests/movie_story/test_active_support_docstrings.py` 的项目根目录定位错误。
- 原测试在 `tests/movie_story/` 中使用 `parents[1]`，会定位到 `E:/aivideo/tests`；现改为 `parents[2]`，定位到 `E:/aivideo`。
- 本轮只修测试路径，不改业务逻辑、不改提示词、不改注释内容。

## DONE-014 priority boundaries/docstrings round16

- 将上一轮 unknown 但有明确用途的 movie_story/long-video-to-shorts 模块登记到 `functional_contracts.py`。
- 为 timeline/highlight/composition/local runner 一批 split/annotate 候选函数补职责 docstring。
- 新增 `tests/movie_story/test_priority_boundaries_docstrings.py`，保护这些模块边界和注释不被后续重构删除。
- 本轮只补契约与注释，不改业务逻辑、不改提示词、不删除旧源码。

## DONE-015 priority boundaries/docstrings round16 fix

- 修复 `tests/movie_story/test_priority_boundaries_docstrings.py` 的项目根目录定位错误。
- 原测试在 `tests/movie_story/` 中使用 `parents[1]`，会定位到 `E:/aivideo/tests`；现改为 `parents[2]`，定位到 `E:/aivideo`。
- 本轮只修测试路径，不改业务逻辑、不改提示词、不改注释内容。

## DONE-016 composition plan helpers round17

- 新增 `app/services/movie_story/composition_plan_helpers.py`，沉淀长视频拆短视频/剪辑合成计划的纯确定性 helper。
- 新增 `tests/movie_story/test_composition_plan_helpers.py`，保护时间段校验、最小时长扩展、时长分配、区间合并和稳定 group id 构造。
- 将 `composition_plan_helpers` 登记为 `long_video_to_shorts` 的 `active_support` 模块。
- 本轮不改现有业务调用链，新 helper 先待引用，后续再逐步接入 composition/highlight 模块。

## DONE-017 highlight window helpers round18

- 新增 `app/services/movie_story/highlight_window_helpers.py`，沉淀长视频拆短视频候选窗口的纯确定性 helper。
- 新增 `tests/movie_story/test_highlight_window_helpers.py`，保护窗口校验、扩展、重叠去重、分数合成、metadata 合并和稳定候选 ID。
- 将 `highlight_window_helpers` 登记为 `long_video_to_shorts` 的 `active_support` 模块。
- 本轮不改现有业务调用链，新 helper 先待引用，后续再逐步接入 highlight selection/runtime。

## DONE-018 timeline candidate helpers round19

- 新增 `app/services/movie_story/timeline_candidate_helpers.py`，沉淀时间轴候选的纯确定性 helper。
- 新增 `tests/movie_story/test_timeline_candidate_helpers.py`，保护候选校验、重叠去重、覆盖桶、每桶 top 候选、场景边界规范化和窗口扩展。
- 将 `timeline_candidate_helpers` 登记为 `long_video_to_shorts` 的 `active_support` 模块。
- 本轮不改现有业务调用链，新 helper 先待引用，后续再逐步接入 timeline/highlight/visual focus 模块。

## DONE-019 narration timecode helpers round20

- 新增 `app/services/movie_story/narration_timecode_helpers.py`，沉淀解说文案时间码和所需时长计算的纯确定性 helper。
- 新增 `tests/movie_story/test_narration_timecode_helpers.py`，保护字符数估算、60 秒下限、窗口扩展、排序、重叠检测和序列化。
- 将 `narration_timecode_helpers` 登记为 `two_round` 的 `active_support` 模块。
- 本轮不改现有业务调用链，不改两轮提示词，新 helper 先待引用。

## DONE-028 detach unified entry from engines round28a fix

- 更新 `tests/test_movie_story_unified_entry.py`，改为 monkeypatch `run_highlight_edit_pipeline`。
- 更新 `tests/test_movie_story_architecture_guard.py`，允许 `unified_entry.py -> app.services.highlight_edit_pipeline` 作为 round24 已登记的 `long_video_to_shorts / migration_value_review` 边界。
- 本轮只修测试和架构测试口径，不改业务逻辑、不改提示词、不新增 fallback。

## DONE-047 archived old-chain pending history round40

- 已将项目待办中的旧链路历史段落移入 workspace recycle。
- 当前项目目录只保留现行主流程相关记录。
- 本轮只整理历史记录，不改业务逻辑、不改提示词、不新增 fallback。

## DONE-048 root transient cleanup round41

- 批量清理项目根目录非源码临时残留。
- 仅处理根目录直接子项，不递归触碰 app/tests/tools/docs/web/scripts/resource/docker 等源码目录。
- 回收目录：`E:\aivideo-workspace\root_cleanup\round41_root_transient_cleanup_20260527_115947`。
- 新增 `tests/test_root_transient_artifacts_round41.py`，防止补丁脚本、审计脚本、压缩包、临时备份和运行产物目录回流到项目根目录。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved root artifacts

- `E:\aivideo\storage` -> `E:\aivideo-workspace\root_cleanup\round41_root_transient_cleanup_20260527_115947\storage` | root transient directory: storage

## DONE-049 docs tree final sweep round42

- Cleaned historical documentation residue from `docs/`.
- Moved matched files to workspace recycle: `E:\aivideo-workspace\recycle\round42_docs_tree_final_sweep_20260527_120513`.
- Removed empty documentation folders: 1.
- Added `tests/test_docs_tree_final_sweep_round42.py` to protect the cleaned docs tree.
- This round did not change runtime code, prompts, or current active flows.

### Summary

- moved docs: 1
- removed empty dirs: 1

## DONE-050 project hygiene guard consolidation round43

- 合并 root transient 与 docs tree cleanup 两类 round-specific guard。
- 新增 `tests/test_project_hygiene_contract.py` 作为统一项目卫生契约。
- 将 round-specific guard 测试移入 workspace recycle。
- 回收目录：`E:\aivideo-workspace\recycle\round43_project_hygiene_guard_consolidation_20260527_121423`。
- 本轮只合并测试，不改业务逻辑、不改提示词、不新增 fallback。

### Moved tests

- `E:\aivideo\tests\test_root_transient_artifacts_round41.py` -> `E:\aivideo-workspace\recycle\round43_project_hygiene_guard_consolidation_20260527_121423\tests\test_root_transient_artifacts_round41.py` | merged into tests/test_project_hygiene_contract.py
- `E:\aivideo\tests\test_docs_tree_final_sweep_round42.py` -> `E:\aivideo-workspace\recycle\round43_project_hygiene_guard_consolidation_20260527_121423\tests\test_docs_tree_final_sweep_round42.py` | merged into tests/test_project_hygiene_contract.py

## DONE-051 orphan support code cleanup round44

- 批量检查一组旧清理阶段支撑模块。
- 只有完全没有 app/tests/tools import 引用的候选模块才移出 app 主源码树。
- 回收目录：`E:\aivideo-workspace\recycle\round44_orphan_support_code_cleanup_20260527_122017`。
- 新增 `tests/test_orphan_support_code_cleanup_round44.py` 保护已回收支撑模块不再被 import。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved modules

- no files moved

## DONE-052 native migration support recycle round45

- 批量回收旧 native migration 支撑代码与对应测试。
- 回收前已确认除本组待移动文件外，app/tests/tools 不再 import 这些支撑模块。
- 回收目录：`E:\aivideo-workspace\recycle\round45_native_migration_support_recycle_20260527_122533`。
- 重写 `tests/test_orphan_support_code_cleanup_round44.py`，保护 round45 后状态。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved files

- `E:\aivideo\tools\audit_movie_story_native_migration.py` -> `E:\aivideo-workspace\recycle\round45_native_migration_support_recycle_20260527_122533\tools\audit_movie_story_native_migration.py` | old native migration support group
- `E:\aivideo\app\services\movie_story\architecture_guard.py` -> `E:\aivideo-workspace\recycle\round45_native_migration_support_recycle_20260527_122533\app\services\movie_story\architecture_guard.py` | old native migration support group
- `E:\aivideo\app\services\movie_story\engine_status.py` -> `E:\aivideo-workspace\recycle\round45_native_migration_support_recycle_20260527_122533\app\services\movie_story\engine_status.py` | old native migration support group
- `E:\aivideo\tests\test_movie_story_engine_status.py` -> `E:\aivideo-workspace\recycle\round45_native_migration_support_recycle_20260527_122533\tests\test_movie_story_engine_status.py` | old native migration support group

## DONE-053 functional contract support recycle round46

- 批量回收旧清理阶段的功能边界/功能契约支撑代码。
- 对仍保留的 active helper 测试，只删除边界契约断言，保留 helper 行为测试。
- 回收目录：`E:\aivideo-workspace\recycle\round46_functional_contract_support_recycle_20260527_123151`。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved files

- `E:\aivideo\app\services\movie_story\functional_boundaries.py` -> `E:\aivideo-workspace\recycle\round46_functional_contract_support_recycle_20260527_123151\app\services\movie_story\functional_boundaries.py` | functional contract support module has no remaining imports
- `E:\aivideo\app\services\movie_story\functional_contracts.py` -> `E:\aivideo-workspace\recycle\round46_functional_contract_support_recycle_20260527_123151\app\services\movie_story\functional_contracts.py` | functional contract support module has no remaining imports

### Modified tests

- `tests/movie_story/test_composition_plan_helpers.py` | removed_imports=1, removed_tests=1
- `tests/movie_story/test_highlight_window_helpers.py` | removed_imports=1, removed_tests=1
- `tests/movie_story/test_narration_timecode_helpers.py` | removed_imports=1, removed_tests=1
- `tests/movie_story/test_priority_boundaries_docstrings.py` | removed_imports=1, removed_tests=1
- `tests/movie_story/test_timeline_candidate_helpers.py` | removed_imports=1, removed_tests=1

## DONE-054 removed pipeline code path sweep round47

- 扫描 app/tools/tests 下旧链路命名的 Python 文件路径残留。
- 若候选 app/tools 模块仍被外部 import，脚本会直接报错；本轮移动的均为可安全移出项目主树的残留。
- 回收目录：`E:\aivideo-workspace\recycle\round47_removed_pipeline_code_path_sweep_20260527_123744`。
- 更新集中 old-chain guard，防止旧链路命名源码/工具/测试文件回流。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Summary

- moved files: 3

## DONE-055 priority docstrings after round47 fix

- 修正 `tests/movie_story/test_priority_boundaries_docstrings.py` 中对已回收文件的 docstring 检查。
- 不恢复旧文件、不创建兼容 stub、不新增 fallback。
- 清理结果：removed_dict_entries=1, removed_list_items=1

## DONE-056 priority docstrings after round47 fix v5

- 重写 `tests/movie_story/test_priority_boundaries_docstrings.py` 为当前 active 短视频合成链路 docstring 契约。
- 不再要求当前 active 源码写回已移除链路的历史措辞。
- 本轮不恢复旧文件、不创建兼容 stub、不改业务逻辑、不改提示词、不新增 fallback。

## DONE-057 removed pipeline final contract round48

- 新增 `tests/test_removed_pipeline_final_contract_round48.py`，集中保护旧链路源码、工具、测试路径和文档 token 不回流。
- 本轮只新增最终防回流测试，不改业务逻辑、不改提示词、不新增 fallback。

## DONE-058 removed pipeline guard consolidation round49

- 将旧链路过渡 guard 合并进最终防回流契约。
- 重写 `tests/test_removed_pipeline_final_contract_round48.py`，覆盖已回收源码、工具、测试、docs、PENDING 的防回流检查。
- 回收目录：`E:\aivideo-workspace\recycle\round49_removed_pipeline_guard_consolidation_20260527_131348`。
- 本轮只合并测试，不改业务逻辑、不改提示词、不新增 fallback。

### Moved guards

- `E:\aivideo\tests\test_old_chain_recycled_contract.py` -> `E:\aivideo-workspace\recycle\round49_removed_pipeline_guard_consolidation_20260527_131348\tests\test_old_chain_recycled_contract.py` | merged into removed pipeline final contract
- `E:\aivideo\tests\test_orphan_support_code_cleanup_round44.py` -> `E:\aivideo-workspace\recycle\round49_removed_pipeline_guard_consolidation_20260527_131348\tests\test_orphan_support_code_cleanup_round44.py` | merged into removed pipeline final contract

## DONE-059 narration quality confidence labels round50

- 修复 narration workbench evidence pack 构建时对 `asr_high` 等置信度标签直接 `float(...)` 导致 500 的问题。
- 已知标签明确映射为数值；未知标签和越界值直接报错。
- 本轮不改 two_round_visual 主链路、不改提示词、不新增 fallback。

### Changes

- inserted confidence normalization helper
- replaced raw float confidence conversion

## DONE-060 narration quality confidence round50 fix v2

- 修复 round50 补丁中 `idx` / `index` 变量名错误导致 workbench 和 narration tests 失败的问题。
- 补充 build_evidence_pack 回归测试，覆盖缺失 confidence 的 script evidence。
- 修正 project hygiene guard：`storage/` 是当前服务会重新创建的运行时目录，不再作为根目录 transient 清理目标。
- 修复上一版补丁脚本的 f-string 反斜杠语法错误。
- 本轮不改 two_round_visual 主链路、不改提示词、不新增 fallback。

### Changes

- fixed confidence helper call from idx to index
- added build_evidence_pack idx/index regression test
- removed runtime storage directory from transient root dirs

## DONE-061 movie_story orphan candidates recycle round51

- 根据 round50 active code inventory，批量回收静态无引用的 movie_story orphan candidate 支撑模块。
- v2 修复字符串预检误报：`app.services.movie_story.audit_runtime` 不再误判为 `app.services.movie_story.audit`。
- 回收前检查 app/tests/tools import 引用和 app/tools 完整模块/路径字符串引用。
- 包结构 `__init__.py` 暂不按普通 orphan 删除。
- 回收目录：`E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756`。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved files

- `app.services.movie_story.audit`: `E:\aivideo\app\services\movie_story\audit.py` -> `E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\audit.py`
- `app.services.movie_story.commentary_pipeline`: `E:\aivideo\app\services\movie_story\commentary_pipeline.py` -> `E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\commentary_pipeline.py`
- `app.services.movie_story.engine_failover`: `E:\aivideo\app\services\movie_story\engine_failover.py` -> `E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\engine_failover.py`
- `app.services.movie_story.quality_gate`: `E:\aivideo\app\services\movie_story\quality_gate.py` -> `E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\quality_gate.py`
- `app.services.movie_story.scene_alignment`: `E:\aivideo\app\services\movie_story\scene_alignment.py` -> `E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\scene_alignment.py`

### Skipped package init files

- `app/services/movie_story/__init__.py`
- `app/services/movie_story/production/__init__.py`

## DONE-062 restore audit after round51 relative import miss

- 修复 round51 v2 漏检相对 import 的问题：`pipeline.py` 仍通过 `.audit` 使用 `StageAuditWriter`。
- `audit.py` 不是 orphan，已从 recycle 恢复。
- 同步修正 round51 recycled guard。
- 本轮不创建兼容 stub、不改业务逻辑、不改提示词、不新增 fallback。

### Changes

- restored E:\aivideo-workspace\recycle\round51_movie_story_orphan_candidates_recycle_20260527_153756\app\services\movie_story\audit.py -> E:\aivideo\app\services\movie_story\audit.py
- removed audit.py from round51 recycled guard

## DONE-063 LLM tests out of app round52

- 将误放在 `app/services/llm/` 生产代码目录里的测试文件移到 `tests/services/llm/`。
- 移动前检查相对 import；若存在相对 import，脚本会拒绝移动。
- 新增 `tests/test_llm_tests_out_of_app_round52.py`，防止 LLM 测试文件回流到 app 生产目录。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved files

- `E:\aivideo\app\services\llm\test_litellm_integration.py` -> `E:\aivideo\tests\services\llm\test_litellm_integration.py` | moved LLM test out of app/services/llm
- `E:\aivideo\app\services\llm\test_llm_service.py` -> `E:\aivideo\tests\services\llm\test_llm_service.py` | moved LLM test out of app/services/llm

## DONE-064 LLM manual checks round52 fix

- 修复 round52 将 LLM 集成/手工检查文件放入 pytest 默认收集路径导致全量测试失败的问题。
- 这些文件依赖真实 provider / LiteLLM / async 运行环境，保留为 `tests/manual/llm/*_check.py`，不作为默认单元测试收集。
- 重写 `tests/test_llm_tests_out_of_app_round52.py`，继续保护 app 生产目录无 test 文件。
- 本轮不改业务逻辑、不改 LLM provider 代码、不新增 fallback。

### Moved files

- `E:\aivideo\tests\services\llm\test_litellm_integration.py` -> `E:\aivideo\tests\manual\llm\litellm_integration_check.py` | renamed unstable LLM integration test into manual check not collected by pytest tests
- `E:\aivideo\tests\services\llm\test_llm_service.py` -> `E:\aivideo\tests\manual\llm\llm_service_check.py` | renamed unstable LLM integration test into manual check not collected by pytest tests

### Removed empty dirs

- no empty dirs removed

## DONE-065 stabilize round-named guard tests round53

- 将稳定 guard 测试从 round-numbered 文件名改为正式文件名。
- 同步修正 guard 内部自引用路径。
- 新增 `tests/test_test_filename_residue_contract.py`，防止 round48/round51/round52 这类临时命名回流。
- 本轮只重命名测试文件，不改业务逻辑、不改提示词、不新增 fallback。

### Renamed files

- `E:\aivideo\tests\test_removed_pipeline_final_contract_round48.py` -> `E:\aivideo\tests\test_removed_pipeline_final_contract.py` | renamed round-numbered guard test to stable name
- `E:\aivideo\tests\test_movie_story_orphan_candidates_recycled_round51.py` -> `E:\aivideo\tests\test_movie_story_orphan_candidates_recycled.py` | renamed round-numbered guard test to stable name
- `E:\aivideo\tests\test_llm_tests_out_of_app_round52.py` -> `E:\aivideo\tests\test_llm_tests_out_of_app.py` | renamed round-numbered guard test to stable name

### Internal reference updates

- updated internal references: tests/test_removed_pipeline_final_contract.py
- updated internal references: tests/test_movie_story_orphan_candidates_recycled.py
- updated internal references: tests/test_llm_tests_out_of_app.py

## DONE-066 SDE SDP package init round55

- 根据 round54 audit，给已存在但缺少显式包边界的 `app/services/short_drama_editing` 与 `app/services/short_drama_production` 添加 `__init__.py`。
- 本轮不改包名、不移动业务文件、不改 import，只补齐 package boundary。
- 新增 `tests/test_sde_sdp_package_init_round55.py` 防止显式包边界缺失。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Changes

- created E:\aivideo\app\services\short_drama_editing\__init__.py
- created E:\aivideo\app\services\short_drama_production\__init__.py

## DONE-067 stabilize SDE SDP guard name round56

- 修复 round56 半完成状态：不再依赖 `test_round_named_guard_tests_stabilized.py` 内部存在 `ROUND_TOKEN_PATTERNS`。
- 确保 SDE/SDP package boundary guard 使用正式文件名 `tests/test_short_drama_packages_contract.py`。
- 新增 `tests/test_short_drama_package_names_contract.py` 保护旧 round55 文件名不回流。
- manifest: `E:\aivideo-workspace\recycle\round56_stabilize_sde_sdp_guard_name_fix_20260527_164144\MANIFEST.json`
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Rename state

- old round55 guard was already renamed before this fix

### Updates

- stable SDE/SDP guard already had no round55 tokens
- wrote tests/test_short_drama_package_names_contract.py

## DONE-069 transient artifact cleanup round58

- 批量移出项目主树中的 Python 编译缓存、pytest/mypy 缓存和 Windows 系统文件。
- 新增 `tests/test_transient_artifacts_hygiene.py`，防止 `__pycache__`、`.pyc`、`desktop.ini` 等回流。
- 同时保护 `app/` 生产代码目录不再出现 `test_*.py`。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Moved artifacts

- `E:\aivideo\app\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\api\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\api\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\api\routers\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\api\routers\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\api\schemas\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\api\schemas\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\config\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\config\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\models\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\models\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\repositories\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\repositories\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\schemas\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\schemas\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\short_drama_editing\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\short_drama_editing\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\short_drama_production\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\short_drama_production\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\short_drama_production\utils\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\short_drama_production\utils\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\llm\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\llm\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\llm\providers\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\llm\providers\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\movie_story\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\movie_story\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\movie_story\human_narration\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\movie_story\human_narration\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\movie_story\production\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\movie_story\production\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\prompts\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\prompts\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\prompts\documentary\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\prompts\documentary\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\prompts\movie_story_narration\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\prompts\movie_story_narration\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\prompts\short_drama_editing\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\prompts\short_drama_editing\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\services\prompts\short_drama_narration\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\services\prompts\short_drama_narration\__pycache__` | transient directory: __pycache__
- `E:\aivideo\app\utils\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\app\utils\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tests\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tests\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tests\api\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tests\api\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tests\manual\llm\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tests\manual\llm\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tests\movie_story\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tests\movie_story\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tests\services\llm\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tests\services\llm\__pycache__` | transient directory: __pycache__
- `E:\aivideo\tools\__pycache__` -> `E:\aivideo-workspace\recycle\round58_transient_artifact_cleanup_20260527_171347\tools\__pycache__` | transient directory: __pycache__

## DONE-070 transient artifact hygiene round58 fix

- 修复 round58 guard 与 `python -m compileall -q app tests tools` 的冲突。
- `__pycache__` / `.pyc` 会被 compileall 重新生成，不适合作为 pytest 后置断言。
- 保留稳定 guard：禁止 Windows 元数据文件和 app/ 下 test_*.py 回流。
- 后续打包 zip 时应由打包脚本排除 `__pycache__` / `.pyc`。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Changes

- rewrote transient hygiene guard to avoid compileall/__pycache__ contradiction

## DONE-071 simple cleanup batch round59

- 修复 round59 脚本自身 `newline` 参数错误导致的半完成状态。
- 当前未发现 `test_*_roundNN.py` 文件需要重命名；新增正式 guard 防止此类命名回流。
- 清理空的旧 LLM test 目录：`tests/services/llm`、`tests/services`。
- manifest: `E:\aivideo-workspace\recycle\round59_simple_cleanup_batch_fix_20260527_172316\MANIFEST.json`
- 本轮不处理 `_clean.py`、`migration_stage_x`、`llm_config.py`、超大文件拆分。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Removed empty dirs

- no empty leftover test service dirs removed

## DONE-072 migration stage test names round60

- 批量处理测试文件名中的 `migration_stage` 临时阶段命名。
- 匹配 `tests/**/test_*migration_stage*.py`，改为 `architecture_contract` 命名。
- 同步替换 tests/docs/PENDING 中旧路径文本。
- 新增 `tests/test_architecture_contract_test_names_stabilized.py` 防止 `migration_stage` 测试文件名回流。
- 本轮不处理 `_clean.py`、`llm_config.py`、超大文件拆分。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Renamed tests

- `E:\aivideo\tests\test_movie_story_migration_stage_a.py` -> `E:\aivideo\tests\test_movie_story_architecture_contract_a.py` | renamed migration_stage test file to architecture_contract test file
- `E:\aivideo\tests\test_movie_story_migration_stage_b.py` -> `E:\aivideo\tests\test_movie_story_architecture_contract_b.py` | renamed migration_stage test file to architecture_contract test file
- `E:\aivideo\tests\test_movie_story_migration_stage_c.py` -> `E:\aivideo\tests\test_movie_story_architecture_contract_c.py` | renamed migration_stage test file to architecture_contract test file
- `E:\aivideo\tests\test_movie_story_migration_stage_d.py` -> `E:\aivideo\tests\test_movie_story_architecture_contract_d.py` | renamed migration_stage test file to architecture_contract test file

### Text updates

- `E:\aivideo\docs\MIGRATION_STAGE_A_PATCH2_REPORT.md` replacements=1
- `E:\aivideo\docs\MIGRATION_STAGE_A_REPORT.md` replacements=2
- `E:\aivideo\docs\MIGRATION_STAGE_B_REPORT.md` replacements=3
- `E:\aivideo\docs\movie_story_highlight_edit_modularization_stage_k.md` replacements=4
- `E:\aivideo\docs\movie_story_pipeline_modularization_stage_i.md` replacements=4

## DONE-073 migration stage guard self-name fix

- 修复 round60 guard 自己的文件名包含 `migration_stage` 导致自身测试失败的问题。
- 将 guard 改名为 `tests/test_architecture_contract_test_names_stabilized.py`。
- 同步替换 tests/docs/PENDING 中旧路径文本。
- manifest: `E:\aivideo-workspace\recycle\round60_migration_stage_guard_self_name_fix_20260527_191421\MANIFEST.json`
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Rename

- `E:\aivideo\tests\test_migration_stage_test_names_stabilized.py` -> `E:\aivideo\tests\test_architecture_contract_test_names_stabilized.py` | renamed guard file so it no longer violates its own migration_stage filename rule

### Text updates

- `E:\aivideo\PENDING.md` replacements=1

## DONE-074 clean suffix service rename round61

- 批量处理 `app/services/**/_clean.py` 重构过渡命名，改为正式文件名。
- 同步替换 app/tests/tools/docs/PENDING 中的模块路径和文件路径文本。
- 若目标文件已存在，脚本会直接拒绝覆盖，不做兼容 wrapper。
- 新增 `tests/test_clean_suffix_service_names.py` 防止 `_clean.py` 命名回流。
- manifest: `E:\aivideo-workspace\recycle\round61_clean_suffix_service_rename_20260527_192136\MANIFEST.json`
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Renamed files

- `E:\aivideo\app\services\generate_narration_script.py` -> `E:\aivideo\app\services\generate_narration_script.py` | `app.services.generate_narration_script` -> `app.services.generate_narration_script`
- `E:\aivideo\app\services\plot_understanding.py` -> `E:\aivideo\app\services\plot_understanding.py` | `app.services.plot_understanding` -> `app.services.plot_understanding`
- `E:\aivideo\app\services\story_validator.py` -> `E:\aivideo\app\services\story_validator.py` | `app.services.story_validator` -> `app.services.story_validator`
- `E:\aivideo\app\services\subtitle_review.py` -> `E:\aivideo\app\services\subtitle_review.py` | `app.services.subtitle_review` -> `app.services.subtitle_review`

### Text updates

- `E:\aivideo\app\services\plot_first_pipeline.py` replacements=2
- `E:\aivideo\app\services\movie_story\highlight_runtime.py` replacements=1
- `E:\aivideo\app\services\movie_story\narration_engine.py` replacements=2
- `E:\aivideo\app\services\movie_story\narration_runtime.py` replacements=1
- `E:\aivideo\app\services\movie_story\two_round_feature_modes.py` replacements=1
- `E:\aivideo\app\services\movie_story\two_round_visual_narration.py` replacements=1
- `E:\aivideo\tests\test_generate_narration_script.py` replacements=1
- `E:\aivideo\tests\test_narration_quality_anti_recitation.py` replacements=1
- `E:\aivideo\tests\test_plot_understanding.py` replacements=2
- `E:\aivideo\docs\aivideo_coding_standards.md` replacements=1

## DONE-075 clean suffix reference fix round61b

- 修复 round61 文件改名后残留旧模块 token 的半完成状态。
- 修复上一版脚本占位符未替换错误。
- 重写 `tests/test_clean_suffix_service_names.py`，避免 guard 自己包含旧 token 字面量。
- 顺手将 tests 下旧 clean 后缀测试文件改成稳定文件名。
- 最后重新扫描 app/tests/tools，确认旧模块 token 已消失。
- manifest: `E:\aivideo-workspace\recycle\round61b_clean_suffix_fix_v2_20260527_194250\MANIFEST.json`
- 本轮不新增 wrapper、不保留兼容别名、不改业务逻辑、不改提示词、不新增 fallback。

### Renamed test files

- `E:\aivideo\tests\test_generate_narration_script_clean.py` -> `E:\aivideo\tests\test_generate_narration_script.py` | removed clean suffix from test filename
- `E:\aivideo\tests\test_plot_understanding_clean.py` -> `E:\aivideo\tests\test_plot_understanding.py` | removed clean suffix from test filename

### Module token updates

- no remaining module token updates

### Path text updates

- no test path references updated

## DONE-076 subtitle font path round62b

- 修复字幕字体默认值和路径解析问题：默认 `font_name` 不再是 workspace 下不存在的 `SimHei` stem。
- `generate_video.py` 现在允许真实绝对字体路径直接传给 MoviePy/Pillow，并校验字体可读。
- 短字体名仍只解析到 workspace fonts 下实际存在的同 stem `.ttf/.ttc/.otf`。
- 不复制/分发字体文件，不新增 unrelated fallback 字体。
- 新增 `tests/test_subtitle_font_path_resolution.py`。
- 本轮不改提示词。

### Changes

- schema default font already points to C:/Windows/Fonts/simhei.ttf
- added pathlib.Path import
- inserted _resolve_subtitle_font_path helper
- replaced workspace-only subtitle font join with resolver

## DONE-077 plot understanding loguru test stub round62c

- 修复 `tests/test_plot_understanding.py` 导入 `app.services.plot_understanding` 时，测试 loguru stub 缺少 `remove/add` 导致 `app.config` 初始化失败的问题。
- 只修改测试桩，不改 `app/config` 生产日志逻辑，不改 LLM 配置。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Changes

- inserted loguru-compatible test stub helper

## DONE-079 plot understanding loguru stub call round62c fix v2

- 修复上一版 round62c fix 的缩进插入错误。
- 使用 AST 定位 `_load_plot_understanding()` 中的目标 return 行，并用 return 行自身缩进插入 helper 调用。
- 只修改测试桩，不改 `app/config` 生产日志逻辑。
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Changes

- inserted helper call before target import using AST line number

## DONE-080 video font contract round63

- 根因：前端视频合成提交点硬编码 `font_name: "SimHei"`，当前 UI 没有合成字体输入框，用户无法手工修改。
- 修复：前端源码/构建产物中的 `font_name/fontName: "SimHei"` 改为 `C:/Windows/Fonts/simhei.ttf`。
- 后端任务边界增加精确历史默认值迁移：`SimHei` -> `C:/Windows/Fonts/simhei.ttf`。
- schema 默认值保持真实字体文件路径。
- 其它错误字体值不做通用 fallback，仍由 `generate_video.py` resolver 明确报错。
- manifest: `E:\aivideo-workspace\recycle\round63_video_font_contract_20260528_080839\MANIFEST.json`

### Schema

- schema default already canonical

### Task boundary

- inserted _canonicalize_video_font_name helper
- patched params.font_name -> subtitle_font mapping

### Frontend patches

- `web/src/pages/editor/Dubbing.tsx` replacements=1
- `web/dist/assets/index-mOsDh7xf.js` replacements=1

## DONE-081 refactor residue test filenames round64

- 处理 `remaining_refactor_residue_after_round63` 中真正属于历史迁移/轮次命名的测试文件。
- 保留 `two_round` 测试命名，因为 `two_round` 是当前正式业务链路名称，不是 refactor round 残留。
- 保留 `stage_index` 测试命名，因为 `stage_index` 是 runtime audit 字段，不是 migration stage 残留。
- 新增 `tests/test_refactor_residue_test_filenames.py` 作为更精确的文件名合同。
- manifest: `E:\aivideo-workspace\recycle\round64_refactor_residue_test_names_20260528_092420\MANIFEST.json`
- 本轮不改业务代码、不改主链路、不改提示词。

### Renames

- `tests/test_movie_story_stage_a_runtime_audit.py` -> `tests/test_movie_story_runtime_audit_contract.py`
- `tests/test_movie_story_three_stage_refactor.py` -> `tests/test_movie_story_pipeline_phase_contract.py`
- `tests/test_round_named_guard_tests_stabilized.py` -> `tests/test_test_filename_residue_contract.py`

## DONE-083 LLM runtime config migration round65 fix

- 修复 round65 半完成状态：`llm_config.py` 已迁入 `app/services/llm/runtime_config.py`，但新 guard 测试自身包含旧模块字符串导致脚本拒绝完成。
- 重写 `tests/test_llm_runtime_config_migration.py`，用动态拼接方式检查旧模块 token，避免 guard 自身成为误报。
- 再次确认 `app/services/llm_config.py` 不存在，`app/services/llm/runtime_config.py` 存在。
- manifest: `E:\aivideo-workspace\recycle\round65_llm_runtime_config_fix_20260528_094532\MANIFEST.json`
- 本轮不改 LLM 配置读取逻辑，不改 provider/unified_service，不新增 fallback，不改提示词。

### Extra text updates

- no additional import text updates

## DONE-085 short drama package lowercase rename round66 fix

- 修复 round66 半完成状态：目录已经迁移，但新 package guard 自身包含旧路径字面量导致自检失败。
- 重写 `tests/test_short_drama_packages_contract.py` 与 `tests/test_short_drama_package_names_contract.py`，旧路径通过动态拼接生成，避免 guard 自身误报。
- 再次确认 `app/services/SDE` 与 `app/services/SDP` 不存在，新小写 package 存在。
- manifest: `E:\aivideo-workspace\recycle\round66_short_drama_package_rename_fix_20260528_102417\MANIFEST.json`
- 本轮不改业务逻辑、不改提示词、不新增 fallback。

### Extra text updates

- no additional text references needed

## DONE-086 clip_video_unified task dir round67b

- 根因：`task._run_pipeline()` 已有外层 job `task_id`，但调用 `clip_video_unified()` 时没有传 `output_dir/task_id`。
- 结果：音频/字幕/最终合成在 `workspace/tasks/<job_uuid>`，而裁剪片段落到项目主树 `storage/temp/clip_video_unified/<md5>`。
- 修复：`task.py` 显式传入 `utils.task_dir(os.path.join(task_id, "clip_video_unified"))` 与 `task_id=task_id`。
- 直接调用 `clip_video_unified()` 的默认目录也改为 `utils.temp_dir(os.path.join("clip_video_unified", task_id))`，不再回落到 repo storage。
- 旧项目主树临时目录已移动到 recycle：moved=True
- 新增 `tests\test_clip_video_unified_task_dir_contract.py`。
- manifest: `E:\aivideo-workspace\recycle\round67b_clip_video_unified_task_dir_20260528_113644\MANIFEST.json`
- 本轮不拆大文件、不改提示词、不新增 fallback。

### Changes

- `app/services/task.py`: patched clip_video_unified call to use workspace task dir
- `app/services/clip_video.py`: replaced repo storage/temp default dir lines 1017-1020; added utils import
- `tests/test_clip_video_unified_task_dir_contract.py`: wrote task-dir contract guard

## DONE-087 narration plain text sanitizer round68

- 根因：raw_srt/two_round 最终文案中允许模型保留 `开场/分论点/回响/收尾` 结构；旧清洗只覆盖部分 raw_srt 解析，job 返回层仍只做 strip。
- 修复：新增 `app/services/narration_text_sanitizer.py`，最终 narration/text 字段统一清理 Markdown 分隔线和结构标签。
- 生成链路：`_raw_srt_clean_narration()` 返回前调用最终 sanitizer。
- 返回链路：`jobs.py` 与 `local_job_runner.py` 归一化 script_items 时清洗 narration。
- 新增 `tests/test_narration_plain_text_sanitizer.py`。
- 本次 fix 修正了 round68 原脚本把顶层 import 插入局部 import 后导致的缩进问题。
- manifest: `E:\aivideo-workspace\recycle\round68_narration_plain_text_sanitizer_fix_20260528_120911\MANIFEST.json`
- 本轮不改提示词、不拆大文件、不新增 fallback。

### Changes

- `app/services/narration_text_sanitizer.py` changed=True: ensured shared deliverable narration sanitizer
- `app/services/generate_narration_script.py` changed=True: patched _raw_srt_clean_narration return line 2255; added sanitizer import
- `app/api/routers/jobs.py` changed=True: inserted sanitizer after narration strip blocks: 1; added sanitizer import
- `app/services/local_job_runner.py` changed=True: inserted sanitizer after narration strip blocks: 1; added sanitizer import
- `tests/test_narration_plain_text_sanitizer.py` changed=True: wrote sanitizer contract tests

## DONE-088 narration sanitizer paragraph/entry fix round68

- 修复 round68 sanitizer 测试失败。
- sanitizer 删除 `---/--` 等 Markdown 分隔线时保留原有空行段落边界。
- `_raw_srt_clean_narration()` 函数入口先做 deliverable sanitizer，避免旧清洗逻辑在分隔线处截断后丢掉后文。
- 保留函数出口 sanitizer，最终返回仍满足纯正文合同。
- manifest: `E:\aivideo-workspace\recycle\round68_narration_sanitizer_fix2_20260528_121348\MANIFEST.json`
- 本轮不改提示词、不拆大文件、不新增 fallback。

### Changes

- `app/services/narration_text_sanitizer.py` changed=True: rewrote sanitizer to preserve paragraph breaks
- `app/services/generate_narration_script.py` changed=True: inserted entry sanitizer for argument text

## DONE-089 two-round artifact sanitizer round69

- 根因：`jobs.py` 与 `local_job_runner.py` 已清洗返回层，但 `two_round_feature_modes.py` 写 artifact JSON 前未清洗。
- 修复：`_write_json()` 写入前递归清洗 `narration/text/source_text/title/section_title`。
- 新增 `sanitize_deliverable_title_text()`，当 title 是纯结构标签时，用正文开头生成可显示标题。
- 本次 fix 兼容 `_write_json` 第二参数不叫 `payload` 的现有签名。
- 新增/重写 `tests\test_two_round_artifact_sanitizer_contract.py`。
- manifest: `E:\aivideo-workspace\recycle\round69_two_round_artifact_sanitizer_fix_20260528_144706\MANIFEST.json`
- 本轮不改 prompt、不拆大文件、不新增 fallback。

### Changes

- `app/services/narration_text_sanitizer.py` changed=False: title sanitizer already present
- `app/services/movie_story/two_round_feature_modes.py` changed=False: already patched _write_json payload argument: data
- `tests/test_two_round_artifact_sanitizer_contract.py` changed=True: rewrote flexible two-round artifact sanitizer tests

## DONE-090 historical narration artifact repair round70

- round68/round69 已修复新生成文案的清洗链路。
- 本轮只修复历史任务产物中已落盘的脏 JSON 字段。
- 处理文件名：`['movie_story_script.json', 'movie_story_script_highlight_narration_segments.json', 'movie_story_script_highlights.json']`。
- changed_files: 3
- field_changes: 35
- manifest: `E:\aivideo-workspace\recycle\round70_historical_narration_artifact_repair_20260528_161720\MANIFEST.json`
- 不处理 prompt/response/debug/frame/shot boundary 等调试产物。
- 不改提示词、不拆大文件、不新增 fallback。

## DONE-092 short video batch theme-only MVP round72

- 新增/更新 `app/services/movie_story/short_video_batch/` 独立包。
- MVP 从现有 highlight-like segments 召回短视频候选并生成 `short_video_candidates.json` / `short_video_plans.json`。
- 当前阶段不生成完整解说文案；每条 short 只包含 `title` 和 `theme_or_emo_line`。
- 新增/更新 `tests/test_short_video_batch_mvp_contract.py`。
- 新增/更新 `docs/decisions/ADR-010-short-video-batch.md`。
- 本轮只建立合同和规划产物，不接 API、不接前端、不接批量渲染。
- manifest: `E:\aivideo-workspace\recycle\round72_short_video_batch_theme_only_mvp_20260529_101235\MANIFEST.json`

## DONE-093 short video batch source_segments naming round73

- 修正不清楚的 `highlight-like segments` 表达。
- 正式输入概念统一为 `source_segments`。
- `source_segments` 可以来自旧 highlight artifact、用户手选片段或未来事件检测器；highlight 只是生产者之一，不是正式字段名。
- 不保留旧 `*_from_highlights` 兼容入口，直接改正式命名。
- 当前阶段仍然只输出 `title` + `theme_or_emo_line`，不生成完整解说。
- manifest: `E:\aivideo-workspace\recycle\round73_short_video_batch_source_segments_20260529_130058\MANIFEST.json`

## DONE-094 short video batch naming guard fix round73

- 修复 `tests/test_short_video_batch_mvp_contract.py::test_no_highlight_like_public_naming_in_short_video_batch`。
- 原因：源码注释/CONTEXT 仍残留旧的模糊命名描述。
- 处理：短视频批量链路源码统一使用 `source_segments` 表达，不在正式源码中保留旧模糊术语。
- 不恢复旧 `*_from_highlights` 入口。
- 不生成完整解说、不接 API/前端/渲染。
- manifest: `E:\aivideo-workspace\recycle\round73_short_video_batch_guard_fix_20260529_132038\MANIFEST.json`

## DONE-095 short video batch artifact adapter round74

- 新增 `source_segment_adapter.py`，从显式 movie_story artifact JSON 转换出 `source_segments`。
- 新增 `tools/build_short_video_batch_from_movie_story_artifact.py`，用于真实任务产物手动验证。
- 新增 `tests/test_short_video_batch_source_segment_adapter.py`。
- 仍然只生成 `short_video_candidates.json` / `short_video_plans.json`。
- 不生成完整解说、不调用 LLM、不接 API/前端/渲染。
- manifest: `E:\aivideo-workspace\recycle\round74_short_video_batch_artifact_adapter_20260529_143316\MANIFEST.json`

