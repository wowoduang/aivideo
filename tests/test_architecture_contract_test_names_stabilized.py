# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DISALLOWED_TEST_FILENAME_TOKENS = (
    "migration_stage",
)


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_no_migration_stage_test_filenames_after_round60() -> None:
    """稳定测试文件名不应继续携带 migration_stage 临时阶段命名。"""
    violations = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "tests").rglob("test_*.py")
        if any(token in path.name for token in DISALLOWED_TEST_FILENAME_TOKENS)
    ]

    assert violations == []
