# legacy_archive/tools

本目录保存已经执行过、且不应继续放在项目根目录的临时补丁脚本。

这些脚本只用于人工追溯历史变更：

- `applied_patches/patch_aivideo_cleanup_old_visual_evidence.py`
  - round1：删除 selected-highlight 后置视觉证据旧链路。
- `applied_patches/patch_aivideo_contract_cleanup_round2.py`
  - round2：修正 `movie_story_visual_focus_segments` API → runtime 映射，收紧 `unified_entry` 当前主流程。
- `applied_patches/patch_aivideo_full_test_contract_round3.py`
  - round3：修正全量测试契约，确认 `333 passed, 1 skipped, 1 warning`。

约束：

1. 不得从正式源码 import 本目录下任何脚本。
2. 不得为了旧脚本里的过时 token 恢复 compatibility wrapper。
3. 后续新补丁若执行完成，也应移入本目录或 `.patch_backups/`，不要长期堆在项目根目录。
