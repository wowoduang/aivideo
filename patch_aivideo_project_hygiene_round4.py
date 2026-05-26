# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Round 4 hygiene patch for aivideo.

Purpose:
- Preserve the stable 333-passed checkpoint after movie_story/two_round_visual cleanup.
- Move temporary patch scripts out of the project root into deprecated/legacy_archive/tools/applied_patches.
- Add Git hygiene files before the user initializes a repository.
- Add/refresh handoff/status documents so future AI coding sessions start from the correct architecture.

This script does not change prompts, visual algorithms, runtime routing, or tests.
"""

import argparse
import datetime as _dt
import shutil
from pathlib import Path
from typing import Iterable

PATCH_NAME = "project_hygiene_round4"

APPLIED_PATCHES = [
    "patch_aivideo_cleanup_old_visual_evidence.py",
    "patch_aivideo_contract_cleanup_round2.py",
    "patch_aivideo_full_test_contract_round3.py",
]

GITIGNORE_TEXT = """\
# Local configuration and secrets
/config.toml
*.env
.env

# Python cache/build artifacts
__pycache__/
**/__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
build/
dist/
*.egg-info/

# Node / frontend build artifacts
node_modules/
/web/node_modules/
/web/dist/
/web/.vite/

# Runtime workspaces and generated media
/workspace/
/AIVideo-workspace/
/*-workspace/
/.-workspace/
/storage/temp/
/storage/tasks/
/.patch_backups/
/reports/*.tmp

# OS / editor noise
.DS_Store
Thumbs.db
.vscode/
.idea/
"""

GITATTRIBUTES_TEXT = """\
*.py    text=auto eol=lf
*.ts    text=auto eol=lf
*.tsx   text=auto eol=lf
*.js    text=auto eol=lf
*.json  text=auto eol=lf
*.toml  text=auto eol=lf
*.md    text=auto eol=lf
*.yml   text=auto eol=lf
*.yaml  text=auto eol=lf
*.sh    text=auto eol=lf
"""

LEGACY_TOOLS_README = """\
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
"""

HANDOFF_TEXT = """\
# aivideo 架构交接分析：基础双轮链、视觉增强链与长视频拆短视频主流程

**状态日期**：2026-05-26  
**当前稳定测试基线**：`333 passed, 1 skipped, 1 warning`

## 1. 当前正式主流程

当前 aivideo 只把以下三条作为正式主流程：

```text
1. 基础双轮链
   text-only two_round：完整字幕 → 第一轮结构理解 → 第二轮文案与片段时间码。

2. 视觉增强链
   two_round_visual：第一轮前本地低成本音视频/视觉证据准备 → 第一轮多模态理解 → 第二轮文本写作 → 直接剪辑。

3. 长视频拆短视频流程
   类似抖音/剪映/CapCut 的“长视频生成多个短视频”产品方向。
```

`legacy` 和 `native` 不是正式主流程，也不是 fallback。它们只临时保留，用于提取有价值的确定性模块；价值模块迁移完成后，应进入项目回收站或删除。

## 2. two_round_visual 的准确定义

`two_round_visual` 的目标不是“多看一遍画面”，而是解决基础 text-only 双轮链容易搞错的人物关系、说话人、说话对象、动作归属问题。

正式链路是：

```text
本地音视频/视觉证据准备
  → 生成全片低密度帧 + visual_focus_segments 详细帧
  → 第一轮多模态模型结合完整字幕和少量高价值视觉证据理解全片
  → 第二轮文本模型写文案并给出片段时间码
  → 第二轮后直接剪辑/导出
```

明确禁止：

```text
第二轮后再对 selected_highlights 抽帧
第二轮后人工复选
把 visual_focus_segments 当最终剪辑片段
缺视觉配置时 fallback 到 text-only two_round
恢复 selected_highlight_visual_evidence_workflow 主流程
```

## 3. visual_focus_segments 的准确定义

`visual_focus_segments` 是第一轮前需要详细抽帧的视觉重点时间段。它不是高光，不是最终短视频片段，也不是本地字幕语义分析结果。

本地层主要使用：

```text
shot/scene 边界
画面变化
音频/说话轮次等可计算信号
关键帧预算
字幕时间轴作为对齐和分窗锚点
```

字幕在本地层只用于时间对齐、分窗、对白密度/轮次等可计算信号；剧情含义、人物关系、代词指向交给第一轮多模态大模型理解。

## 4. 已完成的三轮工程收敛

### round1：删除旧后置视觉证据链

- 删除 `movie_story_enable_visual_evidence` 正式主流程旧开关。
- 删除 `local_job_runner.py` 对 selected-highlight 后置抽帧复核 workflow 的调用。
- 将 `selected_highlight_visual_evidence_workflow.py` 和旧测试移入 `deprecated/legacy_archive/`。
- 新增 guard 测试，防止旧后置抽帧链回流。

### round2：修正主流程契约

- `movie_story_visual_focus_segments` 已接入运行时。
- `unified_entry.py` 改成当前正式主流程入口。
- 旧 native/legacy movie_story 标签改为拒绝，不再迁移到当前主流程。
- FunASR 测试去除本机固定 `E:/.../test.wav` 依赖。
- `tests/movie_story + tests/test_movie_story_unified_entry.py`：`97 passed`。

### round3：修正全量测试契约

- 修复 `json_utils`。
- 修正 subprocess 测试 mock 与 `run_cancellable` 的契约。
- 清理旧 native/legacy 测试期望。
- 修正 audit stage 命名空间测试。
- 不改两轮提示词。
- 全量测试：`333 passed, 1 skipped, 1 warning`。

## 5. 后续代码规则

后续 AI 写代码前必须遵守：

```text
不改基础双轮提示词，除非用户明确要求。
不改视觉增强提示词，除非用户明确要求。
不新增 fallback，不静默吞异常。
不加 compatibility wrapper 来兼容旧测试。
不恢复 native/legacy movie_story 主流程。
优先直接重构、删除错误残留、统一字段契约。
代码按功能模块化，不机械卡 80 行，但必须职责清晰、可测试。
```

## 6. 推荐验收命令

```bash
cd /e/aivideo
python -m compileall -q app tests
python -m pytest -q tests
```

当前稳定基线：

```text
333 passed, 1 skipped, 1 warning
```

唯一 warning 是 Pydantic V2 class-based config 弃用提示，暂不影响当前主流程。

## 7. 新会话开场提示

建议在新会话开头粘贴：

```text
请先阅读 docs/status/aivideo_architecture_handoff_analysis.md。
当前 aivideo 正式主流程只有：基础双轮链、视觉增强链、长视频拆短视频流程。
不要改两轮提示词，不要恢复 legacy/native 主流程，不要 fallback，不要 compatibility wrapper。
two_round_visual 是第一轮前本地视觉证据准备 + 第一轮多模态理解，不是第二轮后 selected-highlight 抽帧。
当前测试基线：333 passed, 1 skipped, 1 warning。
```
"""

STABLE_BASELINE_TEXT = """\
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
"""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_text(path: Path, text: str, *, dry_run: bool, actions: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _read_text(path)
    if current == text:
        return
    actions.append(f"{'would write' if dry_run else 'write'}: {path}")
    if not dry_run:
        path.write_text(text, encoding="utf-8", newline="\n")


def _backup_file(path: Path, backup_root: Path) -> None:
    if not path.exists():
        return
    target = backup_root / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _move_if_present(src: Path, dst: Path, *, dry_run: bool, actions: list[str], backup_root: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        actions.append(f"skip move, archive already exists: {src} -> {dst}")
        return
    actions.append(f"{'would move' if dry_run else 'move'}: {src} -> {dst}")
    if not dry_run:
        _backup_file(src, backup_root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def _append_status_rounds(project: Path, *, dry_run: bool, actions: list[str]) -> None:
    path = project / "docs" / "status" / "two_round_visual_status.md"
    if not path.exists():
        return
    text = _read_text(path)
    updated = text.replace("**最后更新**：2026-05-25", "**最后更新**：2026-05-26")
    marker = "## 8. 2026-05-26 后续收敛状态"
    block = """

## 8. 2026-05-26 后续收敛状态

```text
round2：已完成 movie_story_visual_focus_segments API → runtime 映射，unified_entry 只保留当前正式主流程，旧 native/legacy 标签拒绝进入 movie_story 主流程。
round3：已修正全量测试契约，确认当前稳定测试基线为 333 passed, 1 skipped, 1 warning。
```

后续不得为了旧测试或旧脚本恢复 selected-highlight 后置视觉证据链，也不得把 legacy/native 重新接回 movie_story 主流程。
"""
    if marker not in updated:
        updated = updated.rstrip() + block + "\n"
    _write_text(path, updated, dry_run=dry_run, actions=actions)


def _append_pending_checkpoint(project: Path, *, dry_run: bool, actions: list[str]) -> None:
    path = project / "PENDING.md"
    if not path.exists():
        return
    text = _read_text(path)
    marker = "### [DONE-006] 全量测试契约收敛到稳定基线"
    block = """

### [DONE-005] 修正 visual_focus_segments API 到运行时契约

**完成日期**：2026-05-26

**方案**：

- `movie_story_visual_focus_segments` 作为正式 API 字段进入 `two_round_visual` 运行时。
- `unified_entry.py` 明确只接受当前正式 movie_story 主流程。
- 旧 native/legacy movie_story 标签拒绝进入正式主流程，不再迁移为当前模式。
- FunASR 测试去除本机固定 wav 路径依赖。

### [DONE-006] 全量测试契约收敛到稳定基线

**完成日期**：2026-05-26

**结果**：

```text
333 passed, 1 skipped, 1 warning
```

**方案**：

- 修正 `json_utils` 对 fenced JSON 和双大括号 JSON 的解析。
- 修正 FFmpeg 相关测试 mock，使其符合当前 `run_cancellable` 调用契约。
- 更新旧 native/legacy 测试，防止旧 movie_story 主流程回流。
- 修正 audit stage 命名空间测试期望。
- 未改动基础双轮提示词和视觉增强提示词。
"""
    if marker not in text:
        updated = text.rstrip() + block + "\n"
        _write_text(path, updated, dry_run=dry_run, actions=actions)


def run(project: Path, *, dry_run: bool) -> None:
    project = project.resolve()
    if not (project / "app").exists() or not (project / "tests").exists():
        raise SystemExit(f"not an aivideo project root: {project}")

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = project / ".patch_backups" / f"{PATCH_NAME}_{stamp}"
    actions: list[str] = []

    _write_text(project / ".gitignore", GITIGNORE_TEXT, dry_run=dry_run, actions=actions)
    _write_text(project / ".gitattributes", GITATTRIBUTES_TEXT, dry_run=dry_run, actions=actions)
    _write_text(
        project / "deprecated" / "legacy_archive" / "tools" / "README.md",
        LEGACY_TOOLS_README,
        dry_run=dry_run,
        actions=actions,
    )
    _write_text(
        project / "docs" / "status" / "aivideo_architecture_handoff_analysis.md",
        HANDOFF_TEXT,
        dry_run=dry_run,
        actions=actions,
    )
    _write_text(
        project / "docs" / "status" / "stable_baseline_after_round3.md",
        STABLE_BASELINE_TEXT,
        dry_run=dry_run,
        actions=actions,
    )
    _append_status_rounds(project, dry_run=dry_run, actions=actions)
    _append_pending_checkpoint(project, dry_run=dry_run, actions=actions)

    archive_dir = project / "deprecated" / "legacy_archive" / "tools" / "applied_patches"
    for name in APPLIED_PATCHES:
        _move_if_present(
            project / name,
            archive_dir / name,
            dry_run=dry_run,
            actions=actions,
            backup_root=backup_root,
        )

    prefix = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"{prefix} project: {project}")
    for action in actions:
        print(f"- {action}")
    if not actions:
        print("- no changes")
    if not dry_run:
        print(f"backup_root: {backup_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Round 4 project hygiene patch for aivideo.")
    parser.add_argument("--project", required=True, help="Project root, e.g. E:/aivideo or .")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(Path(args.project), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
