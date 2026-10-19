# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def _legacy_uppercase_package_tokens() -> tuple[str, ...]:
    """Build legacy tokens without embedding old full paths as source literals."""
    return (
        ".".join(("app", "services", "SDE")),
        ".".join(("app", "services", "SDP")),
        "/".join(("app", "services", "SDE")),
        "/".join(("app", "services", "SDP")),
        "\\".join(("app", "services", "SDE")),
        "\\".join(("app", "services", "SDP")),
    )


def test_no_uppercase_sde_sdp_package_paths_in_active_python_code() -> None:
    """Active Python code should not reference removed uppercase package paths."""
    violations: list[str] = []
    forbidden_tokens = _legacy_uppercase_package_tokens()

    for root_name in ("app", "tests", "tools"):
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in forbidden_tokens):
                violations.append(_normalize(path.relative_to(PROJECT_ROOT)))

    assert violations == []


def test_short_drama_package_guard_names_are_stable() -> None:
    """Guard test filenames should use final short_drama package terminology."""
    assert (PROJECT_ROOT / "tests/test_short_drama_packages_contract.py").exists()
    assert (PROJECT_ROOT / "tests/test_short_drama_package_names_contract.py").exists()
    assert not (PROJECT_ROOT / "tests/test_sde_sdp_package_init.py").exists()
    assert not (PROJECT_ROOT / "tests/test_sde_sdp_guard_name_stabilized.py").exists()
