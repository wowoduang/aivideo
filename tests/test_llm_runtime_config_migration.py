# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def _legacy_module_token() -> str:
    """Build the old module token without embedding it as one source literal."""
    return ".".join(("app", "services", "llm_config"))


def test_legacy_root_llm_config_file_was_migrated() -> None:
    """LLM runtime config should live under app/services/llm/."""
    assert not (PROJECT_ROOT / "app" / "services" / "llm_config.py").exists()
    assert (PROJECT_ROOT / "app" / "services" / "llm" / "runtime_config.py").exists()


def test_active_code_imports_llm_runtime_config_package_path() -> None:
    """app/tests/tools should not import the legacy root config module."""
    legacy_token = _legacy_module_token()
    violations: list[str] = []

    for root_name in ("app", "tests", "tools"):
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if legacy_token in text:
                violations.append(_normalize(path.relative_to(PROJECT_ROOT)))

    assert violations == []


def test_runtime_config_exports_existing_llm_config_functions() -> None:
    """Migration preserves the old text/vision config contract."""
    from app.services.llm.runtime_config import (
        get_text_llm_config,
        get_vision_llm_config,
    )

    assert callable(get_text_llm_config)
    assert callable(get_vision_llm_config)
