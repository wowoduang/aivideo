# Narration Quality Hard Fix

本次修复目标不是“流程能跑完”，而是“输出必须像影视解说，不能像台词复述”。

## 修复点

1. **新增反复述质量门禁**
   - `generate_narration_script_clean.py` 增加 `_is_verbatim_like()`。
   - 检测 narration 是否连续照抄字幕、是否大段重合、是否把字幕原文当解说。
   - 生成后、review 后、最终 script item 构建前都会检查。

2. **LLM 文案如果像字幕复述，会强制二次修复**
   - 新增 `_repair_verbatim_with_llm()`。
   - 当 LLM 输出过于贴近字幕时，使用专门的“反台词复述”修复 prompt 重新改写。
   - 修复失败时使用本地反复述解说句，不再交付原字幕。

3. **fallback 不再复制字幕**
   - 旧 fallback 会优先使用 `real_narrative_state/surface/subtitle_text`，这些字段在无 LLM 时经常就是原字幕。
   - 现在 fallback 使用 `_local_commentary_narration()`，输出“剧情功能/人物处境/矛盾推进”类型解说。

4. **局部理解的无 LLM heuristic 不再把字幕原文写回理解字段**
   - `plot_understanding_clean._heuristic_local_understanding()` 改为生成保守剧情解释。
   - 例如“催征税银/遍地饥民”会被解释成“皇权压力和民间困境正面冲突”，而不是照抄台词。

5. **提高中文解说字数预算**
   - 原来短片段预算过低，6-10 秒片段经常只能写 15-22 个字，导致文案被截成碎句。
   - 现在选中高光使用更适合中文 TTS 的预算策略，并在 `apply_timeline_budget()` 中保留已有更高预算。

6. **最终脚本增加质量标记**
   - 每条 script item 增加 `narration_quality`：
     - `anti_verbatim_checked`
     - `verbatim_like_after_repair`
     - `source_text_length`

7. **提示词强化**
   - `movie_story_narration/narration_generation.py` 明确禁止连续照抄字幕 8 个以上汉字。
   - 明确要求输出“这段剧情在交代什么/推动什么/暴露什么矛盾”，不能写成“某人说了什么”。

## 针对本次用户审计包的验证

使用 `run_20260502_180430` 中的高光字幕样例做本地反复述验证：

- 输入：`诺，皇上，再过两个月可臣妾的生日了`
- 输出：`一上来，朝廷钱粮已经吃紧，后宫却还惦记排场，`
- 反复述检测：通过

- 输入：`朕现在就任命你为钦差大臣，赴各地催征税银...`
- 输出：`这里的重点是，皇权把催税压力继续往下压，可民间早已被灾荒逼到边缘，`
- 反复述检测：通过

## 测试

新增：

- `tests/test_narration_quality_anti_recitation.py`

已通过：

```bash
pytest -q tests/test_narration_quality_anti_recitation.py \
          tests/test_generate_narration_script_clean.py \
          tests/test_plot_understanding_clean.py \
          tests/test_movie_story_flow_debug_fix.py
# 12 passed
```

并执行：

```bash
python3 -m compileall -q app/services app/api app/utils
```

## 注意

这版不是绕开正式链路：

- 有 LLM 时仍走正式 LLM 解说生成。
- LLM 输出不合格时强制修复。
- 无 LLM 或 LLM 失败时也不能把字幕原文交付，只能输出保守解说。
