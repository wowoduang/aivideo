# two_round_visual 当前状态

**最后更新**：2026-05-22  
**状态**：设计冻结，等待实现

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

当前 `two_round_visual` 已有 guard，防止它假跑 text-only 链：

```text
two_round_visual multimodal first-round pipeline is not wired yet;
refusing to run the text-only two_round chain as a fake visual mode.
```

因此，当前失败是有意保护，不是普通 bug。

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

## 4. 未完成实现

```text
1. visual_focus_segments 自动选择模块。
2. 第一轮前 visual_focus_segments 复选 / 补选状态机制。
3. 全片低密度抽帧接口。
4. visual_focus_segments 详细抽帧接口。
5. visual_first_round_input 打包器。
6. 第一轮多模态调用入口。
7. 第二轮与现有 writer prompt 的稳定复用。
8. 前端文案从旧定义改为新定义。
9. API schema 注释同步。
10. tests 按新定义重写。
```

## 5. 推荐实现顺序

```text
1. 先修文档、注释、前端文案和 schema 注释，消灭旧定义。
2. 从 native 迁移或重写确定性 shot / scene / frame 工具能力。
3. 新增 visual_focus_segments 模块。
4. 新增 visual_first_round_input packager。
5. 新增 two_round_visual_narration 入口。
6. 在 two_round_feature_modes 中接通 visual_enabled=True 路由。
7. 补充 tests，确保不调用 text-only fake chain。
8. 更新 PENDING.md 与本 status 文档。
```

## 6. 风险点

```text
1. 把 visual_focus_segments 误写成 AI 推荐高光。
2. 把第二轮后人工复选重新加回来。
3. 把旧 selected_highlight_visual_evidence_workflow 当成 two_round_visual 主流程。
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
