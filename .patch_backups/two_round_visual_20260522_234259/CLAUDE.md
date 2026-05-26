# CLAUDE.md — aivideo 项目 AI 接手入口

> 任何 ChatGPT / Claude Code / Cursor 在本仓库开始工作前，必须先阅读本文件，再阅读相关设计文档、ADR、PENDING.md 和目标文件顶部的 `__CONTEXT__`。

## 1. 项目当前主线

aivideo 当前重点是 `movie_story` 业务域下的双轮解说链路与 `two_round_visual` 第一轮多模态增强。

当前主流程原则：

```text
movie_story unified entry
  → two_round / two_round_visual feature mode
  → 第一轮结构理解
  → 第二轮文案写作与片段选择
  → 剪辑合成 / 导出
```

legacy / native 主流程已经从项目主链路移除，源码暂时保留，仅用于迁移确定性工具能力或后续删除。

## 2. 必读文档

开始任何 `movie_story` 或 `two_round_visual` 相关任务前，按顺序阅读：

1. `docs/aivideo_coding_standards.md`
2. `docs/movie_story_two_round_visual_design.md`
3. `docs/decisions/ADR-005-two-round-visual-first-round-multimodal.md`
4. `docs/status/two_round_visual_status.md`
5. `PENDING.md`
6. 目标文件顶部的 `__CONTEXT__` 字典

完成读取后，先复述当前任务边界，再修改代码。

## 3. two_round_visual 的唯一正确定义

`two_round_visual` 表示：

```text
第一轮提示词前准备视觉证据
  → 全片低密度抽帧
  → visual_focus_segments 详细抽帧
  → 第一轮多模态大模型理解全片
  → 第二轮文本大模型写文案并选择片段
  → 第二轮后直接剪辑合成
```

它不是：

```text
text-only 双轮链跑完后再抽帧
AI 推荐高光
最终剪辑片段人工复选流程
legacy/native fallback
```

## 4. visual_focus_segments 的定义

`visual_focus_segments` 是第一轮提示词前的“视觉重点片段 / 详细抽帧区域”。

它的作用只有一个：

```text
决定哪些时间段要抽更详细的帧，帮助第一轮多模态模型看清楚全片。
```

它用于解决：

```text
谁在说话
谁是说话对象
谁在动作
场景里有哪些人
字幕里的“你/我/他”对应谁
text-only two_round 是否误判人物关系
```

它不是：

```text
AI 推荐高光
最终剪辑片段
最终文案片段
第二轮输出片段
大模型必须采用的片段
```

产品层可以继续使用“高光 / 精彩片段”这类叫法，但后端设计和代码注释必须说明：第一轮前选择的片段只是视觉重点抽帧区域，不是 AI 推荐高光。

## 5. 人工干预位置

只允许在第一轮提示词发送前，对 `visual_focus_segments` 做复选 / 补选。

典型场景：

```text
第一次生成后，大模型把某处人物关系搞错
  → 用户把错误相关时间段补选为 visual_focus_segments
  → 完整重新跑 two_round_visual
  → 该时间段会被详细抽帧送入第一轮多模态提示词
```

第二轮之后不再设计人工复选。大模型两轮链已经负责理解、写文案、选片段；第二轮输出什么片段就按什么片段剪辑。

## 6. legacy / native 策略

允许迁移 native 中稳定、低成本、确定性的视觉基础能力，例如：

```text
镜头切分
场景切分
关键帧抽取
视频元信息读取
时间轴工具
```

禁止：

```text
恢复 native 主流程
恢复 legacy 主流程
把 native/legacy 当 fallback
迁移 native LLM 编排链路
在 two_round_visual 失败时改跑 text-only / native / legacy
```

迁移出的工具必须重命名并整理到新的 visual / timeline / scene 模块中。

## 7. 错误策略

新链路失败必须直接报错。禁止 fallback、静默降级、吞异常。

以下情况必须 `raise`：

```text
缺 video_path
缺 raw_srt_text / 字幕输入
缺视觉模型配置
抽帧失败
关键帧文件不存在
多模态模型调用失败
多模态返回结构不合法
```

## 8. 代码规范摘要

写 Python 代码时必须遵守：

```text
文件头：# -*- coding: utf-8 -*- + from __future__ import annotations
日志：只用 loguru logger，禁止 print / logging
函数：完整类型注解，超过 3 个参数使用 keyword-only
长度：单文件 ≤ 600 行，单函数 ≤ 80 行
Prompt：超过 5 行必须为模块级常量
LLM：统一走项目封装 _call_chat_completion
测试：新模块必须配套 tests
追溯：新文件必须有 __CONTEXT__，全局决策必须写 ADR
```

## 9. 常用验收命令

```bash
python -m compileall -q app tests
python -m pytest -q tests/movie_story
```

按任务范围补充更精确的测试命令；不要只跑 happy path。

## 10. AI 开始工作前必须确认

开始写代码前，先回答：

```text
1. 当前任务是否属于 two_round_visual / movie_story 主流程？
2. 是否读过本文件和对应 ADR / design / status / PENDING？
3. 本次修改是否会触碰 legacy/native？如果会，是否只是迁移确定性工具能力？
4. 本次修改是否可能引入 fallback？如果可能，停止设计。
5. 新增文件是否准备了 __CONTEXT__ 与测试？
```
