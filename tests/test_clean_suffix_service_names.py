# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


CLEAN_MODULE_BASES = (
    "generate_narration_script",
    "plot_understanding",
    "story_validator",
    "subtitle_review",
)


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def _legacy_tokens() -> tuple[str, ...]:
    """运行时生成旧模块 token，避免 guard 文件自身写入旧 token 字面量。"""
    suffix = "_" + "clean"
    return tuple(f"{base}{suffix}" for base in CLEAN_MODULE_BASES)


def test_no_clean_suffix_python_files_in_app_services() -> None:
    """app/services 下不应继续保留旧 clean 后缀文件。"""
    root = PROJECT_ROOT / "app" / "services"
    if not root.exists():
        return

    suffix = "_" + "clean.py"
    violations = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in root.rglob("*" + suffix)
        if "__pycache__" not in path.parts
    ]

    assert violations == []


def test_no_clean_suffix_test_filenames_after_service_rename() -> None:
    """tests 下不应继续保留旧 clean 后缀测试文件。"""
    root = PROJECT_ROOT / "tests"
    if not root.exists():
        return

    suffix = "_" + "clean.py"
    violations = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in root.rglob("test_*" + suffix)
        if "__pycache__" not in path.parts
    ]

    assert violations == []


def test_no_clean_suffix_module_tokens_in_active_code() -> None:
    """app/tests/tools 中不应继续引用已改名的旧模块 token。"""
    violations: list[str] = []
    legacy_tokens = _legacy_tokens()

    for root_name in ("app", "tests", "tools"):
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            matched = [token for token in legacy_tokens if token in text]
            if matched:
                violations.append(f"{_normalize(path.relative_to(PROJECT_ROOT))}: {matched}")

    assert violations == []
