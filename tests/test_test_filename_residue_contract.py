# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


RENAMED_GUARD_TESTS = {
    "tests/test_removed_pipeline_final_contract_round48.py",
    "tests/test_movie_story_orphan_candidates_recycled_round51.py",
    "tests/test_llm_tests_out_of_app_round52.py",
}


STABLE_GUARD_TESTS = {
    "tests/test_removed_pipeline_final_contract.py",
    "tests/test_movie_story_orphan_candidates_recycled.py",
    "tests/test_llm_tests_out_of_app.py",
}


ROUND_TOKEN_PATTERNS = (
    "_round48",
    "_round51",
    "_round52",
)


def test_round_numbered_guard_test_files_are_renamed_after_round53() -> None:
    """稳定 guard 测试文件名不应继续携带历史 round 编号。"""
    present_old_paths = [
        relative
        for relative in sorted(RENAMED_GUARD_TESTS)
        if (PROJECT_ROOT / relative).exists()
    ]
    missing_new_paths = [
        relative
        for relative in sorted(STABLE_GUARD_TESTS)
        if not (PROJECT_ROOT / relative).exists()
    ]

    assert present_old_paths == []
    assert missing_new_paths == []


def test_stable_guard_test_files_do_not_reference_old_round_filenames() -> None:
    """重命名后的 guard 内部不应继续引用旧文件名。"""
    violations: list[str] = []

    for relative in sorted(STABLE_GUARD_TESTS):
        path = PROJECT_ROOT / relative
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        for old_relative in RENAMED_GUARD_TESTS:
            if old_relative in text:
                violations.append(f"{relative}: {old_relative}")
        for token in ROUND_TOKEN_PATTERNS:
            if token in text:
                violations.append(f"{relative}: {token}")

    assert violations == []
