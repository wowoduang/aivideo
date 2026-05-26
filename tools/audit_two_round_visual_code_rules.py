# -*- coding: utf-8 -*-
from __future__ import annotations

"""Audit code-rule basics for two_round_visual files."""

import ast
import sys
from pathlib import Path

TARGETS = [
    Path("app/services/movie_story/shot_boundary_detector.py"),
    Path("app/services/movie_story/scene_segmenter.py"),
    Path("app/services/movie_story/visual_focus_segments.py"),
    Path("app/services/movie_story/visual_timeline_sampler.py"),
    Path("app/services/movie_story/two_round_visual_input_packager.py"),
    Path("app/services/movie_story/two_round_visual_narration.py"),
]

FORBIDDEN_PATTERNS = ("print(", "import logging", "logging.", "_ORIGINAL_")


def main() -> None:
    root = Path(".").resolve()
    errors: list[str] = []
    for relative_path in TARGETS:
        errors.extend(_audit_file(root / relative_path, relative_path=relative_path))
    if errors:
        raise SystemExit("\n".join(errors))
    sys.stdout.write("two_round_visual code-rule audit passed\n")


def _audit_file(path: Path, *, relative_path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing file: {relative_path}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors.extend(_audit_header(lines=lines, relative_path=relative_path))
    errors.extend(_audit_size(lines=lines, relative_path=relative_path))
    errors.extend(_audit_forbidden(text=text, relative_path=relative_path))
    errors.extend(_audit_ast(text=text, relative_path=relative_path))
    return errors


def _audit_header(*, lines: list[str], relative_path: Path) -> list[str]:
    errors: list[str] = []
    if len(lines) < 1 or lines[0] != "# -*- coding: utf-8 -*-":
        errors.append(f"{relative_path}: missing utf-8 header")
    if len(lines) < 2 or lines[1] != "from __future__ import annotations":
        errors.append(f"{relative_path}: missing future annotations header")
    return errors


def _audit_size(*, lines: list[str], relative_path: Path) -> list[str]:
    if len(lines) > 600:
        return [f"{relative_path}: file too long: {len(lines)} > 600"]
    return []


def _audit_forbidden(*, text: str, relative_path: Path) -> list[str]:
    return [f"{relative_path}: forbidden pattern found: {item}" for item in FORBIDDEN_PATTERNS if item in text]


def _audit_ast(*, text: str, relative_path: Path) -> list[str]:
    try:
        tree = ast.parse(text, filename=str(relative_path))
    except SyntaxError as exc:
        return [f"{relative_path}: syntax error: {exc}"]
    return _audit_function_lengths(tree=tree, relative_path=relative_path)


def _audit_function_lengths(*, tree: ast.AST, relative_path: Path) -> list[str]:
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        length = node.end_lineno - node.lineno + 1
        if length > 80:
            errors.append(f"{relative_path}:{node.lineno} function {node.name!r} too long: {length} > 80")
    return errors


if __name__ == "__main__":
    main()
