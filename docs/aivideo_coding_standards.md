# aivideo 代码规范

> 基于 aivideo 实际代码库提炼，面向 ChatGPT/Cursor 等 AI 辅助编码场景。  
> 每条规则附有 **真实反例**（来自代码库中已发现的问题）和 **正例**。

---

## 0. 给 AI 的总体指令

在任何 aivideo 代码任务开始前，先在 prompt 中附上此声明：

```
你正在为 aivideo 项目写 Python 代码（FastAPI + loguru + litellm，Python 3.12）。
严格遵守项目编码规范：
- 文件头必须有 # -*- coding: utf-8 -*- 和 from __future__ import annotations
- 日志只用 loguru logger，禁止 print，禁止 logging 模块
- 所有函数必须有完整类型注解（参数 + 返回值）
- 单文件不超过 600 行，单函数不超过 80 行
- 新模块必须在 tests/ 对应目录有配套测试
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

### 3.3 函数长度

- **单函数不超过 80 行**（不含注释和空行）
- 超过 80 行必须拆分为若干私有辅助函数
- 最大不得超过 120 行（已是极限，需在 PR 说明原因）

**反例（来自代码库）：**
```
voice.py: get_all_azure_voices()   1000 行  ← 禁止
generate_video.py: merge_materials()  354 行  ← 禁止
story_runtime.py: extract_highlights() 332 行  ← 禁止
```

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
    raw_subtitle_text: str = "",       # 新增
    raw_subtitle_path: str = "",       # 新增
    raw_subtitle_segments: List[Dict] | None = None,  # 新增
    **kwargs,
) -> List[Dict]:
    normalized_style = style if style in STYLE_GUIDE else "default"

    # raw_srt 优先路由
    if normalized_style in _FAST_CUT_STYLES:
        raw_srt = raw_subtitle_text or _raw_srt_read_file(raw_subtitle_path)
        if raw_srt and api_key and model:
            return _generate_raw_srt_narration_items(
                scene_evidence or [],
                raw_srt_text=raw_srt,
                api_key=api_key, base_url=base_url,
                model=model, style=normalized_style,
            )
    # 原有逻辑继续 ...
```

---

## 4. 命名规范

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

## 5. 日志规范

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

## 6. 错误处理

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

# ❌ 禁止：裸 except 吞掉所有异常（代码库中有 280 处此类问题）
try:
    result = do_something()
except Exception:
    pass  # 绝对禁止
```

回退逻辑必须用 `logger.warning` 记录，说明为何走了降级路径。

---

## 7. 文件与模块规范

### 7.1 单文件行数

| 情况 | 处理方式 |
|------|----------|
| ≤ 400 行 | 正常 |
| 400~600 行 | 评估是否可以拆分 |
| > 600 行 | 必须拆分，PR 不得合并 |
| > 800 行 | 存量问题，新代码不允许继续往里追加 |

**存量超大文件（待拆分）：**
```
generate_narration_script_clean.py  2536 行 → 拆出 raw_srt_narration.py
voice.py                            2134 行 → 拆出 azure_voices.py
timeline_runtime.py                 1928 行 → 按算法阶段拆子模块
```

### 7.2 一个文件只做一件事

判断标准：能用一句话说清楚这个文件做什么，不需要"和"字。

```
✅ raw_srt_narration.py     — 原始 SRT → 双轮解说链路
✅ voice_cache.py           — TTS 音频缓存读写
❌ generate_narration_script_clean.py  — 标准解说生成 + 历史剧链路 + raw_srt 链路（三件事）
```

### 7.3 禁止往已超大的文件里追加代码

如果目标文件 > 600 行，必须先拆出子模块，再在子模块里写新代码。

---

## 8. LLM 调用规范

### 8.1 统一走 `_call_chat_completion`

所有 LLM 调用必须通过项目封装的 `_call_chat_completion`，禁止直接调用 `openai.chat.completions.create` 或 `litellm.completion`。

```python
# ✅ 正确
raw = _call_chat_completion(
    prompt,
    api_key=api_key,
    base_url=base_url,
    model=model,
    timeout=180,  # 长任务显式设置超时
)

# ❌ 禁止：绕过封装
import openai
resp = openai.chat.completions.create(model=model, messages=[...])
```

### 8.2 Prompt 管理

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

# ❌ 禁止：Prompt 内联（来自代码库真实反例，130字符单行）
prompt = f"你正在修复影视解说文案...原字幕：{source}...只返回 JSON：{{\"narration\":\"改好的解说词\"}}"
```

### 8.3 LLM 输出解析必须有容错

```python
# ✅ 正确
rows = _raw_srt_extract_rows(raw_text)
if not rows:
    raise ValueError(f"大模型未返回可解析的时间轴，原始输出前200字：{raw_text[:200]}")

# ❌ 禁止：直接 json.loads 不处理异常
result = json.loads(raw_text)  # 大模型输出不稳定，必须加 try-except
```

---

## 9. 测试规范

### 9.1 测试文件位置

```
✅ tests/test_generate_narration_script_clean.py
✅ tests/llm/test_llm_service.py
❌ app/services/llm/test_llm_service.py  （生产代码目录里放测试）
```

### 9.2 新功能必须配套测试

**AI 写新链路代码时，必须同时输出对应的测试用例，不允许只输出实现代码。**

测试最低覆盖：
1. **正常路径**：标准输入 → 预期输出
2. **空输入/边界值**：空列表、空字符串、None → 不崩溃
3. **路由分支**：如果有 `if A: 走路径1 else: 走路径2`，两条路各一个测试

```python
# 示例：raw_srt 链路最小测试集
class TestRawSrtNarration(unittest.TestCase):

    def test_extract_rows_standard_timecode(self):
        """标准 [MM:SS ~ MM:SS] 格式可正确解析"""
        raw = "**开场**\n[00:30 ~ 01:10]\n开场文案。"
        rows = narration_clean._raw_srt_extract_rows(raw)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["start"], 30.0)

    def test_extract_rows_empty_input_returns_empty(self):
        """无时间码时返回空列表，不崩溃"""
        rows = narration_clean._raw_srt_extract_rows("没有时间码的文本")
        self.assertEqual(rows, [])

    def test_route_with_raw_subtitle_path_calls_raw_srt_chain(self):
        """传 raw_subtitle_path 时路由到 raw_srt 链路"""
        with unittest.mock.patch(
            "app.services.generate_narration_script_clean._generate_raw_srt_narration_items"
        ) as mock:
            mock.return_value = [{"start": 30, "end": 70, "narration": "测试"}]
            narration_clean.generate_narration_from_scene_evidence(
                scene_evidence=[],
                api_key="sk-test", base_url="", model="test-model",
                style="historical_drama",
                raw_subtitle_text="1\n00:00:30,000 --> 00:01:10,000\n测试字幕",
            )
            mock.assert_called_once()
```

### 9.3 禁止只测 happy path

```python
# ❌ 仅测成功路径，没有异常测试
def test_generate_narration(self):
    result = generate_narration(evidence, api_key="real-key", ...)
    self.assertTrue(len(result) > 0)
```

---

## 10. 配置与敏感信息

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

## 11. 换行符与编码

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

## 12. AI 辅助编码 Checklist

让 ChatGPT/Cursor 写完代码后，对照以下清单验收，有任何一项不通过就打回重写：

- [ ] 文件头有 `# -*- coding: utf-8 -*-` 和 `from __future__ import annotations`
- [ ] 所有函数都有参数和返回值的类型注解
- [ ] 超过 3 个参数的函数使用了 `*` 强制 keyword-only
- [ ] 无 `print`，日志统一用 `logger.xxx`，占位符用 `{}`
- [ ] 没有裸 `except:` 或 `except Exception: pass`
- [ ] 没有在同一文件中重复定义同名函数
- [ ] 没有把 API Key 写死在代码里
- [ ] 单函数不超过 80 行
- [ ] 新增的生产代码有配套测试，测试覆盖正常路径 + 空输入 + 路由分支
- [ ] 测试文件在 `tests/` 目录，不在 `app/` 内
- [ ] 换行符是 LF（用 `file xxx.py` 命令检查，不能出现 CRLF）
- [ ] Prompt 模板超过 5 行的定义为模块级常量，不内联在函数体里

---

## 13. 代码可追溯性（Code Traceability）

> **核心目标**：让 AI 工具（ChatGPT/Cursor/Copilot）拿到任意一个文件，
> 无需深度分析整个代码库，就能立即理解：
> 1. 这个文件**是什么**、**为什么存在**
> 2. 它在整体架构里**处于哪个位置**
> 3. **历史上做过什么决策**、为什么这么选择
> 4. **接下来该做什么**、边界在哪里
>
> 涉及术语：**Context Engineering**（AI 上下文工程）、
> **ADR（Architecture Decision Records）**（架构决策记录）、
> **Code Provenance**（代码来源溯源）、
> **Intent Documentation**（意图文档化）。

---

### 13.1 模块级 `__CONTEXT__` 块（AI 入口点）

每个模块在文件头 docstring 之后，import 之前，写一个 `__CONTEXT__` 字典。
AI 工具读取这个文件的前 40 行，就能获得完整上下文，无需分析函数体。

**格式（必须字段）：**

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
generate_narration_script_clean.py

影视解说文案生成主模块。接收场景证据列表，调用 LLM 生成逐片段解说词。
"""

__CONTEXT__ = {
    # ── 定位 ──────────────────────────────────────────────────────────────
    "layer": "service",                          # api / service / model / util
    "domain": "movie_story.narration",           # 业务域
    "entry_points": [                            # 外部调用此模块的唯一入口
        "generate_narration_from_scene_evidence",
        "generate_narration",
    ],
    "called_by": [                               # 谁调用了这个模块
        "movie_story/narration_runtime.py",
        "movie_story/direct_cut_runtime.py",
    ],
    # ── 历史决策（ADR 简版）─────────────────────────────────────────────
    "decisions": [
        "2026-04: raw_srt 链路合并进主函数签名（新增 raw_subtitle_text/path 参数），"
        "废弃了之前用 _ORIGINAL_* 别名+重复定义的 dispatcher 模式，见 docs/FIX_REPORT.md",
        "2026-03: _raw_srt_* 命名族（20个函数）内联在本文件，"
        "计划迁移到 movie_story/raw_srt_narration.py，尚未执行",
    ],
    # ── 待完成任务（TODO for AI）─────────────────────────────────────────
    "pending": [
        "将 _raw_srt_* 函数族（L2077~L2530）提取到 movie_story/raw_srt_narration.py",
        "文件行数超标（2780行），拆分后主文件应降至 ~800 行",
    ],
    # ── 禁止行为（AI 必须遵守）───────────────────────────────────────────
    "ai_constraints": [
        "禁止在本文件继续追加新函数，超过 600 行的文件不得新增代码",
        "禁止重复定义 generate_narration_from_scene_evidence",
        "新增链路必须先在 tests/ 写测试再写实现",
    ],
}
```

**AI 使用方式：** 每次对话开头附上：
```
请先读取目标文件的 __CONTEXT__ 字典，按照其中的 pending 执行任务，
遵守 ai_constraints，并在完成后更新 decisions 追加本次变更记录。
```

---

### 13.2 函数级意图注释（Intent Comment）

普通 docstring 说"是什么"，**意图注释说"为什么"和"不能做什么"**。

AI 最容易犯的错误是"看到问题就修"，在不理解历史决策的情况下把绕过某个 bug
的代码"优化"掉。意图注释明确告诉 AI：这段看起来奇怪的代码有它存在的理由。

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
        历史正剧（historical_drama）字幕密度高、台词文言化，
        标准批量生成链路会产生大量语义割裂。
        此链路先用第一轮 LLM 做结构分析，第二轮再写文案，
        效果比单轮批量生成高约 40%（2026-03 AB 测试结论）。

    注意（AI 不得修改以下行为）：
        - row["start"] 和 row["end"] 单位是秒（float），不是帧号
        - _raw_srt_build_items 返回的 items 时间已经过扩展验证（≥60秒），
          调用方不得再次裁剪
        - 本函数只在 style in _FAST_CUT_STYLES 时被调用，
          调用前的路由判断在 generate_narration_from_scene_evidence 里

    调用方：
        generate_narration_from_scene_evidence（raw_srt 分支）
    """
```

---

### 13.3 架构决策记录（ADR）

**每次做了影响全局的决策，必须在 `docs/decisions/` 写一条 ADR。**

AI 工具在修改相关模块时，先被告知去读对应 ADR，避免推翻已经经过验证的方案。

文件命名：`docs/decisions/ADR-{编号}-{主题}.md`

```
docs/decisions/
├── ADR-001-llm-unified-via-litellm.md
├── ADR-002-raw-srt-two-round-narration.md
├── ADR-003-movie-story-nine-stage-pipeline.md
└── ADR-004-task-function-naming-no-version-suffix.md
```

**ADR 模板（最小版本）：**

```markdown
# ADR-002: 历史正剧原始 SRT 双轮解说链路

**日期**：2026-03-15
**状态**：已实施（Active）
**影响文件**：
- app/services/generate_narration_script_clean.py
- app/services/movie_story/two_round_narration.py

## 背景

历史正剧字幕密度高（平均 6 字/秒），台词文言化，
标准单轮批量生成链路产生大量语义割裂，用户反馈解说"读不通"。

## 决策

新增双轮解说路由：
- 第一轮：结构分析（ANALYSIS_PROMPT_TEMPLATE），提取故事段落和关键小戏
- 第二轮：文案写作（WRITER_PROMPT_TEMPLATE），基于分析结果生成解说

触发条件：`style in _FAST_CUT_STYLES and raw_srt_text`

## 结果

AB 测试（2026-03 样本 200 条）：用户满意度 +38%，解说连贯性评分 4.2→4.7。

## 注意（AI 不得推翻）

双轮调用会消耗约 2× token，这是**已知且接受的成本**。
不要试图合并为单轮提示以"节省 token"，会破坏生成质量。
```

---

### 13.4 变更日志注释（Change Provenance）

**在修改已有函数时，在修改处附近加变更注释，说明为什么改、改了什么。**

这是给下一个接手的人（或 AI）看的，比 git blame 更直接。

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
    # 调用方（direct_cut_runtime.py）无需修改，新参数有默认值。
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

变更注释写在**被修改的代码旁边**，不写在文件顶部（顶部是模块级说明）。

---

### 13.5 Pipeline 阶段标注

本项目 movie_story 流水线有 9 个阶段（01~09），
**每个阶段函数必须在 docstring 里标注自己的阶段编号和上下游关系**，
AI 才能在不读完整 pipeline.py 的情况下理解调用链。

```python
# ── 本项目实际阶段定义 ────────────────────────────────────────────────────
# 01_scene_candidates       build_segmentation_candidates()
# 02_draft_story_candidates （内部，由 stage1 生成）
# 03_evidence_segments      enrich_candidates_with_evidence()
# 04_split_merge_suggestions（内部）
# 05_selected_highlights    select_highlights_with_report()
# 06_rejected_candidates    （内部）
# 07_human_narration_director build_human_narration_package()
# 08_humanized_script_items  （内部，由 stage7 生成）
# 09_subtitle_design_cues   design_subtitle_cues()
# ──────────────────────────────────────────────────────────────────────────

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

### 13.6 `PENDING.md`：项目级待办（给 AI 的任务队列）

在项目根目录维护一个 `PENDING.md`，记录所有已知的待完成任务。
每次让 AI 开始新任务前，把 `PENDING.md` 的相关条目粘贴进 prompt。

```markdown
# PENDING.md — aivideo 待完成任务

## 🔴 高优先级

### [PEND-001] 拆分 generate_narration_script_clean.py
- 文件现状：2780 行，3 条链路混合
- 目标：提取 _raw_srt_* 函数族（约 450 行）到 movie_story/raw_srt_narration.py
- 前置条件：raw_srt 链路测试覆盖率 ≥ 80%（当前 0%）
- 影响文件：generate_narration_script_clean.py, direct_cut_runtime.py
- 验收标准：主文件降至 ≤ 800 行，所有现有测试通过

### [PEND-002] 补充 raw_srt 链路测试
- 目标：tests/test_generate_narration_script_clean.py 新增 TestRawSrtNarration 类
- 最少覆盖：时间码解析、空输入容错、路由分支选择（共 6 个测试用例）
- 相关 ADR：ADR-002

## 🟡 中优先级

### [PEND-003] voice.py 音色数据外置
- 文件现状：get_all_azure_voices() 1000 行硬编码音色列表
- 目标：提取到 resource/azure_voices.json，函数缩减至 10 行
- 注意：azure_voices.json 格式需与现有返回值结构兼容

### [PEND-004] SDE/ SDP/ 目录重命名
- 目标：SDE/ → short_drama_explanation/, SDP/ → short_drama_generation/
- 影响：需批量更新所有 import 路径（约 12 处）

## ✅ 已完成（供溯源）

### [DONE-001] 修复 generate_narration_from_scene_evidence 重复定义
- 完成日期：2026-05
- 方案：合并参数，删除 _ORIGINAL_* 别名和 dispatcher，见 docs/FIX_REPORT.md

### [DONE-002] task.py 版本号函数统一
- 完成日期：2026-05
- 方案：_v12/_v15/_v161 → 无版本号统一命名，删除重复实现
```

**给 AI 的 prompt 模板：**

```
当前任务：[PEND-001] 拆分 generate_narration_script_clean.py

相关上下文：
- 目标文件 __CONTEXT__: [粘贴文件头的 __CONTEXT__ 字典]
- 相关 ADR: [粘贴 ADR-002 内容]
- 验收标准：主文件 ≤ 800 行，所有现有测试通过，新增 TestRawSrtNarration 6 个测试

请在不影响现有功能的前提下执行，完成后：
1. 更新 generate_narration_script_clean.py 的 __CONTEXT__.decisions
2. 在 PENDING.md 中将 PEND-001 移到「已完成」并记录方案
```

---

### 13.7 AI 可追溯性 Checklist（补充到第 12 章）

在第 12 章 Checklist 基础上，每次 AI 写完代码额外检查：

- [ ] 新建文件有 `__CONTEXT__` 字典（layer / domain / entry_points / called_by / decisions / pending / ai_constraints）
- [ ] 修改已有函数时，在修改处加了 `# [YYYY-MM 操作]` 变更注释
- [ ] 做了影响全局的决策（新链路/废弃旧逻辑/改数据结构），在 `docs/decisions/` 写了 ADR
- [ ] 完成 `PENDING.md` 中的任务后，将对应条目移到「已完成」并填写方案摘要
- [ ] 新的阶段函数标注了 `【阶段 XX / 9】`、上游和下游
- [ ] `__CONTEXT__.pending` 中记录了本次未完成但已知需要做的后续任务

