# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


OLD_APP_TEST_PATHS = {
    "app/services/llm/test_litellm_integration.py",
    "app/services/llm/test_llm_service.py",
}


COLLECTED_TEST_PATHS = {
    "tests/services/llm/test_litellm_integration.py",
    "tests/services/llm/test_llm_service.py",
}


MANUAL_CHECK_PATHS = {
    "tests/manual/llm/litellm_integration_check.py",
    "tests/manual/llm/llm_service_check.py",
}


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def test_llm_test_files_are_not_left_in_app_services_after() -> None:
    """LLM 测试文件不应继续放在生产代码目录 app/services/llm。"""
    present_old_paths = [
        relative
        for relative in sorted(OLD_APP_TEST_PATHS)
        if (PROJECT_ROOT / relative).exists()
    ]

    assert present_old_paths == []


def test_unstable_llm_checks_are_not_collected_by_default_pytest() -> None:
    """依赖真实 provider/异步环境的 LLM 检查不应位于 pytest 默认收集路径。"""
    present_collected_paths = [
        relative
        for relative in sorted(COLLECTED_TEST_PATHS)
        if (PROJECT_ROOT / relative).exists()
    ]

    assert present_collected_paths == []


def test_llm_manual_check_files_exist_after_fix() -> None:
    """被移动的 LLM 集成检查应保留在 tests/manual/llm 下供人工运行。"""
    missing_manual_paths = [
        relative
        for relative in sorted(MANUAL_CHECK_PATHS)
        if not (PROJECT_ROOT / relative).exists()
    ]

    assert missing_manual_paths == []


def test_app_services_llm_has_no_test_py_files_after() -> None:
    """app/services/llm 下不应再出现 test_*.py。"""
    root = PROJECT_ROOT / "app" / "services" / "llm"
    if not root.exists():
        return

    test_files = [
        _normalize(path.relative_to(PROJECT_ROOT))
        for path in root.rglob("test_*.py")
        if "__pycache__" not in path.parts
    ]

    assert test_files == []
