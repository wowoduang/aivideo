# ADR-005: two_round_visual 第一轮多模态增强

**日期**：2026-05-22  
**状态**：Active  
**影响文件**：

- `app/services/movie_story/two_round_feature_modes.py`
- `app/services/movie_story/two_round_narration.py`
- `app/services/movie_story/visual_frame_sampler.py`
- `app/services/movie_story/*visual*`
- `app/services/local_job_runner.py`
- `app/api/schemas/jobs.py`
- `web/src/components/workspace/ConfigStep.tsx`
- `tests/movie_story/*`

## 背景

text-only `two_round` 链路在影视剧字幕场景中能完成结构理解和文案写作，但容易搞混说话主体和说话对象，例如：

```text
谁在说话
这句话对谁说
谁在动作
画面里有哪些人
“你/我/他”对应哪个人物
```

仅靠字幕无法稳定解决这些问题，需要在第一轮结构理解前补充视觉证据。

## 决策

新增并重新定义 `two_round_visual`：

```text
第一轮提示词前：后端准备视觉证据
第一轮：多模态大模型理解全片
第二轮：文本大模型写文案并选择片段
第二轮后：直接剪辑合成 / 导出
```

后端第一轮前准备两类视觉证据：

```text
全片 scene_segments 低密度抽帧
visual_focus_segments 详细抽帧
```

`visual_focus_segments` 只是详细抽帧区域，不是 AI 推荐高光，不是最终剪辑片段。

## 拒绝方案

### 拒绝方案 1：text-only 双轮后再抽帧

拒绝旧定义：

```text
text-only two_round 先生成文案
  → 再对 selected highlights 抽帧
  → 作为 two_round_visual
```

原因：这不能解决第一轮理解时的说话主体/对象误判。

### 拒绝方案 2：第二轮后人工复选

拒绝在第二轮之后增加人工复选流程。

原因：两轮提示词已经要求大模型理解、写文案、选片段。第二轮后如果再人工修补，会让系统责任边界混乱。效果不好应回到第一轮前补视觉证据并完整重跑。

### 拒绝方案 3：fallback 到 text-only / native / legacy

`two_round_visual` 缺视觉模型、缺视频、抽帧失败或多模态返回异常时，必须直接报错。

## 结果

预期收益：

```text
减少说话主体/对象误判
减少人物关系误判
让第一轮结构分析能结合画面证据
保持第二轮文案链路稳定复用
```

成本控制：

```text
全片只低密度抽帧
仅对 visual_focus_segments 详细抽帧
不提前做人脸聚类、姿态识别、物件识别等复杂视觉系统
```

## legacy / native 处理

legacy / native 主流程已经从项目主链路移除，源码暂时保留。

允许迁移 native 中稳定确定性的视觉工具：

```text
镜头切分
场景切分
关键帧抽取
视频元信息读取
时间轴工具
```

迁移后必须重命名并整理到新模块，不能恢复 native 主流程，不能作为 fallback。

## AI 不得推翻的约束

```text
1. two_round_visual = 第一轮多模态增强，不是后置抽帧证据包。
2. visual_focus_segments 不是 AI 推荐高光，不是最终剪辑片段。
3. 第一轮大模型输出全片结构理解，不输出高光推荐。
4. 第二轮大模型写文案并选择片段。
5. 第二轮后直接剪辑，不人工复选。
6. 效果不好时，补选 visual_focus_segments 并完整重跑。
7. 不 fallback 到 text-only / native / legacy。
```
