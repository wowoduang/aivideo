# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PACKAGES = (
    "app/services/short_drama_editing",
    "app/services/short_drama_production",
)


def _legacy_uppercase_package_paths() -> tuple[str, str]:
    """Build removed package paths without embedding old slash-path literals."""
    return (
        "/".join(("app", "services", "SDE")),
        "/".join(("app", "services", "SDP")),
    )


def test_short_drama_packages_use_lowercase_names() -> None:
    """Short drama packages should use lowercase, descriptive package names."""
    for relative in EXPECTED_PACKAGES:
        package = PROJECT_ROOT / relative
        assert package.exists(), relative
        assert (package / "__init__.py").exists(), relative

    for relative in _legacy_uppercase_package_paths():
        assert not (PROJECT_ROOT / relative).exists(), relative


def test_short_drama_package_files_remained_migrated() -> None:
    """The known implementation files should remain under new packages."""
    assert (
        PROJECT_ROOT
        / "app/services/short_drama_editing/short_drama_explanation.py"
    ).exists()
    assert (
        PROJECT_ROOT
        / "app/services/short_drama_production/generate_script_short.py"
    ).exists()
    assert (
        PROJECT_ROOT
        / "app/services/short_drama_production/utils/short_schema.py"
    ).exists()
