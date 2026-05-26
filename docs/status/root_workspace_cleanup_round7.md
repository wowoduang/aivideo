# Root workspace cleanup round7

## 目标

根目录只保留正式源码、测试、文档、工程配置和可维护工具；运行产物、补丁备份、
临时报告和一次性补丁脚本移动到外部工作区，避免污染源码基线。

外部工作区：

```text
E:\aivideo-workspace
```

## 根目录保留目录

```text
app, docker, docs, resource, scripts, tests, tools, web
```

## 本轮处理记录

| action | source | target | reason |
| --- | --- | --- | --- |
| move | `.patch_backups` | `E:\aivideo-workspace\patch_backups` | 补丁备份目录，非正式源码 |
| move | `.-workspace` | `E:\aivideo-workspace\runtime\dot_workspace` | 测试/运行中间目录 |
| move | `workspace` | `E:\aivideo-workspace\runtime\workspace` | 运行状态和本地 workspace |
| move | `reports` | `E:\aivideo-workspace\reports` | 审计/运行报告 |
| move | `storage` | `E:\aivideo-workspace\storage` | 运行期存储目录 |
| move | `patch_aivideo_audit_tool_round6.py` | `E:\aivideo-workspace\applied_patches\patch_aivideo_audit_tool_round6.py` | 已执行补丁脚本 |
| move | `patch_aivideo_project_hygiene_round4.py` | `E:\aivideo-workspace\applied_patches\patch_aivideo_project_hygiene_round4.py` | 已执行补丁脚本 |
| move | `patch_aivideo_pydantic_warning_round5.py` | `E:\aivideo-workspace\applied_patches\patch_aivideo_pydantic_warning_round5.py` | 已执行补丁脚本 |
| move | `patch_aivideo_root_workspace_cleanup_round7.py` | `E:\aivideo-workspace\applied_patches\patch_aivideo_root_workspace_cleanup_round7.py` | 已执行补丁脚本 |
| move | `audit_aivideo_post_cleanup_contracts.py` | `E:\aivideo-workspace\audit_tools\audit_aivideo_post_cleanup_contracts.py` | 一次性审计脚本 |
| delete_cache | `app\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\api\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\api\routers\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\api\schemas\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\config\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\models\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\repositories\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\schemas\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\llm\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\llm\providers\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\movie_story\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\movie_story\human_narration\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\movie_story\production\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\prompts\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\prompts\documentary\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\prompts\movie_story_narration\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\prompts\short_drama_editing\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\prompts\short_drama_narration\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\SDE\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\SDP\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\services\SDP\utils\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `app\utils\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `tests\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `tests\api\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `tests\movie_story\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |
| delete_cache | `tools\__pycache__` | `None` | Python/pytest 缓存，可安全删除 |

## 可选项状态

- `deprecated` 移动到外部工作区：False
- `config.toml` 移动到外部工作区：False

## 注意

- 本轮不移动 `app/`, `web/`, `tests/`, `docs/`, `tools/`, `scripts/`, `docker/`, `resource/`。
- 默认不移动 `deprecated/`，因为其中可能还有后续迁移价值模块的历史溯源。
- 默认不移动 `config.toml`，因为本地运行可能仍依赖根目录配置。
- 缓存目录只删除 `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`。


## Round9 follow-up: runtime path redirection

Round7 移动了已有根目录运行产物，但全量测试会重新创建 `workspace/`,
`reports/`, `storage/`, `.-workspace/`。原因是少量旧代码仍硬编码
`Path("storage")`, `Path(".-workspace")` 或 `"workspace/state"`。

Round9 已把这些默认路径重定向到 `app.utils.workspace` 管理的外部
workspace：

- WorkbenchStateRepository 默认状态目录 → `workspace.state_dir("workbench")`
- 双轮链 raw_srt debug → `workspace.temp_dir("raw_srt_debug")`
- prompt strategy archive → `workspace.analysis_dir("narration_prompt_strategies")`
- direct runtime legacy audit fallback → `workspace.runtime_dir("debug/...")`
- 相关测试临时输出 → `workspace.temp_dir("tests/...")`

新增测试 `tests/test_no_root_runtime_artifacts.py` 保护该契约。
