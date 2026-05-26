# Movie story functional boundaries round12

## 目的

Round11 已建立静态功能契约：

```text
app/services/movie_story/functional_contracts.py
```

Round12 在此基础上新增可复用函数边界：

```text
app/services/movie_story/functional_boundaries.py
```

它不是业务调度器，不 import 旧 native/legacy 实现，只提供后续重构可引用的判断函数。

## 新增能力

- `classify_module_boundary(module)`
  - 判断模块是否 active、support、migration review、retired candidate。
- `assert_new_code_may_reference(module, reason=...)`
  - 防止新补丁把旧 movie_story native/legacy 主流程接回 runtime。
- `mainflow_modules()`
  - 返回当前正式主流程模块。
- `support_modules()`
  - 返回当前正式支撑模块。
- `migration_review_modules()`
  - 返回需要拆分审查、但不能直接删除的长视频拆短视频相关模块。
- `modules_blocked_for_new_runtime()`
  - 返回禁止新 runtime 引用的待退休模块。
- `module_to_source_path()` / `source_path_to_module()`
  - 给审计工具做路径和 dotted module 转换。

## 当前边界

允许作为正式主流程：

```text
app.services.movie_story.two_round_narration
app.services.movie_story.two_round_visual_narration
```

禁止新 runtime 主动引用：

```text
app.services.movie_story.movie_story_native_engine
app.services.movie_story.legacy_understanding_adapter
app.services.subtitle_first_pipeline
```

需要继续拆分审查，不能因历史命名直接删：

```text
app.services.movie_story.highlight_edit_selection
app.services.movie_story.timeline_runtime
```

## 后续用法

后续任何自动补丁要新增 movie_story 依赖时，应优先调用：

```python
assert_new_code_may_reference(module, reason="说明为什么需要引用")
```

这样可以把“旧 native/legacy 不得回流”的口头规则变成可测试代码。
