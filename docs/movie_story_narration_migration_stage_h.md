# Movie Story Narration Stage-H 收口迁移说明

## 目标

把旧仓库优秀的影视解说链路从 `subtitle_first_pipeline.py` 继续迁入 `app/services/movie_story/`，并把前面 A-G 中停留在 contract/sample 的解说生成与校验能力收口到正式生产链路。

## 本轮新增模块

| 模块 | 职责 |
|---|---|
| `app/services/movie_story/story_window.py` | 片头/序幕、片尾/预告、正文窗口、LLM 高光窗口归一化与非破坏性标注 |
| `app/services/movie_story/narration_evidence.py` | typed highlights -> rich narration evidence，保留剧情、视觉、人物、raw voice、校验信息 |
| `app/services/movie_story/narration_runtime.py` | 统一正式解说运行模式，调用成熟旧解说器 |
| `app/services/movie_story/narration_finalize.py` | Stage-H 最终脚本收口：归一化、过滤、语义窗锁定、grounding 校验、修复元数据 |

## 对 `subtitle_first_pipeline.py` 的改造

- 旧大文件从约 3216 行降到约 1989 行。
- 保留 `run_subtitle_first_pipeline` 对外入口。
- 私有函数名通过 import alias 保持兼容，旧测试/旧调用不会因为函数迁移立刻断裂。
- 正式解说流程新增 `07c_final_narration_validation` 审计节点。
- 最终 audit 增加 `narration_finalize_report`。

## A-G 与 H 的关系

A-G 已经迁移了证据增强、高光规划、输入契约、理解质量抽样、理解回写、解说抽样、解说校验抽样；但 F/G 未完整进入正式生产链路。本轮 Stage-H 做的是：

```text
正式 narration_evidence
↓
narration_runtime.generate
↓
narration_finalize.finalize_narration_script
↓
07c_final_narration_validation
↓
最终 script_items
```

## 仍保留的兼容策略

- 仍然调用 `generate_narration_script.py` 作为成熟旧解说器。
- 没有隐藏新增 LLM 重写调用，避免成本和不可控漂移。
- `narration_finalize.py` 只做确定性校验和空白修复；非空 review 项只打标，不擅自改写。

## 下一轮建议

1. 把剩余审计函数迁入统一 `movie_story/audit_runtime.py`。
2. 把 `_build_story_audit_payload` 从旧大文件迁出。
3. 再把 `highlight_edit_pipeline.py` 接入 `movie_story.narration_evidence/runtime/finalize`，实现统一 `CompositionPlan` 主线。
