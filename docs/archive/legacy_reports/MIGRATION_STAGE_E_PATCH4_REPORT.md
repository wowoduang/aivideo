# Stage E Patch 4 - stale cache bypass and Stage-E-ready diagnostics

修复点：

1. Stage-D live-fill 工具不再被旧的无效 cache 阻断。
   - 只有 cache 中的 llm_result 满足 Stage-E 最小回写字段时才复用。
   - 旧 cache 如果是空结果、review、不含最小字段，会自动标记为 stale_or_incomplete 并继续执行 live LLM。

2. live_result_count 现在表示“可用于 Stage-E 回写的结果数”，而不是简单判断是否存在 cache 文件。

3. live_failed_items 会展示：
   - Stage-E 缺失的最小字段
   - cache_quality
   - raw_preview / call_exception / json_parse_failed 等原因

4. 仍然不会调用最终 narration 生成。只补 Stage-D global/local understanding 结果。
