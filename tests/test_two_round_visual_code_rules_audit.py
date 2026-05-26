# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for the two_round_visual code-rule audit helper."""

import ast
from pathlib import Path

from tools import audit_two_round_visual_code_rules as audit_rules


def test_original_alias_detection_uses_ast_assignments_only() -> None:
    """String mentions of the forbidden token are allowed; alias assignments are not."""
    harmless = ast.parse('TEXT = "_ORIGINAL_ is mentioned in documentation"\n')
    assert not audit_rules._audit_forbidden_ast(
        tree=harmless,
        relative_path=Path("sample.py"),
    )

    bad = ast.parse("_ORIGINAL_HANDLER = handler\n")
    errors = audit_rules._audit_forbidden_ast(
        tree=bad,
        relative_path=Path("sample.py"),
    )
    assert any("_ORIGINAL_* alias patching" in item for item in errors)


def test_function_length_is_not_a_hard_error() -> None:
    """The audit no longer enforces the obsolete hard 80-line function rule."""
    body = "\n".join("    value += 1" for _ in range(95))
    source = (
        "# -*- coding: utf-8 -*-\n"
        "from __future__ import annotations\n\n"
        "__CONTEXT__ = {}\n\n"
        "def long_but_typed(value: int) -> int:\n"
        f"{body}\n"
        "    return value\n"
    )
    path = Path("virtual_two_round_visual.py")
    errors = audit_rules._audit_ast(text=source, relative_path=path)
    assert errors == []


def test_audit_targets_pass_on_current_official_two_round_visual_files() -> None:
    """The official first-round visual modules satisfy the current audit contract."""
    errors = audit_rules.audit_targets(root=Path("."))
    assert errors == []
