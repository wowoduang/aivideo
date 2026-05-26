# aivideo 架构交接分析：基础双轮链、视觉增强链与长视频拆短视频主流程

**状态日期**：2026-05-26  
**当前稳定测试基线**：`333 passed, 1 skipped, 1 warning`

## 1. 当前正式主流程

当前 aivideo 只把以下三条作为正式主流程：

```text
1. 基础双轮链
   text-only two_round：完整字幕 → 第一轮结构理解 → 第二轮文案与片段时间码。

2. 视觉增强链
   two_round_visual：第一轮前本地低成本音视频/视觉证据准备 → 第一轮多模态理解 → 第二轮文本写作 → 直接剪辑。

3. 长视频拆短视频流程
   类似抖音/剪映/CapCut 的“长视频生成多个短视频”产品方向。
```

`legacy` 和 `native` 不是正式主流程，也不是 fallback。它们只临时保留，用于提取有价值的确定性模块；价值模块迁移完成后，应进入项目回收站或删除。

## 2. two_round_visual 的准确定义

`two_round_visual` 的目标不是“多看一遍画面”，而是解决基础 text-only 双轮链容易搞错的人物关系、说话人、说话对象、动作归属问题。

正式链路是：

```text
本地音视频/视觉证据准备
  → 生成全片低密度帧 + visual_focus_segments 详细帧
  → 第一轮多模态模型结合完整字幕和少量高价值视觉证据理解全片
  → 第二轮文本模型写文案并给出片段时间码
  → 第二轮后直接剪辑/导出
```

明确禁止：

```text
第二轮后再对 selected_highlights 抽帧
第二轮后人工复选
把 visual_focus_segments 当最终剪辑片段
缺视觉配置时 fallback 到 text-only two_round
恢复 selected_highlight_visual_evidence_workflow 主流程
```

## 3. visual_focus_segments 的准确定义

`visual_focus_segments` 是第一轮前需要详细抽帧的视觉重点时间段。它不是高光，不是最终短视频片段，也不是本地字幕语义分析结果。

本地层主要使用：

```text
shot/scene 边界
画面变化
音频/说话轮次等可计算信号
关键帧预算
字幕时间轴作为对齐和分窗锚点
```

字幕在本地层只用于时间对齐、分窗、对白密度/轮次等可计算信号；剧情含义、人物关系、代词指向交给第一轮多模态大模型理解。

## 4. 已完成的三轮工程收敛

### round1：删除旧后置视觉证据链

- 删除 `movie_story_enable_visual_evidence` 正式主流程旧开关。
- 删除 `local_job_runner.py` 对 selected-highlight 后置抽帧复核 workflow 的调用。
- 将 `selected_highlight_visual_evidence_workflow.py` 和旧测试移入 `deprecated/legacy_archive/`。
- 新增 guard 测试，防止旧后置抽帧链回流。

### round2：修正主流程契约

- `movie_story_visual_focus_segments` 已接入运行时。
- `unified_entry.py` 改成当前正式主流程入口。
- 旧 native/legacy movie_story 标签改为拒绝，不再迁移到当前主流程。
- FunASR 测试去除本机固定 `E:/.../test.wav` 依赖。
- `tests/movie_story + tests/test_movie_story_unified_entry.py`：`97 passed`。

### round3：修正全量测试契约

- 修复 `json_utils`。
- 修正 subprocess 测试 mock 与 `run_cancellable` 的契约。
- 清理旧 native/legacy 测试期望。
- 修正 audit stage 命名空间测试。
- 不改两轮提示词。
- 全量测试：`333 passed, 1 skipped, 1 warning`。

## 5. 后续代码规则

后续 AI 写代码前必须遵守：

```text
不改基础双轮提示词，除非用户明确要求。
不改视觉增强提示词，除非用户明确要求。
不新增 fallback，不静默吞异常。
不加 compatibility wrapper 来兼容旧测试。
不恢复 native/legacy movie_story 主流程。
优先直接重构、删除错误残留、统一字段契约。
代码按功能模块化，不机械卡 80 行，但必须职责清晰、可测试。
```

## 6. 推荐验收命令

```bash
cd /e/aivideo
python -m compileall -q app tests
python -m pytest -q tests
```

当前稳定基线：

```text
333 passed, 1 skipped, 1 warning
```

唯一 warning 是 Pydantic V2 class-based config 弃用提示，暂不影响当前主流程。

## 7. 新会话开场提示

建议在新会话开头粘贴：

```text
请先阅读 docs/status/aivideo_architecture_handoff_analysis.md。
当前 aivideo 正式主流程只有：基础双轮链、视觉增强链、长视频拆短视频流程。
不要改两轮提示词，不要恢复 legacy/native 主流程，不要 fallback，不要 compatibility wrapper。
two_round_visual 是第一轮前本地视觉证据准备 + 第一轮多模态理解，不是第二轮后 selected-highlight 抽帧。
当前测试基线：333 passed, 1 skipped, 1 warning。
```
