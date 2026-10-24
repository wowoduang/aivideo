# aivideo 代码规范

> 基于 aivideo 实际代码库提炼，面向 ChatGPT/Cursor 等 AI 辅助编码场景。  
> 重点聚焦：可维护性、AI 可追溯性、任务边界清晰、避免 fake fallback / 历史债积累。  
> 所有规则必须在 AI 写代码前先阅读，必要时按任务类型适当放宽，但不能放宽“主流程唯一性”和“失败直接报错”的核心要求。

---

## 0. 给 AI 的总体指令

在任何 aivideo 代码任务开始前，先在 prompt 中附上此声明：

```
你正在为 aivideo 项目写 Python 代码（FastAPI + loguru + litellm，Python 3.12）。
严格遵守项目编码规范：
- 文件头必须有 # -*- coding: utf-8 -*- 和 from __future__ import annotations
- 日志只用 loguru logger，禁止 print，禁止 logging 模块
- 所有函数必须有完整类型注解（参数 + 返回值）
- 纯函数 ≤ 60 行；编排函数 ≤ 150 行；流水线入口 ≤ 200 行
- 业务文件 ≤ 800 行；提示词/常量表 ≤ 1200 行；测试文件 ≤ 1000 行
- 存量超限文件冻结，禁止继续追加业务逻辑；新逻辑写到新文件中
- AI 任务必须明确区分事实理解 / 节拍设计 / 最终定稿三段式边界
- 失败必须直接 raise，禁止 fallback / silent downgrade
- 不允许同名函数在同一文件中重复定义
- 不允许用 _ORIGINAL_XXX = xxx 这种别名变通；需要扩展函数就直接改函数签名
```

---

## 1. 文件头部

**每个 .py 文件必须以此开头，顺序不得调换：**

```python
# -*- coding: utf-8 -*-
from __future__ import annotations
```

模块有必要说明时，紧接着写 docstring：

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
raw_srt_narration.py

原始 SRT 字幕 → 双轮解说链路。
仅处理 historical_drama 风格且调用方传入了 raw_subtitle_text/path 的场景。
"""
```

---

## 2. import 顺序

按以下三组排列，组间空一行，组内按字母序：

```python
# 第一组：标准库
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# 第二组：第三方库
from loguru import logger

# 第三组：项目内部
from app.services.movie_story.schemas import SceneCandidate
from app.utils import workspace
```

**禁止：**
- `import *`
- 在函数内部 import（除非是为了解决循环依赖，且必须加注释说明原因）
- 混淆标准库与第三方库顺序

---

## 3. 函数规范

### 3.1 类型注解（必须，覆盖率要求 ≥ 95%）

```python
# ✅ 正确
def _build_raw_srt_prompt(
    srt_text: str,
    style: str = "historical_drama",
    video_title: str = "",
) -> str:
    ...

# ❌ 禁止：无注解
def build_prompt(srt_text, style):
    ...
```

### 3.2 keyword-only 参数

**超过 3 个参数的函数，在位置参数后加 `*` 强制关键字调用，防止调用方参数顺序写错：**

```python
# ✅ 正确
def _generate_raw_srt_narration_items(
    scene_evidence: List[Dict],
    *,
    raw_srt_text: str,
    api_key: str,
    base_url: str,
    model: str,
    style: str,
) -> List[Dict]:
    ...

# 调用方必须写关键字，不会搞错顺序
items = _generate_raw_srt_narration_items(
    evidence,
    raw_srt_text=srt,
    api_key=key,
    base_url=url,
    model=model,
    style="historical_drama",
)
```

### 3.3 函数长度与职责边界

按职责区分，不要用单一“80 行硬上限”卡死所有函数。推荐规则：

- **纯函数** ≤ 60 行
- **编排函数** ≤ 150 行
- **流水线入口** ≤ 200 行
- **业务文件** ≤ 800 行
- **提示词和常量表** ≤ 1200 行
- **测试文件** ≤ 1000 行

**行数按物理行计算，含空行和注释。**

**判断标准不是“看上去写了多少行”，而是看“这段代码是否只做了一层职责”：**
- 纯函数负责判断、提取、归一、转换、校验
- 编排函数负责顺序、路由、模型调用、组装结果
- 流水线入口负责一条主流程入口，不能把一大串业务逻辑塞进一个函数里

**例外：**
- 纯数据/常量表文件可允许长一些，但不允许混业务分支；如果内容里出现大量 if/else 分支，就必须拆
- 存量超大文件（>800 行）冻结，禁止追加业务逻辑，新逻辑写到新文件，旧文件只留调用

### 3.4 禁止同名函数重复定义

**严禁在同一文件中用重复定义来"打补丁"。Python 后者覆盖前者，前者变死代码。**

```python
# ❌ 禁止：这是本项目真实发生的事故
def generate_narration_from_scene_evidence(scene_evidence, api_key, ...):
    # 原始实现，310 行
    ...

_ORIGINAL_GENERATE_NARRATION_FROM_SCENE_EVIDENCE = generate_narration_from_scene_evidence  # 别名

def generate_narration_from_scene_evidence(scene_evidence, api_key, ..., raw_subtitle_text=""):
    # dispatcher，覆盖了上面的函数，上面 310 行变成死代码
    ...
```

**正确做法：直接扩展原函数签名：**

```python
# ✅ 正确：在原函数上加参数，内部加分支
def generate_narration_from_scene_evidence(
    scene_evidence: List[Dict],
    api_key: str,
    base_url: str,
    model: str,
    style: str = "documentary",
    video_title: str = "",
    raw_subtitle_text: str = "",
    raw_subtitle_path: str = "",
    raw_subtitle_segments: List[Dict] | None = None,
    **kwargs,
) -> List[Dict]:
    normalized_style = style if style in STYLE_GUIDE else "default"

    if normalized_style in _FAST_CUT_STYLES:
        raw_srt = raw_subtitle_text or _raw_srt_read_file(raw_subtitle_path)
        if raw_srt and api_key and model:
            return _generate_raw_srt_narration_items(
                scene_evidence or [],
                raw_srt_text=raw_srt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                style=normalized_style,
            )
    # 原有逻辑继续 ...
```

---

## 4. AI 任务分三轮边界（强制）

对于 movie_story / two_round_visual / 视频解说类任务，AI 代码和任务流程必须遵守这一条边界：

### 第 1 轮：事实理解 / Event Grounding

**任务目标：** 建立正确事件表，不写最终文案。

输入：
- 稀疏抽帧
- 重点抽帧
- 字幕事件表
- 多模态理解结果

输出：
- 时间
- 谁
- 对谁
- 做了什么
- 结果
- 是否误认 / 误解 / 改认错的人

约束：
- 只能修事实，不允许直接写最终解说稿
- 不能在这一轮做节拍设计

### 第 2 轮：节拍设计 / Beat Planning

**任务目标：** 建立真正的讲述结构，决定怎么讲、讲到哪里。 

输入：
- 事件表
- 视频时间线
- 文案风格要求

输出：
- 8–12 个节拍
- 每拍 2 个候选窗口
- 标注钩子、悬念、删拍、二选一

约束：
- 只能修节拍和窗口，不允许直接输出成稿
- 不能重新写事件表

### 第 3 轮：定稿 / Narration Lock

**任务目标：** 让一条主线最终落成文案，并做小规模核对。 

输入：
- 节拍与窗口
- 指定风格
- 预计字数

输出：
- 每窗一句剧情句
- 成稿 + 事件表 + 字幕要点

约束：
- 只修「核对点名」的句子，不允许整段重写
- 核对可以很短，最好单独一次
- 不能再回到第 2 轮重设计节拍

### 这三轮的意义

- 第 1 轮解决“事实是否正确”
- 第 2 轮解决“结构是否合理”
- 第 3 轮解决“语言是否稳定并可发布”

这是 AI 视频解说项目最关键的工程边界。凡是“第 2 轮又回到理解”或“第 3 轮又重排节拍”的任务，都属于设计不完整，需要调整。

---

## 5. 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块级公开函数 | `snake_case` | `generate_narration_from_scene_evidence` |
| 模块级私有函数 | `_snake_case` | `_build_raw_srt_prompt` |
| 全局常量 | `UPPER_SNAKE_CASE` | `STYLE_GUIDE`, `_FAST_CUT_STYLES` |
| 数据类 | `PascalCase` | `SceneCandidate`, `SubtitleUnit` |
| 包/目录 | `lower_snake_case` | `movie_story/`, `short_drama_explanation/` |

**禁止：**
- 大写缩写目录名（`SDE/`、`SDP/` → 改为 `short_drama_explanation/`）
- 版本号后缀文件名（`direct_runtime_v8.py`、`engine_v2.py`）——版本用 git 管理

---

## 6. 日志规范

**项目统一使用 loguru，禁止 print 和 logging 模块。**

```python
from loguru import logger

# ✅ 用 {} 占位，不用 f-string（loguru 延迟格式化，性能更好）
logger.info("生成完成: style={}, items={}", style, len(items))
logger.warning("历史剧链路未启用: raw_srt={}, model={}", bool(raw_srt), bool(model))
logger.exception("解说生成失败，回退原声粗切: {}", exc)

# ❌ 禁止
print(f"生成完成: {items}")
logging.info("xxx")
logger.info(f"style={style}")  # 用了 f-string，失去延迟格式化
```

日志级别选择：
- `logger.debug`：仅开发调试，生产不输出
- `logger.info`：正常流程里程碑
- `logger.warning`：走了降级/回退路径，或有异常但已处理
- `logger.exception`：在 `except` 块里记录完整堆栈（自动附加 traceback）
- `logger.error`：严重但不需要堆栈的场景

---

## 7. 错误处理

```python
# ✅ 正确：捕获具体异常，记录上下文，决定是否重新抛出
try:
    script_items = _generate_historical_raw_subtitle_script_items(
        scene_evidence, api_key=api_key, model=model, style=style
    )
except ValueError as exc:
    logger.warning("粗时间轴解说解析失败，回退直切: {}", exc)
    return _build_direct_cut_script_items(packages, style=normalized_style)
except Exception as exc:
    logger.exception("历史剧解说生成意外失败: {}", exc)
    raise  # 不吞异常，让上层处理

# ❌ 禁止：裸 except 吞掉所有异常
try:
    result = do_something()
except Exception:
    pass  # 绝对禁止
```

回退逻辑必须用 `logger.warning` 记录，说明为何走了降级路径。

**重要：** 本项目主线禁止 fallback、静默降级、吞异常。多模态链路失败必须直接 raise。

---

## 8. 文件与模块规范

### 8.1 单文件行数

| 情况 | 处理方式 |
|------|----------|
| ≤ 400 行 | 正常 |
| 400~600 行 | 评估是否可以拆分 |
| 600~800 行 | 允许，但要说明职责边界；优先拆 |
| > 800 行 | 存量问题，新代码不允许继续往里追加 |
| > 1200 行 | 纯常量/提示词表允许，但不能混业务逻辑 |

**存量超大文件（待拆分）：**
```
generate_narration_script.py  2536 行 → 拆出 raw_srt_narration.py
voice.py                            2134 行 → 拆出 azure_voices.py
timeline_runtime.py                 1928 行 → 按算法阶段拆子模块
```

### 8.2 一个文件只做一件事

判断标准：能用一句话说清楚这个文件做什么，不需要"和"字。

```
✅ raw_srt_narration.py     — 原始 SRT → 双轮解说链路
✅ voice_cache.py           — TTS 音频缓存读写
❌ generate_narration_script.py  — 标准解说生成 + 历史剧链路 + raw_srt 链路（三件事）
```

### 8.3 禁止往已超大的文件里追加代码

如果目标文件 > 800 行，必须先拆出子模块，再在子模块里写新代码。

---

## 9. LLM 调用规范

### 9.1 统一走 `_call_chat_completion`

所有 LLM 调用必须通过项目封装的 `_call_chat_completion`，禁止直接调用 `openai.chat.completions.create` 或 `litellm.completion`。

```python
# ✅ 正确
raw = _call_chat_completion(
    prompt,
    api_key=api_key,
    base_url=base_url,
    model=model,
    timeout=180,
)

# ❌ 禁止：绕过封装
import openai
resp = openai.chat.completions.create(model=model, messages=[...])
```

### 9.2 Prompt 管理

**超过 5 行的 Prompt 必须定义为模块级常量，禁止内联在函数体里。**

```python
# ✅ 正确：Prompt 作为常量
_RAW_SRT_ANALYSIS_PROMPT_TEMPLATE = """\
你是一位专业的影视解说脚本作家。以下是一部{style_label}的原始字幕：

{srt_text}

请按照以下要求输出解说脚本：
...
"""

def _build_raw_srt_prompt(srt_text: str, style: str) -> str:
    label = STYLE_LABELS.get(style, STYLE_LABELS["default"])
    return _RAW_SRT_ANALYSIS_PROMPT_TEMPLATE.format(
        style_label=label,
        srt_text=srt_text,
    )

# ❌ 禁止：Prompt 内联（来自代码库真实反例）
prompt = f"你正在修复影视解说文案...原字幕：{source}..."
```

### 9.3 LLM 输出解析必须有容错

```python
# ✅ 正确
rows = _raw_srt_extract_rows(raw_text)
if not rows:
    raise ValueError(f"大模型未返回可解析的时间轴，原始输出前200字：{raw_text[:200]}")

# ❌ 禁止：直接 json.loads 不处理异常
result = json.loads(raw_text)
```

---

## 10. 测试规范

### 10.1 测试文件位置

```
✅ tests/test_generate_narration_script.py
✅ tests/llm/test_llm_service.py
❌ app/services/llm/test_llm_service.py  （生产代码目录里放测试）
```

### 10.2 新功能必须配套测试

**AI 写新链路代码时，必须同时输出对应的测试用例，不允许只输出实现代码。**

测试最低覆盖：
1. 正常路径：标准输入 → 预期输出
2. 空输入/边界值：空列表、空字符串、None → 不崩溃
3. 路由分支：if A: 走路径1 else: 走路径2；两条路径各一个测试

### 10.3 禁止只测 happy path

```python
# ❌ 仅测成功路径，没有异常测试
def test_generate_narration(self):
    result = generate_narration(evidence, api_key="real-key", ...)
    self.assertTrue(len(result) > 0)
```

---

## 11. 配置与敏感信息

**API Key 和密钥绝对不允许出现在任何代码文件中。**

```python
# ❌ 绝对禁止
api_key = "sk-bf73a33fa36a4928932501e67fd586e6"

# ✅ 从配置读取
from app.config import get_config
cfg = get_config()
api_key = cfg.vision_litellm_api_key
```

`config.toml` 只放在本地，`.gitignore` 必须包含：

```gitignore
/config.toml
/workspace/
/.patch_backups/
**/__pycache__/
*.pyc
/web/dist/
```

---

## 12. 换行符与编码

项目统一 **LF（Unix）换行符**。在仓库根目录创建 `.gitattributes`：

```gitattributes
*.py    text=auto eol=lf
*.ts    text=auto eol=lf
*.tsx   text=auto eol=lf
*.js    text=auto eol=lf
*.json  text=auto eol=lf
*.toml  text=auto eol=lf
*.md    text=auto eol=lf
```

在 Windows 开发时，提交前运行：

```bash
git add --renormalize .
```

---

## 13. AI 辅助编码 Checklist

让 ChatGPT/Cursor 写完代码后，对照以下清单验收，有任何一项不通过就打回重写：

- [ ] 文件头有 `# -*- coding: utf-8 -*-` 和 `from __future__ import annotations`
- [ ] 所有函数都有参数和返回值的类型注解
- [ ] 超过 3 个参数的函数使用了 `*` 强制 keyword-only
- [ ] 无 `print`，日志统一用 `logger.xxx`，占位符用 `{}`
- [ ] 没有裸 `except:` 或 `except Exception: pass`
- [ ] 没有在同一文件中重复定义同名函数
- [ ] 没有把 API Key 写死在代码里
- [ ] 纯函数 ≤ 60 行，编排函数 ≤ 150 行，入口函数 ≤ 200 行
- [ ] 新增的生产代码有配套测试，测试覆盖正常路径 + 空输入 + 路由分支
- [ ] 测试文件在 `tests/` 目录，不在 `app/` 内
- [ ] 换行符是 LF（用 `file xxx.py` 命令检查，不能出现 CRLF）
- [ ] Prompt 模板超过 5 行的定义为模块级常量，不内联在函数体里
- [ ] 任务边界是否清晰：事实理解 / 节拍设计 / 定稿核对 分层明确
- [ ] 若是主流程改动，是否已确认没有引入 fallback / silent downgrade

---

## 14. 代码可追溯性（Code Traceability）

> **核心目标**：让 AI 工具（ChatGPT/Cursor/Copilot）拿到任意一个文件，
> 无需深度分析整个代码库，就能立即理解：
> 1. 这个文件**是什么**、**为什么存在**
> 2. 它在整体架构里**处于哪个位置**
> 3. **历史上做过什么决策**、为什么这么选择
> 4. **接下来该做什么**、边界在哪里
>
> 涉及术语：**Context Engineering**（AI 上下文工程）、**ADR**（Architecture Decision Records）、**Code Provenance**（代码来源溯源）、**Intent Documentation**（意图文档化）。

### 14.1 模块级 `__CONTEXT__` 块（AI 入口点）

每个模块在文件头 docstring 之后，import 之前，写一个 `__CONTEXT__` 字典。
AI 工具读取这个文件的前 40 行，就能获得完整上下文，无需分析函数体。

**格式（必须字段）：**

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
generate_narration_script.py

影视解说文案生成主模块。接收场景证据列表，调用 LLM 生成逐片段解说词。
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.narration",
    "entry_points": [
        "generate_narration_from_scene_evidence",
        "generate_narration",
    ],
    "called_by": [
        "movie_story/narration_runtime.py",
        "movie_story/direct_cut_runtime.py",
    ],
    "decisions": [
        "2026-04: raw_srt 链路合并进主函数签名，废弃重复定义 dispatcher 模式",
        "2026-03: 双轮解说链路保留，禁止恢复 legacy / native fallback", 
    ],
    "pending": [
        "将 _raw_srt_* 函数族提取到 movie_story/raw_srt_narration.py",
        "主文件降至 ≤ 800 行",
    ],
    "ai_constraints": [
        "禁止继续追加新函数到超大文件",
        "禁止重复定义 generate_narration_from_scene_evidence",
        "新增链路必须先写测试再写实现",
    ],
}
```

---

### 14.2 函数级意图注释（Intent Comment）

普通 docstring 说"是什么"，**意图注释说"为什么"和"不能做什么"**。

```python
def _generate_raw_srt_narration_items(
    scene_evidence: List[Dict],
    *,
    raw_srt_text: str,
    api_key: str,
    base_url: str,
    model: str,
    style: str,
) -> List[Dict]:
    """
    原始 SRT → 双轮解说链路（历史正剧专用）。

    意图：
        历史正剧字幕密度高，单轮生成容易语义割裂。
        此链路先用第一轮 LLM 做结构分析，再写文案。

    注意（AI 不得修改以下行为）：
        - row["start"] 和 row["end"] 单位是秒（float），不是帧号
        - 本函数只在 style in _FAST_CUT_STYLES 时被调用
        - 不允许在这里做 silent fallback

    调用方：
        generate_narration_from_scene_evidence（raw_srt 分支）
    """
```

---

### 14.3 架构决策记录（ADR）

**每次做了影响全局的决策，必须在 `docs/decisions/` 写一条 ADR。**

AI 工具在修改相关模块时，先被告知去读对应 ADR，避免推翻已经经过验证的方案。

文件命名：`docs/decisions/ADR-{编号}-{主题}.md`

---

### 14.4 变更日志注释（Change Provenance）

**在修改已有函数时，在修改处附近加变更注释，说明为什么改、改了什么。**

```python
def generate_narration_from_scene_evidence(
    scene_evidence: List[Dict],
    api_key: str,
    base_url: str,
    model: str,
    style: str = "documentary",
    video_title: str = "",
    # [2026-04 修改] 新增三个参数以支持 raw_srt 链路，
    # 替代之前用 _ORIGINAL_* 别名 + 函数重复定义的 dispatcher 模式。
    # 调用方无需修改，新参数有默认值。
    raw_subtitle_text: str = "",
    raw_subtitle_path: str = "",
    raw_subtitle_segments: List[Dict] | None = None,
    **kwargs,
) -> List[Dict]:
```

**格式规范：**

```python
# [YYYY-MM 操作] 说明。原因/背景。（可选：见 docs/decisions/ADR-XXX.md）
```

---

### 14.5 Pipeline 阶段标注

本项目 movie_story 流水线有多个阶段，**每个阶段函数必须在 docstring 里标注自己的阶段编号和上下游关系**。

```python
def enrich_candidates_with_evidence(
    candidates: List[SceneCandidate],
    *,
    subtitle_segments: List[Dict],
    video_path: str,
) -> List[EvidenceSegment]:
    """
    【阶段 03 / 9】场景候选 → 证据丰富。

    上游：阶段 01 build_segmentation_candidates() → SceneCandidate 列表
    下游：阶段 05 select_highlights_with_report() 消费 EvidenceSegment 列表

    约束（AI 不得修改）：
        - 本阶段只补充证据，不删除候选（policy: stage2_enrich_no_delete）
        - 输出列表长度 ≥ 输入列表长度
    """
```

---

### 14.6 `PENDING.md`：项目级待办（给 AI 的任务队列）

在项目根目录维护一个 `PENDING.md`，记录所有已知的待完成任务。
每次让 AI 开始新任务前，把 `PENDING.md` 的相关条目粘贴进 prompt。

---

## 15. 最终结论：AI 代码不是“写顺手”，而是“收口任务的工程行为”

本项目的目标不是让 AI 自由发挥，而是：

- 先保证事实正确
- 再保证节奏合理
- 最后保证成稿稳定
- 所有这三者都要清晰落在代码和流程里

这也是为什么这次编程规范补充了：
- 三轮任务边界
- 事实判断必须早于节拍设计
- 文案定稿必须在最后
- 失败必须直接 raise，不允许 fallback
- 存量超限文件冻结、禁止继续堆业务逻辑

这条规则对 AI 辅助编码尤其关键：
AI 很容易在错误的边界内继续输出代码，最终只会让项目越来越乱。
因此，既要保持严谨的工程规范，又必须让 AI 明确知道：
**它负责什么，它不负责什么。**

---

## 16. 代码可追溯性 Checklist（补充）

在第 13 章 Checklist 基础上，每次 AI 写完代码额外检查：

- [ ] 新建文件有 `__CONTEXT__` 字典（layer / domain / entry_points / called_by / decisions / pending / ai_constraints）
- [ ] 修改已有函数时，在修改处加了 `# [YYYY-MM 操作]` 变更注释
- [ ] 做了影响全局的决策（新链路/废弃旧逻辑/改数据结构），在 `docs/decisions/` 写了 ADR
- [ ] 完成 `PENDING.md` 中的任务后，将对应条目移到「已完成」并填写方案摘要
- [ ] 新的阶段函数标注了 `【阶段 XX / 9】`、上游和下游
- [ ] `__CONTEXT__.pending` 中记录了本次未完成但已知需要做的后续任务
- [ ] 本次任务是否清楚区分了：事实理解 / 节拍设计 / 最终定稿三段式边界
- [ ] 若本次改动涉及主流程，是否确认没有引入 fallback

---

## 17. 结语

aivideo 不是单纯“写代码”，而是把工程、模型、流程、审核和产品闭环有机结合起来。
这要求代码规范不仅约束语法和风格，更要约束任务边界、AI 行为边界、代码可追溯边界和主链路唯一性。

把这部分规则固化在文档中后，AI 接手协作会明显更稳定，也更有利于后续维护、复盘和演进。

