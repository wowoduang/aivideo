# two_round_visual 当前状态

**最后更新**：2026-05-26  
**状态**：视觉增强链已达到及格测试状态；本轮完成旧后置 selected-highlight 视觉证据链主流程清理

## 1. 当前结论

`two_round_visual` 的正确方向已经确定：

```text
第一轮前准备视觉证据
  → 第一轮多模态理解全片
  → 第二轮文本写作并选片段
  → 第二轮后直接剪辑合成
```

当前不再接受旧定义：

```text
text-only two_round 生成文案后再抽帧
```

## 2. 已确认源码事实

当前双轮链提示词位于：

```text
app/services/movie_story/two_round_narration.py
```

关键常量：

```text
ANALYSIS_PROMPT_TEMPLATE
WRITER_PROMPT_TEMPLATE
```

当前 `two_round_visual` 已从 guard 改为真实路由：

```text
visual_enabled=True
  → generate_two_round_visual_narration_items()
  → visual_focus_segments + 全片低密度帧 + 重点片段详细帧
  → 第一轮多模态理解
  → 第二轮文本写作
```

测试已覆盖：visual 模式不会调用 text-only raw_srt fake chain。

## 3. 已完成设计决策

```text
1. two_round_visual 是第一轮多模态增强。
2. 目标是解决说话主体、说话对象、人物动作和场景人物关系误判。
3. 第一轮前选择的是 visual_focus_segments，不是 AI 推荐高光。
4. visual_focus_segments 只是详细抽帧区域。
5. 全片保留低密度抽帧，visual_focus_segments 做详细抽帧。
6. 第一轮输出全片结构理解。
7. 第二轮写文案并选择片段。
8. 第二轮后直接剪辑，不人工复选。
9. 效果不好时，补选 visual_focus_segments 后完整重跑。
10. legacy/native 主流程不恢复，只迁移确定性视觉工具。
11. 失败直接报错，不 fallback。
```

## 4. 本轮已完成实现

```text
1. 新增 visual_focus_segments.py。
2. 新增 two_round_visual_input_packager.py。
3. 新增 two_round_visual_narration.py。
4. visual_timeline_sampler.py 提供全片低密度帧和 visual_focus_segments 详细帧接口。
5. two_round_feature_modes.py 接通 visual_enabled=True 到真实 two_round_visual 路由。
6. local_job_runner.py 删除旧 selected-highlight 后置视觉证据处理器。
7. API schema 和前端删除 movie_story_enable_visual_evidence 旧开关。
8. selected_highlight_visual_evidence_workflow 已移入 deprecated/legacy_archive，不再属于正式主流程。
9. 新增/更新 tests，覆盖 visual 模式不调用 text-only fake chain，并防止旧后置抽帧链回流。
```

## 5. 未完成实现

```text
1. 与真实视频、真实视觉模型配置做端到端联调。
2. 从 native 迁移更稳定的镜头切分/场景切分工具，替换当前 raw_srt 粗场景来源。
3. 如果需要前端第一轮前人工补选 visual_focus_segments，需要接 UI 交互字段。
4. 检查第二轮输出与剪辑合成模块的最终片段契约。
5. 长视频拆多个短视频流程继续作为正式产品主流程收敛，避免借旧 native/legacy 主流程实现。
```

## 6. 风险点

```text
1. 把 visual_focus_segments 误写成 AI 推荐高光。
2. 把第二轮后人工复选重新加回来。
3. 把 deprecated/legacy_archive 中的旧 selected_highlight_visual_evidence_workflow 重新接回主流程。
4. 缺视觉配置时 fallback 到 text-only two_round。
5. 从 native 迁移时恢复了 native 主流程。
6. 第二轮提示词选出的片段与剪辑合成契约没有对齐。
```

## 7. 新会话接手提示

接手本任务时，先读：

```text
CLAUDE.md
docs/movie_story_two_round_visual_design.md
docs/decisions/ADR-005-two-round-visual-first-round-multimodal.md
PENDING.md
目标文件 __CONTEXT__
```

然后先复述：

```text
visual_focus_segments 不是 AI 推荐高光，只是详细抽帧区域；
第二轮后不复选，直接剪辑；
失败不 fallback。
```

## 8. 2026-05-26 后续收敛状态

```text
round2：已完成 movie_story_visual_focus_segments API → runtime 映射，unified_entry 只保留当前正式主流程，旧 native/legacy 标签拒绝进入 movie_story 主流程。
round3：已修正全量测试契约，确认当前稳定测试基线为 333 passed, 1 skipped, 1 warning。
```

后续不得为了旧测试或旧脚本恢复 selected-highlight 后置视觉证据链，也不得把 legacy/native 重新接回 movie_story 主流程。

