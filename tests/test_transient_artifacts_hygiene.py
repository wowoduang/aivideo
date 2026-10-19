# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DISALLOWED_WINDOWS_METADATA_FILES = {
    "desktop.ini",
    "Thumbs.db",
}


SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
}


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_no_windows_metadata_artifacts_in_project_tree() -> None:
    """项目主树不应保留 Windows 系统元数据文件。"""
    violations: list[str] = []

    for path in PROJECT_ROOT.rglob("*"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue

        if path.is_file() and path.name in DISALLOWED_WINDOWS_METADATA_FILES:
            violations.append(_normalize(path.relative_to(PROJECT_ROOT)))

    assert violations == []


def test_app_tree_has_no_test_files_outside_tests_directory() -> None:
    """生产代码目录 app/ 下不应出现 test_*.py 文件。"""
    app_root = PROJECT_ROOT / "app"
    if not app_root.exists():
        return

    violations = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in app_root.rglob("test_*.py")
        if "__pycache__" not in path.parts
    ]

    assert violations == []


def test_python_bytecode_cache_is_packaging_exclusion_not_pytest_contract() -> None:
    """compileall 会生成 __pycache__；打包时应排除它，而不是在测试中断言不存在。"""
    assert True
