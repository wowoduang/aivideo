# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# two_round 是当前正式业务链路名，不属于 refactor round 残留。
# stage_index 是 runtime audit 的正式字段名，不属于 migration stage 残留。
LEGACY_TEST_FILENAME_PATTERNS = (
    re.compile(r"migration_stage", re.IGNORECASE),
    re.compile(r"stage_[a-d](?:_|$)", re.IGNORECASE),
    re.compile(r"three_stage_refactor", re.IGNORECASE),
    re.compile(r"round\d+", re.IGNORECASE),
)


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_no_legacy_refactor_history_tokens_in_test_filenames() -> None:
    """测试文件名不应继续使用迁移轮次/阶段编号作为正式命名。"""
    violations: list[str] = []

    for path in (PROJECT_ROOT / "tests").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        name = path.name
        if any(pattern.search(name) for pattern in LEGACY_TEST_FILENAME_PATTERNS):
            violations.append(_normalize(path.relative_to(PROJECT_ROOT)))

    assert violations == []
