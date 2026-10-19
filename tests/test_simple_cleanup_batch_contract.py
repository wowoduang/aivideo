# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


ROUND_SUFFIX_PATTERN = re.compile(r"^test_.*_round\d+\.py$")


LEFTOVER_EMPTY_DIRS = (
    "tests/services/llm",
    "tests/services",
)


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_no_round_number_suffix_test_files_after_batch_cleanup() -> None:
    """稳定测试文件名不应保留 _roundNN 历史阶段后缀。"""
    violations = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "tests").rglob("test_*.py")
        if ROUND_SUFFIX_PATTERN.match(path.name)
    ]

    assert violations == []


def test_old_empty_llm_test_dirs_are_not_left_after_manual_move() -> None:
    """LLM 手工检查已移动到 tests/manual/llm，旧空目录不应保留。"""
    violations = [
        relative
        for relative in LEFTOVER_EMPTY_DIRS
        if (PROJECT_ROOT / relative).exists()
        and (PROJECT_ROOT / relative).is_dir()
        and not any((PROJECT_ROOT / relative).iterdir())
    ]

    assert violations == []
