# PENDING.md — aivideo 待完成任务

> 本文件是给 ChatGPT / Claude Code / Cursor 的任务队列。开始任务前先阅读 `CLAUDE.md`、相关 ADR、设计文档和目标文件 `__CONTEXT__`。

## 🔴 高优先级

### [PEND-101] 接通 two_round_visual 第一轮多模态链路

**状态**：未开始  
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

**状态**：未开始

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

**状态**：未开始

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

### [PEND-202] 清理 selected_highlight_visual_evidence_workflow 的定位

**状态**：待分析

**背景**：

旧链路中存在后置 selected highlight 视觉证据包。该模块不应再被当作 `two_round_visual` 主流程。

**目标**：

明确它是后置复核/历史遗留能力，或迁移其中可复用的抽帧工具能力。

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
