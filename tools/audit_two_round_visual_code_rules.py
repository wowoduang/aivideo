# -*- coding: utf-8 -*-
from __future__ import annotations

"""Audit source-level code rules for the official two_round_visual chain.

This tool is a guardrail for the first-round visual enhancement modules only.
It intentionally does not enforce the old hard "80 lines per function" rule;
current project policy is functional modularity, clear responsibility, and no
large mixed-purpose modules. The audit therefore focuses on source-level issues
that are objectively unsafe for this chain: missing headers/context, print or
logging-module usage, `_ORIGINAL_*` alias patching, and incomplete function type
annotations.
"""

__CONTEXT__ = {
    "layer": "tooling",
    "domain": "movie_story.two_round_visual.audit",
    "entry_points": ["main", "audit_targets"],
    "called_by": ["developer CLI", "optional preflight checks"],
    "decisions": [
        "2026-05: audit targets only the official first-round two_round_visual modules.",
        "2026-05: removed the obsolete hard 80-line function rule; readability is judged by functional modularity.",
        "2026-05: switched forbidden checks from raw substring matching to AST checks to avoid self/tool false positives.",
    ],
    "pending": [
        "If more visual modules become official first-round chain modules, add them to TARGETS explicitly.",
    ],
    "ai_constraints": [
        "Do not add prompt content checks here; prompts are intentionally stable unless the user explicitly asks to change them.",
        "Do not use this tool to require compatibility wrappers or legacy/native mainflow restoration.",
    ],
}

import ast
import sys
from pathlib import Path
from typing import Iterable, Sequence

TARGETS = (
    Path("app/services/movie_story/shot_boundary_detector.py"),
    Path("app/services/movie_story/scene_segmenter.py"),
    Path("app/services/movie_story/visual_focus_segments.py"),
    Path("app/services/movie_story/visual_timeline_sampler.py"),
    Path("app/services/movie_story/two_round_visual_input_packager.py"),
    Path("app/services/movie_story/two_round_visual_narration.py"),
)

MAX_MODULE_LINES = 600
_ALLOWED_UNANNOTATED_ARGS = {"self", "cls"}


def main() -> None:
    """Run the audit from the repository root and exit non-zero on violations."""
    root = Path(".").resolve()
    errors = audit_targets(root=root)
    if errors:
        raise SystemExit("\n".join(errors))
    sys.stdout.write("two_round_visual code-rule audit passed\n")


def audit_targets(*, root: Path, targets: Sequence[Path] | None = None) -> list[str]:
    """Audit the configured official two_round_visual files."""
    selected_targets = targets or TARGETS
    errors: list[str] = []
    for relative_path in selected_targets:
        errors.extend(_audit_file(root / relative_path, relative_path=relative_path))
    return errors


def _audit_file(path: Path, *, relative_path: Path) -> list[str]:
    if not path.exists():
        return [f"missing file: {relative_path}"]

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors: list[str] = []
    errors.extend(_audit_header(lines=lines, relative_path=relative_path))
    errors.extend(_audit_context(text=text, relative_path=relative_path))
    errors.extend(_audit_module_size(lines=lines, relative_path=relative_path))
    errors.extend(_audit_ast(text=text, relative_path=relative_path))
    return errors


def _audit_header(*, lines: list[str], relative_path: Path) -> list[str]:
    errors: list[str] = []
    if len(lines) < 1 or lines[0] != "# -*- coding: utf-8 -*-":
        errors.append(f"{relative_path}: missing utf-8 header")
    if len(lines) < 2 or lines[1] != "from __future__ import annotations":
        errors.append(f"{relative_path}: missing future annotations header")
    return errors


def _audit_context(*, text: str, relative_path: Path) -> list[str]:
    if "__CONTEXT__" not in text:
        return [f"{relative_path}: missing module-level __CONTEXT__ block"]
    return []


def _audit_module_size(*, lines: list[str], relative_path: Path) -> list[str]:
    if len(lines) > MAX_MODULE_LINES:
        return [f"{relative_path}: module too large for focused two_round_visual file: {len(lines)} > {MAX_MODULE_LINES}"]
    return []


def _audit_ast(*, text: str, relative_path: Path) -> list[str]:
    try:
        tree = ast.parse(text, filename=str(relative_path))
    except SyntaxError as exc:
        return [f"{relative_path}: syntax error: {exc}"]

    errors: list[str] = []
    errors.extend(_audit_forbidden_ast(tree=tree, relative_path=relative_path))
    errors.extend(_audit_function_annotations(tree=tree, relative_path=relative_path))
    return errors


def _audit_forbidden_ast(*, tree: ast.AST, relative_path: Path) -> list[str]:
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            errors.append(f"{relative_path}:{node.lineno}: print() is forbidden; use loguru logger")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging" or alias.name.startswith("logging."):
                    errors.append(f"{relative_path}:{node.lineno}: logging module import is forbidden; use loguru logger")
        if isinstance(node, ast.ImportFrom) and (node.module == "logging" or str(node.module).startswith("logging.")):
            errors.append(f"{relative_path}:{node.lineno}: logging module import is forbidden; use loguru logger")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "logging":
            errors.append(f"{relative_path}:{node.lineno}: logging module usage is forbidden; use loguru logger")
        if _is_original_alias_assignment(node):
            errors.append(f"{relative_path}:{node.lineno}: _ORIGINAL_* alias patching is forbidden; refactor directly")
    return errors


def _is_original_alias_assignment(node: ast.AST) -> bool:
    targets: Iterable[ast.AST]
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = (node.target,)
    else:
        return False

    for target in targets:
        if isinstance(target, ast.Name) and target.id.startswith("_ORIGINAL_"):
            return True
    return False


def _audit_function_annotations(*, tree: ast.AST, relative_path: Path) -> list[str]:
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is None:
            errors.append(f"{relative_path}:{node.lineno}: function {node.name!r} missing return type annotation")
        for arg in _iter_function_args(node.args):
            if arg.arg in _ALLOWED_UNANNOTATED_ARGS:
                continue
            if arg.annotation is None:
                errors.append(f"{relative_path}:{node.lineno}: function {node.name!r} argument {arg.arg!r} missing type annotation")
    return errors


def _iter_function_args(args: ast.arguments) -> Iterable[ast.arg]:
    yield from args.posonlyargs
    yield from args.args
    yield from args.kwonlyargs
    if args.vararg is not None:
        yield args.vararg
    if args.kwarg is not None:
        yield args.kwarg


if __name__ == "__main__":
    main()
