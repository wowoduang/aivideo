# Stage-N：统一前端任务入口适配层

Stage-J/K/L 已经把“精彩粗剪”主链的大量候选构建、选择、合成与输出逻辑迁入 `app/services/movie_story/*`。Stage-M 又让影视解说链同步输出 `CompositionPlan`。但是本地任务入口仍然分别直接调用：

- `app.services.highlight_edit_pipeline.run_highlight_edit_pipeline`
- `app.services.subtitle_first_pipeline.run_subtitle_first_pipeline`

Stage-N 不改变前端路由名，不破坏现有两个按钮：

- `/jobs/highlight-script`：精彩粗剪
- `/jobs/movie-story-script`：影视解说

但后端本地任务 runner 统一进入：

```text
app/services/movie_story/unified_entry.py
```

## 新增模块

- `edit_modes.py`：统一入口与模式定义。
- `edit_result.py`：统一结果包装，注入 `unified_entry`、`unified_mode`、`unified_artifacts`。
- `unified_entry.py`：统一前端任务适配层。

## 当前状态

```text
前端两个入口保留
↓
local_job_runner 统一进入 movie_story.unified_entry
↓
旧 pipeline 暂时作为兼容 engine
↓
最终返回 CompositionPlan + script_items
```

下一轮 Stage-O 可继续做：新增统一 API schema、迁移旧 pipeline 到 legacy、清理旧 alias 与重复文档。
