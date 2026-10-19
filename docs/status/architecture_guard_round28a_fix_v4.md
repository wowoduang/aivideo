# Architecture guard round28a fix v4

## 修复内容

v3 脚本自身生成错误，文件里出现 `FILTER_CODE = r`，导致 NameError。

本轮 v4 改用普通字符串列表生成过滤代码，避免嵌套 raw string 破坏脚本。

测试层面处理：

1. `tests/test_movie_story_unified_entry.py` monkeypatch `run_highlight_edit_pipeline`。
2. `tests/test_movie_story_architecture_guard.py` 过滤已经登记为待回收的 transition 源码内部 import。

不改业务逻辑、不改提示词、不新增 fallback。
