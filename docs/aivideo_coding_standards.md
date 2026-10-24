### 8.0 先复用现有实现，不重复造轮子

新增风格/模板/Prompt 时，必须优先复用现有实现，而不是另起一套算法或配置体系。

**优先顺序：**
1. 先检查是否已经存在相同能力：`narration_style_templates.json`、`two_round_narration.py`、`narration_engine.py`、`narration_writer.py`
2. 若已有能力可扩展，则在现有模块上增加配置项，不新建平行的 style registry / prompt engine
3. 只有在确实无法复用时，才新增新模块，并必须在 PR 说明“为什么现有实现不能扩展”

**必须遵守：**
- 新增影视类型/解说风格优先写进 `app/services/movie_story/narration_style_templates.json`
- Prompt 风格扩展优先在 `app/services/movie_story/two_round_narration.py` 的现有模板入口上增加 `style_instruction`
- 不允许为同一类需求复制一套完全独立的风格系统、if/else 分支或 prompt 工厂
- 若有新风格项，允许保留一个默认值：`documentary:neutral_cinematic`

**正例：**
```python
style_cfg = resolve_style_config(video_type="documentary", narration_style="neutral_cinematic")
writer_prompt = build_writer_prompt(analysis_result, video_type="documentary", narration_style="neutral_cinematic")
```

**反例：**
```python
if style == "documentary":
    prompt = "..."
elif style == "historical_drama":
    prompt = "..."
# 继续新增很多 if/else，最终形成重复造轮子
```

---

