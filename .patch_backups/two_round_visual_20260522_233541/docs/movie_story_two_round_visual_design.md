# movie_story two_round_visual 设计冻结文档

**状态**：Active / 设计冻结，代码实现进行中  
**适用范围**：`app/services/movie_story`、前端 movie_story 配置、相关 tests、后续剪辑合成链路  
**最后更新**：2026-05-22

## 1. 背景

现有 text-only `two_round` 链路能够完成大部分结构理解和解说文案生成，但在影视剧字幕场景中存在一个高频问题：

```text
只看字幕时，大模型容易搞混说话主体和说话对象。
```

典型错误包括：

```text
不知道是谁在说话
不知道这句话对谁说
把“你/我/他”指错人物
看不清场景里有哪些人
把某个动作归到错误人物身上
误判人物关系或同框关系
```

`two_round_visual` 的目的不是单纯“增加画面理解”，而是用低成本视觉证据帮助第一轮模型看清楚全片，从而减少上述误判。

## 2. 最终定义

`two_round_visual` 表示：

```text
后端第一轮前准备视觉证据
  → 第一轮多模态大模型理解全片
  → 第二轮文本大模型写文案并选择片段
  → 第二轮后直接剪辑合成
```

后端第一轮前只负责“让大模型看清楚”；大模型两轮链负责“理解、写文案、选片段”；第二轮后直接剪辑。

如果结果不好，不在第二轮后补人工复选，而是优化：

```text
visual_focus_segments 选择策略
视觉证据打包
第一轮提示词
第二轮提示词
```

然后完整重新跑一次。

## 3. 明确拒绝的旧定义

旧定义曾经把 `two_round_visual` 理解为：

```text
text-only two_round 先跑完
  → 得到文案 / highlights
  → 再对 selected highlights 抽帧
  → 生成后置视觉证据包
```

该定义已经废弃。

新的 `two_round_visual` 不允许假装跑 text-only 链，也不允许在缺视觉模型或抽帧失败时 fallback 到 text-only。

## 4. visual_focus_segments

### 4.1 定义

`visual_focus_segments` 是第一轮提示词发送前，由后端自动选择或用户补选的“视觉重点片段 / 详细抽帧区域”。

它只用于决定哪些时间段需要抽更详细的帧。

### 4.2 它是什么

```text
详细抽帧区域
第一轮视觉证据重点区域
帮助第一轮模型看清人物、动作、说话对象、场景关系的时间段
```

### 4.3 它不是什么

```text
不是 AI 推荐高光
不是最终剪辑片段
不是最终文案片段
不是第二轮输出片段
不是大模型必须采用的片段
不是用户最终确认的剪辑结果
```

产品层可以继续使用“高光 / 精彩片段”作为业务叫法，但后端代码和文档必须避免把 `visual_focus_segments` 写成“AI 推荐高光”。

## 5. 抽帧策略

第一阶段采用分层抽帧，平衡成本和效果：

```text
全片 / 所有 scene_segments：低密度抽帧
visual_focus_segments：详细抽帧
```

### 5.1 全片低密度抽帧

目的：给第一轮多模态模型建立全片视觉上下文。

建议策略：

```text
每个 scene segment 抽 1 张代表帧
长场景可抽 2 张
设置总帧数上限，避免成本失控
```

### 5.2 visual_focus_segments 详细抽帧

目的：让大模型看清容易误判的人物、动作、说话对象和同框关系。

建议策略：

```text
每个 visual_focus_segment 抽 3–5 张
覆盖片段开头 / 中间 / 结尾
优先覆盖关键字幕附近
保留 timestamp、scene_id、subtitle_window、frame_id
```

### 5.3 后端视觉信息只摆事实

后端提供给第一轮模型的视觉材料应保持证据层，不写解说。

允许：

```text
frame_id
timestamp
scene_id
segment_id
subtitle_window
frame_path / image payload
片段开始结束时间
帧在片段中的位置
```

禁止：

```text
这个镜头体现主角的绝望
这是全片高潮
这里说明两人关系破裂
这个片段应该用于收尾
```

解释性交给第一轮大模型，文案交给第二轮大模型。

## 6. 人工干预机制

人工干预只发生在第一轮提示词发送前，复选/补选的是 `visual_focus_segments`。

流程：

```text
后端自动生成 visual_focus_segments
  → 前端可展示给用户补选 / 删除 / 调整
  → 5 分钟无操作，自动采用后端结果继续
  → 对最终 visual_focus_segments 详细抽帧
  → 发送第一轮多模态提示词
```

人工干预的典型用途：

```text
第一次生成后，大模型搞错某处人物关系
  → 用户把错误相关时间段补选为 visual_focus_segments
  → 重新完整跑 two_round_visual
```

第二轮后不再人工复选。

## 7. 大模型职责边界

### 7.1 第一轮大模型

第一轮大模型负责全片结构理解。现有第一轮提示词在：

```text
app/services/movie_story/two_round_narration.py
ANALYSIS_PROMPT_TEMPLATE
```

它已经规定第一轮输出：

```text
剧情底图
故事段落
每个故事段的理解
关键小戏
深层理解
情绪弧度
主线候选
自动推荐主线
```

`two_round_visual` 不应让第一轮输出“高光推荐”。第一轮只是在现有结构理解基础上增加视觉证据。

### 7.2 第二轮大模型

第二轮大模型负责写正式文案并选择片段时间码。现有第二轮提示词在：

```text
app/services/movie_story/two_round_narration.py
WRITER_PROMPT_TEMPLATE
```

第二轮输出什么片段，就按什么片段进入剪辑合成。

第二轮后不进行人工复选。效果不好，回到前面的视觉证据和提示词设计优化。

## 8. 推荐流程

```text
1. 用户选择 two_round_visual
2. 后端读取视频、字幕、配置
3. 构建字幕时间轴、scene_segments、scene_boundary_context
4. 可迁移 native 中稳定的镜头切分 / 场景切分工具
5. 后端自动生成 visual_focus_segments
6. 前端可在第一轮前复选 / 补选 visual_focus_segments
7. 5 分钟无操作，自动采用后端结果
8. 全片低密度抽帧
9. visual_focus_segments 详细抽帧
10. 构建 visual_first_round_input
11. 调用第一轮多模态模型输出全片结构理解
12. 调用第二轮文本模型生成正式文案和片段时间码
13. 第二轮后直接剪辑合成 / 导出
```

## 9. legacy / native 策略

legacy / native 主流程已经从主链路移除。

允许从 native 迁移：

```text
镜头切分
场景切分
关键帧抽取
视频元信息读取
时间轴工具
```

禁止恢复：

```text
native 主流程
legacy 主流程
native LLM 编排
任何 fallback 到 native / legacy 的逻辑
```

迁移后的工具必须放入新的 visual / scene / timeline 模块，并写清楚职责与调用方。

## 10. 失败策略

`two_round_visual` 必须严格失败，不 fallback。

以下情况必须报错：

```text
缺视频路径
缺字幕输入
缺视觉模型配置
抽帧失败
关键帧不存在
多模态模型调用失败
模型返回无法解析
visual_focus_segments 生成失败且没有用户补选
```

## 11. 当前已完成

```text
1. two_round_visual 旧定义已被否定。
2. 当前后端已有 guard，防止 two_round_visual 假跑 text-only two_round。
3. legacy/native 主流程已从项目主流程移除。
4. native 中可迁移的确定性视觉工具被允许作为新链路底层能力来源。
5. 第一轮/第二轮提示词位置已确认：two_round_narration.py。
```

## 12. 当前未完成

```text
1. 新的 two_round_visual 多模态第一轮链路尚未接通。
2. visual_focus_segments 自动选择模块尚未正式实现或迁移。
3. 全片低密度抽帧与 visual_focus_segments 详细抽帧尚未形成统一输入包。
4. 前端文案仍可能保留旧定义，需要改成“第一轮多模态增强”。
5. API schema 注释仍可能保留旧定义，需要同步更新。
6. 相关测试仍需重写为新定义。
7. 需要新增或更新 PENDING.md 任务状态。
```

## 13. 命名建议

推荐：

```text
visual_focus_segments
scene_segments
visual_first_round_input
visual_first_round_frames
low_density_scene_frames
detailed_focus_frames
script_segments
output_segments
```

谨慎使用：

```text
highlight
selected_highlights
candidate_highlights
```

如果使用“highlight / 高光”，必须在注释中说明它是产品叫法，不代表第一轮前视觉重点片段就是最终剪辑片段。

## 14. 后续维护原则

```text
后端第一轮前只负责让大模型看清楚。
大模型两轮链负责理解、写文案、选片段。
第二轮后直接剪辑。
效果不好就优化前面的视觉重点选择、视觉证据和提示词，而不是在后面加人工复选。
```
