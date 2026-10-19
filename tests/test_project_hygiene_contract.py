# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


ROOT_TRANSIENT_DIRS = {
    ".patch_backups",
    ".-workspace",
    "reports",
    "workspace",
    "tmp",
    "temp",
}


ROOT_TRANSIENT_FILE_PREFIXES = (
    "patch_",
    "patch-aivideo",
    "patch_aivideo",
    "audit_",
    "audit-aivideo",
    "audit_aivideo",
    "auto_patch_",
    "auto_fix_",
    "auto_repair_",
)


ROOT_TRANSIENT_FILE_SUFFIXES = (
    ".bak",
    ".tmp",
    ".temp",
    ".orig",
    ".rej",
    ".patch",
    ".diff",
    ".log",
    ".zip",
    ".rar",
    ".7z",
)


DISALLOWED_DOC_PATH_TOKENS = (
    "legacy",
    "native",
    "retired",
    "retirement",
    "old_chain",
    "old-chain",
    "direct_runtime",
    "direct-runtime",
    "subtitle_first",
    "subtitle-first",
)


def _is_transient_root_file(path: Path) -> bool:
    name = path.name
    lowered = name.lower()
    return (
        any(lowered.startswith(prefix) for prefix in ROOT_TRANSIENT_FILE_PREFIXES)
        or any(lowered.endswith(suffix) for suffix in ROOT_TRANSIENT_FILE_SUFFIXES)
        or "_backup" in lowered
        or ".bak_" in lowered
    )


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_project_root_has_no_transient_artifacts() -> None:
    """项目根目录不应保留补丁脚本、审计脚本、压缩包、临时备份或运行产物目录。"""
    transient_dirs = [
        name
        for name in sorted(ROOT_TRANSIENT_DIRS)
        if (PROJECT_ROOT / name).exists()
    ]
    transient_files = [
        path.name
        for path in PROJECT_ROOT.iterdir()
        if path.is_file() and _is_transient_root_file(path)
    ]

    assert transient_dirs == []
    assert transient_files == []


def test_docs_tree_has_no_removed_old_path_names() -> None:
    """docs 树不应再出现已移除旧链路的命名路径。"""
    docs_root = PROJECT_ROOT / "docs"
    if not docs_root.exists():
        return

    violations: list[str] = []
    for path in docs_root.rglob("*"):
        relative = _normalize(path.relative_to(PROJECT_ROOT)).lower()
        if any(token in relative for token in DISALLOWED_DOC_PATH_TOKENS):
            violations.append(relative)

    assert violations == []


def test_docs_tree_has_no_empty_directories() -> None:
    """docs 树清理后不应留下空目录。"""
    docs_root = PROJECT_ROOT / "docs"
    if not docs_root.exists():
        return

    empty_dirs = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in docs_root.rglob("*")
        if path.is_dir() and not any(path.iterdir())
    ]

    assert empty_dirs == []
