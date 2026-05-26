# PENDING.md — aivideo 待完成任务

> 本文件是给 ChatGPT / Claude Code / Cursor 的任务队列。开始任务前先阅读 `CLAUDE.md`、相关 ADR、设计文档和目标文件 `__CONTEXT__`。

## 🔴 高优先级

### [PEND-101] 接通 two_round_visual 第一轮多模态链路

**状态**：已完成首版骨架，待真实端到端联调  
**相关文档**：

- `docs/movie_story_two_round_visual_design.md`
- `docs/decisions/ADR-005-two-round-visual-first-round-multimodal.md`
- `docs/status/two_round_visual_status.md`

**目标**：

实现真正的 `two_round_visual`：第一轮提示词前准备视觉证据，第一轮多模态理解全片，第二轮文本写作并选择片段，第二轮后直接剪辑。

**关键约束**：

```text
visual_focus_segments 不是 AI 推荐高光
visual_focus_segments 只是详细抽帧区域
第一轮大模型输出全片结构理解，不输出高光推荐
第二轮后不人工复选
失败直接报错，不 fallback
```

**影响文件候选**：

- `app/services/movie_story/two_round_feature_modes.py`
- `app/services/movie_story/two_round_narration.py`
- `app/services/movie_story/visual_frame_sampler.py`
- `app/services/movie_story/two_round_visual_narration.py`（待新增）
- `app/services/movie_story/two_round_visual_input_packager.py`（待新增）
- `app/services/movie_story/visual_focus_segments.py`（待新增）
- `tests/movie_story/*`

**验收标准**：

```text
1. visual_enabled=True 不再调用 text-only fake chain。
2. 缺 video_path / 视觉模型 / 抽帧结果时直接 raise。
3. 第一轮输入包含全片低密度帧和 visual_focus_segments 详细帧。
4. 第一轮输出仍遵守 ANALYSIS_PROMPT_TEMPLATE 的结构理解职责。
5. 第二轮仍复用 WRITER_PROMPT_TEMPLATE 或其显式升级版本。
6. 所有新增模块有 tests。
```

---

### [PEND-102] 修正 two_round_visual 旧定义文案与注释

**状态**：已完成首版同步

**目标**：

把前后端所有“two_round_visual = text-only 双轮后置抽帧”的旧定义改成“第一轮多模态增强”。

**影响文件候选**：

- `app/services/movie_story/two_round_feature_modes.py`
- `app/api/schemas/jobs.py`
- `app/services/local_job_runner.py`
- `web/src/components/workspace/ConfigStep.tsx`
- `web/src/lib/api.ts`
- 相关 tests

**验收标准**：

```text
1. 不再把 two_round_visual 描述为“先生成文案，再抽帧”。
2. 不再把 visual_focus_segments 描述为 AI 推荐高光。
3. 前端入口可以保留，但文案必须说明是第一轮多模态增强。
4. 测试名称和断言不再使用旧定义。
```

---

### [PEND-103] 迁移 native 中稳定视觉工具能力

**状态**：未开始

**目标**：

从 native 源码中只迁移稳定、低成本、确定性的视觉基础能力，用于新 `two_round_visual`。

**允许迁移**：

```text
镜头切分
场景切分
关键帧抽取
视频元信息读取
时间轴工具
```

**禁止迁移**：

```text
native 主流程
native LLM 编排
legacy fallback
native result contract
```

**验收标准**：

```text
1. 新模块命名不再带 native 主流程含义。
2. 不恢复 native/legacy 路由。
3. 工具有独立 tests。
4. 失败直接 raise。
```

---

### [PEND-104] 为新增模块补充 __CONTEXT__ 与 ADR 引用

**状态**：已完成首版新增模块

**目标**：

后续新增 `two_round_visual_*` 模块时，文件头必须包含 `__CONTEXT__`，并在 decisions 中引用 ADR-005。

**验收标准**：

```text
1. 新建 Python 文件有规定文件头。
2. 新建 Python 文件有 __CONTEXT__。
3. ai_constraints 写明禁止 fallback、禁止恢复 native/legacy。
4. pending 写明后续待优化事项。
```

## 🟡 中优先级

### [PEND-201] 更新 two_round 第二轮提示词与剪辑契约对齐

**状态**：待分析

**背景**：

当前 `WRITER_PROMPT_TEMPLATE` 会让第二轮从整集范围内选择片段。后续需要确认第二轮输出片段如何与剪辑合成模块对齐。

**注意**：

不要把第一轮前的 `visual_focus_segments` 当作第二轮必须采用的片段。大模型两轮链负责最终文案和片段选择。

---


## ✅ 已完成

### [DONE-001] 冻结 two_round_visual 新定义

**完成日期**：2026-05-22

**结论**：

```text
two_round_visual = 第一轮多模态增强
visual_focus_segments = 第一轮前详细抽帧区域，不是 AI 推荐高光
第二轮后直接剪辑，不人工复选
失败不 fallback
```

### [DONE-002] 建立 AI 接手上下文文档

**完成日期**：2026-05-22

**新增文件**：

- `CLAUDE.md`
- `docs/movie_story_two_round_visual_design.md`
- `docs/decisions/ADR-005-two-round-visual-first-round-multimodal.md`
- `docs/status/two_round_visual_status.md`
- `PENDING.md`

### [DONE-003] 接通 two_round_visual 第一轮多模态骨架

**完成日期**：2026-05-22

**新增/修改内容**：

- 新增 `visual_focus_segments.py`
- 新增 `two_round_visual_input_packager.py`
- 新增 `two_round_visual_narration.py`
- 扩展 `visual_frame_sampler.py` 的 first-round 抽帧接口
- `two_round_feature_modes.py` 的 visual 模式不再 fake-run text-only 链
- `local_job_runner.py` 不再把 two_round_visual 自动等同于后置视觉证据包
- 前端与 API schema 注释同步为第一轮多模态增强

**仍需后续联调**：

```text
真实视频抽帧
真实 vision_litellm 配置
剪辑合成契约
native 稳定镜头/场景切分工具迁移
```

### [DONE-004] 清理 selected-highlight 后置视觉证据链

**完成日期**：2026-05-25

**方案**：

- 删除正式主流程中的 `movie_story_enable_visual_evidence` 旧开关。
- 删除 `local_job_runner.py` 对 selected-highlight 后置抽帧复核 workflow 的调用。
- 将 `selected_highlight_visual_evidence_workflow.py` 和对应旧测试移入 `deprecated/legacy_archive/`。
- 未迁移该 workflow 内部代码：它围绕第二轮后 selected highlights 复核设计，
  不服务当前正式 two_round_visual 的第一轮前成本受控视觉证据准备。
- 归档旧 API 测试，防止它们要求恢复已废弃的 compatibility wrapper。
- 新增 guard 测试，防止旧开关或旧 workflow 再次被接回正式主流程。



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


## [PEND-STAGE3D-PROMPT-HEADING-TEST-REFACTOR]
- Status: applied by `fix_visual_prompt_heading_tests_and_refactor_v1.py`.
- Reason: prompt-facing headings were intentionally renamed and extra two_round_visual rules removed, but tests still asserted old labels.
- Refactor: split `generate_two_round_visual_narration_items()` into smaller helpers to satisfy the <=80-line function rule.
- Guard: run compileall, `tools/audit_two_round_visual_code_rules.py`, and focused pytest before real task runs.

### [DONE-005] 修正 visual_focus_segments API 到运行时契约

**完成日期**：2026-05-26

**方案**：

- `movie_story_visual_focus_segments` 作为正式 API 字段进入 `two_round_visual` 运行时。
- `unified_entry.py` 明确只接受当前正式 movie_story 主流程。
- 旧 native/legacy movie_story 标签拒绝进入正式主流程，不再迁移为当前模式。
- FunASR 测试去除本机固定 wav 路径依赖。

### [DONE-006] 全量测试契约收敛到稳定基线

**完成日期**：2026-05-26

**结果**：

```text
333 passed, 1 skipped, 1 warning
```

**方案**：

- 修正 `json_utils` 对 fenced JSON 和双大括号 JSON 的解析。
- 修正 FFmpeg 相关测试 mock，使其符合当前 `run_cancellable` 调用契约。
- 更新旧 native/legacy 测试，防止旧 movie_story 主流程回流。
- 修正 audit stage 命名空间测试期望。
- 未改动基础双轮提示词和视觉增强提示词。

### [DONE-007] 消除 Pydantic warning 并修正 two_round_visual 审计规则

**完成日期**：2026-05-26

**结果**：

```text
334 passed, 1 skipped
```

**方案**：

- `app/models/schema.py` 改为 Pydantic v2 `ConfigDict` 配置，消除 class-based config warning。
- `tools/audit_two_round_visual_code_rules.py` 去除旧的 80 行函数硬限制。
- 审计工具改为 AST 级检查 `print`、`logging`、`_ORIGINAL_*` alias 和类型注解，避免把文档/字符串/测试 guard 误判为正式源码违规。

## DONE-008 functional contracts round11

- 新增 `app/services/movie_story/functional_contracts.py`，用数据契约固定当前三条正式主流程、可复用支撑能力、长视频拆短视频待审模块、旧 movie_story native/legacy 待退休候选。
- 新增 `tests/movie_story/test_functional_contracts.py`，保护旧 movie_story native/legacy 主流程不会作为新代码 active reference 回流。
- 本轮不改提示词、不改运行调度、不删除旧模块，只为后续拆函数和迁移提供引用边界。

## DONE-009 functional boundaries round12

- 新增 `app/services/movie_story/functional_boundaries.py`，把 round11 静态功能契约封装成可复用函数。
- 新增 `tests/movie_story/test_functional_boundaries.py`，保护当前主流程模块、支撑模块、待退休模块和路径转换规则。
- 后续自动补丁新增 movie_story 依赖时，可使用 `assert_new_code_may_reference(module, reason=...)` 防止旧 native/legacy 主流程回流。

