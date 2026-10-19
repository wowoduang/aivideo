# movie_story

影视解说专用流水线模块，主流程不再按 runtime 版本号分叉，统一使用语义化入口：

1. `timeline_runtime.py`：负责字幕/音频保护优先的权威时间线切片，产出稳定的 `video_start` / `video_end`。
2. `story_runtime.py`：负责生产级高光选择编排、时间线一致性校验和只读规范化，不生成解说副作用。
3. `stage1_segmentation.py`：候选切片建库，只切片，不筛选。
4. `stage2_evidence.py`：证据增强与语义标注，只理解，不删除。
5. `stage3_highlight_selection.py`：按 `strict` / `balanced` / `loose` / `very_loose` 做高光选择。
6. `audit.py` / `audit_policy.py`：统一审计 JSON / CSV / clips 输出策略。
7. `pipeline.py`：前三阶段旁路测试入口。

重要原则：

- `video_start` / `video_end` 是视频裁剪范围，TTS 时长不能决定视频片段时长。
- 高光选择只负责选片段，不在内部生成解说文案。
- 最终文案由 `subtitle_first_pipeline.py` 将高光重新聚合为 rich `scene_evidence` 后，统一调用旧成熟 LLM 解说链路生成。

## 本轮解说链路收口模块

这轮把 `subtitle_first_pipeline.py` 中仍然滞留的旧解说链路能力拆入 `movie_story`，定位如下：

8. `story_window.py`：片头/序幕、片尾/演职员表、下集预告、`story_end_time`、LLM highlight windows、正文窗口裁剪策略。
9. `narration_evidence.py`：把 typed highlights 重新聚合成旧成熟解说器需要的 rich `scene_evidence`，保留剧情功能、局部理解、代表帧、人物/对白、raw voice 和校验信息。
10. `narration_runtime.py`：正式生产解说运行时，统一 `disabled` / `fallback` / `hybrid` / `full` / `batch` 模式，并调用现有成熟 `generate_narration_script`。
11. `narration_finalize.py`：Stage-H 收口层。将原 Stage F/G 的抽样生成/抽样校验升级为正式脚本最终门禁：归一化、按高光过滤、语义窗锁定、grounding 检查和安全修复元数据。

当前架构原则：

- `movie_story` 是新的影视解说能力层，不再只是迁移报告目录。
- `subtitle_first_pipeline.py` 保留旧 API 兼容，但逐步退化为编排器。
- 不再把旧仓库优秀解说逻辑继续堆到旧大文件里；新增能力必须进入 `movie_story/*`。
- 正式文案仍调用成熟旧解说器，但输入、运行模式、最终校验已经模块化。


## Stage-I 模块化收口

Stage-H 后，`subtitle_first_pipeline.py` 仍然残留运行参数、审计、场景对齐、高光运行和质量门禁等稳定生产逻辑。本轮已继续拆出：

12. `runtime_options.py`：统一目标时长、视觉模式、LLM 配置、迁移阶段、解说模式和阶段 trace。
13. `audit_runtime.py`：统一阶段审计、manifest、CSV、items_full 和可选 clips 导出。
14. `scene_alignment.py`：统一复用已有边界池、语义窗解析和场景组对齐。
15. `highlight_runtime.py`：统一 bounded 高光规划、fallback summary、typed selector fallback 和最终 evidence guard。
16. `quality_gate.py`：统一 pipeline 质量门禁和最终 audit payload。

本轮后旧入口 `subtitle_first_pipeline.py` 已降到约 997 行，继续作为兼容编排器使用。

## Stage-J：粗剪选择器迁入 movie_story

Stage-I 后，`highlight_edit_pipeline.py` 仍然保留大量复杂选择器逻辑。本轮继续把粗剪主链中的稳定高光选择能力迁入 `movie_story`：

17. `highlight_edit_selection.py`：粗剪高光选择器 runtime。负责 score/diverse/coverage/raw-audio/scene/opening/ending/climax/chronology 多池选择，peak window 扩展，字幕/剧情边界吸附，主角窗口、payoff 窗口，以及 clip 去重合并。

本轮后：

- `highlight_edit_pipeline.py` 从约 2651 行降到约 1484 行。
- 原 `_build_highlight_recut_selection_pool`、`_merge_unique_clips`、`_clip_overlap_ratio`、`_detect_main_character_reference` 保留兼容 shim，但实际逻辑已进入 `movie_story.highlight_edit_selection`。
- `movie_story` 继续从“影视解说迁移模块目录”升级为“解说 + 粗剪选择能力层”。

## Stage-K：粗剪候选构建与 CompositionPlan 迁入 movie_story

Stage-J 后，`highlight_edit_pipeline.py` 仍然保留候选构建、narrated pool 和 CompositionPlan 生成逻辑。本轮继续拆出：

18. `highlight_edit_candidates.py`：粗剪候选构建 runtime。负责 plot/scene candidate 构建、scene 与 plot chunk 对齐、字幕 speaker/exchange 信号提取、候选统计、narrated candidate pool、matched clips 收集。
19. `highlight_edit_composition.py`：粗剪 CompositionPlan runtime。负责 narrated group shot、intra-scene subshots、旁白文本分配、shot duration planning、raw/ducked/tts 音频策略和 timeline cursor。

本轮后：

- `highlight_edit_pipeline.py` 从约 1484 行降到约 739 行。
- 原候选构建和 CompositionPlan 私有函数保留 compatibility alias，但实际实现已进入 `movie_story.highlight_edit_candidates` / `movie_story.highlight_edit_composition`。
- `highlight_edit_pipeline.py` 进一步变成粗剪编排器，不再承载大块候选和合成逻辑。

## Stage-L：粗剪运行上下文与输出写盘迁入 movie_story

Stage-K 后，`highlight_edit_pipeline.py` 仍然残留视觉配置、AI 适配、profile/audio 注入和输出写盘等胶水逻辑。本轮继续拆出：

20. `highlight_edit_context.py`：粗剪运行上下文 runtime。负责视觉模式配置、可选 AI 高光选择/解说匹配、profile 能力解析和应用、音频信号上下文构建、候选音频打分、AI 选片 id 映射和 narration match 刷新。
21. `highlight_edit_outputs.py`：粗剪输出 runtime。负责 `CompositionPlan` / script items 写盘，以及稳定的 success/error response shape。

本轮后：

- `highlight_edit_pipeline.py` 从约 737 行降到约 462 行。
- 原运行上下文和输出私有函数保留 compatibility alias，但实际实现已进入 `movie_story.highlight_edit_context` / `movie_story.highlight_edit_outputs`。
- 粗剪主链继续向“薄编排器 + movie_story 能力层”收口。


## Stage-M：影视解说链路统一输出 CompositionPlan

Stage-L 后，粗剪主链已经以 `CompositionPlan` 为标准输出，但影视解说主链仍主要返回旧 `script_items`。本轮新增：

22. `composition_bridge.py`：把 `subtitle_first_pipeline.py` 最终 `script_items`、`narration_evidence` 与 `story_highlights` 桥接成统一 `CompositionPlan`，保留语义窗、raw/ducked/tts 音频意图、剧情类型、选择理由和 `movie_story_validation` 元数据。

本轮后：

- `subtitle_first_pipeline.py` 保留旧 `script_items` 兼容输出，同时新增 `composition_plan` / `composition_plan_path` / `composition_plan_report`。
- 审计新增 `08_movie_story_composition_plan`，用于检查 CompositionPlan 的片段数、timeline 连续性、音频模式和窗口合法性。
- `highlight_edit_pipeline.py` 和 `subtitle_first_pipeline.py` 不再在输出格式上完全分裂，后续 WebUI / 渲染 / job history 可以逐步统一消费 `CompositionPlan`。

## Stage-N：前端任务入口统一进入 movie_story

Stage-M 后，两个前端功能虽然都能产出 `CompositionPlan`，但本地任务 runner 仍然直接调用两个旧 pipeline 文件。本轮新增：

23. `edit_modes.py`：统一入口与模式定义，包含 `movie_story_script`、`highlight_script`、`movie_story`、`highlight_recut`、`narrated_highlight_edit`、`raw_highlight` 等归一化逻辑。
24. `edit_result.py`：统一结果包装，向返回 payload 注入 `unified_entry`、`unified_mode`、`unified_artifacts`。
25. `unified_entry.py`：统一前端任务适配层。`local_job_runner` 的影视解说和精彩粗剪入口都先进入这里，再分发到当前兼容 engine。

本轮后：

- `/jobs/movie-story-script` 和 `/jobs/highlight-script` 路由名继续保持前端兼容。
- `start_local_movie_story_script_job` 和 `start_local_highlight_script_job` 不再直接调用两个旧 pipeline，而是调用 `movie_story.unified_entry.run_unified_edit_request`。
- `subtitle_first_pipeline.py` / `highlight_edit_pipeline.py` 暂时保留为兼容 engine，下一轮可继续迁到 legacy 或进一步删除旧 alias。


## Stage-O：旧引擎兼容边界与文档归档

Stage-O 新增 `engines.py`，将 `subtitle_first_pipeline.py` 与 `highlight_edit_pipeline.py` 的兼容调用集中到一个边界。

本轮后：

- `unified_entry.py` 不再直接 import 两个旧 pipeline。
- `engines.py` 是唯一允许 import 旧 pipeline 的兼容层。
- 根目录仅保留 `README.md`，历史报告迁入 `docs/archive/`。
- 下一阶段可继续把旧 pipeline 替换为 native movie_story engine，或者迁入 legacy。

## Stage-P：旧 pipeline 退场边界

Stage-P 新增 `engine_policy.py`、`engine_result.py`、`legacy_engines.py`、`native_engines.py`，让 `engines.py` 从单纯兼容 wrapper 升级为可切换 engine 边界。

本轮后：

- 旧 `subtitle_first_pipeline.py` / `highlight_edit_pipeline.py` 只允许在 `legacy_engines.py` 中被直接 import。
- `engine_backend=auto|legacy|native` 成为显式后端选择参数。
- Stage-P 默认 `auto -> legacy`，native slot 先建立但未启用。

## Stage-Q：精彩粗剪 native backend

Stage-Q 新增 `highlight_native_engine.py`，把“精彩粗剪 / highlight_edit”作为第一个 movie_story native backend 接上。

本轮后：

- `highlight_edit` 的 `native_ready_for()` 返回 true。
- highlight/edit 请求在 `engine_backend=auto` 时默认选择 native。
- `engine_backend=legacy` 仍可强制走旧 `highlight_edit_pipeline.py`。
- `movie_story` 影视解说 native 仍未启用，继续走 legacy，避免在解说链路未完全 parity 前冒进切换。
