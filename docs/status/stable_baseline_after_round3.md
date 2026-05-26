# stable baseline after round3

**日期**：2026-05-26  
**基线**：movie_story / two_round_visual 主流程契约收敛后稳定点

## 测试结果

```text
333 passed, 1 skipped, 1 warning in 26.61s
```

## 已完成

```text
round1：删除 selected-highlight 后置视觉证据旧链路。
round2：修正 visual_focus_segments API → runtime 映射，收紧 unified_entry 当前主流程。
round3：修正全量测试契约，清理旧 native/legacy 主流程测试期望。
```

## 当前 warning

Pydantic V2 对 class-based `config` 的弃用提示。该 warning 不影响当前主流程，可作为后续依赖升级规范债单独处理。

## 下一阶段建议

```text
1. 保存 Git 基线。
2. 清理临时补丁脚本和审计脚本。
3. 整理 deprecated/legacy_archive。
4. 逐批处理 print/logging/_ORIGINAL_/重复函数等规范债。
5. 迁移 native/legacy 中确有价值的确定性模块，迁移完成后彻底归档或删除旧入口。
```
