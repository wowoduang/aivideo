# 新版本项目工程化修复报告

本次修复目标：清理多版本 runtime 命名和历史遗留入口，恢复成熟视频解说生成链路，并让新项目的时间线/高光能力与旧项目的 LLM 解说能力正确衔接。

## 1. Runtime 命名与多版本清理

- 删除 active 目录中的 历史多版本 runtime 文件。
- 新增语义化 runtime：
  - `app/services/movie_story/timeline_runtime.py`：负责权威时间线、切片、视觉边界和高光候选。
  - `app/services/movie_story/story_runtime.py`：负责故事运行时适配、typed highlight 选择和最终无重定时规范化 fallback。
- 清理 active source 中的 历史版本号 runtime 命名引用。
- 更新 `movie_story/README.md`，将文档改成面向职责边界的说明，而不是版本号说明。

## 2. 修复视频解说主链路

- 删除 `subtitle_first_pipeline.py` 底部同名 passthrough adapter 覆盖逻辑。
- 恢复 `generate_narration_script_clean.generate_narration_from_scene_evidence` 作为成熟 LLM 解说生成入口。
- 将旧的裸 passthrough 解说函数保留为语义化 fallback：`normalize_script_items_without_retiming`，不再伪装成 LLM 解说生成器。
- 明确主流程：
  1. timeline runtime 负责时间线与高光选择。
  2. subtitle-first pipeline 负责聚合 rich evidence。
  3. legacy narration engine 负责最终影视解说文案。

## 3. 修复高光到解说的证据聚合

- 重写 `_build_highlight_narration_segments`。
- selected highlights 不再直接 passthrough 成 narration。
- 高光会重新聚合源 scene evidence，包括：
  - subtitle/main text evidence
  - surface dialogue meaning
  - real narrative state
  - local understanding
  - story validation
  - plot function / importance level
  - visual summary / representative frames
  - speaker names / speaker turns / exchange pairs
  - raw voice retain suggestion
  - global summary
- 这样最终送给 LLM 的是 rich evidence，而不是单薄字幕文本。

## 4. 修复高光选择副作用

- `story_runtime.extract_highlights` 现在只负责选择高光。
- 移除内部偷偷调用 narration engine 但结果又不进入最终输出的副作用。
- 生成解说统一由 subtitle-first pipeline 的 narration 阶段完成。

## 5. 修复视觉边界保护

- `timeline_runtime.protect_visual_boundaries` 不再只识别 `ffmpeg_scene`。
- 新增统一视觉边界判断，覆盖：
  - `ffmpeg_scene`
  - `pyscenedetect*`
  - `internal_visual_cut`
- 避免默认 PySceneDetect 边界绕过字幕内部边界保护。

## 6. 前端与配置安全修复

- 修复 `web/src/lib/api.ts`：前端不再默认把 `qwen3.6-plus` 当成 `asr_backend` 传给后端。
- 清理 `config.toml`，用安全示例配置替换，避免源码包携带真实密钥。
- 修复 `app/config/config.py` 配置加载文件句柄未关闭问题。

## 7. 已做校验

- active source 已检查不再出现 历史版本号 runtime 引用。
- 关键 Python 文件已通过 AST 语法解析。
- `movie_story.timeline_runtime` 与 `movie_story.story_runtime` 已做目标导入检查。
- `normalize_script_items_without_retiming` 已做基础 sanity check。

注意：本环境下完整 pytest 执行存在超时，未声明完整测试套件通过。建议你在本机依赖环境完整安装后执行 `pytest` 和一次端到端视频解说任务验证。
