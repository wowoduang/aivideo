# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Audit code-rule basics for two_round_visual files.
"""

import ast
from pathlib import Path


TARGETS = [
    Path("app/services/movie_story/shot_boundary_detector.py"),
    Path("app/services/movie_story/scene_segmenter.py"),
    Path("app/services/movie_story/visual_focus_segments.py"),
    Path("app/services/movie_story/visual_timeline_sampler.py"),
    Path("app/services/movie_story/two_round_visual_input_packager.py"),
    Path("app/services/movie_story/two_round_visual_narration.py"),
]

FORBIDDEN = (
    "print(",
    "import logging",
    "logging.",
    "_ORIGINAL_",
)


def main() -> None:
    root = Path(".").resolve()
    errors: list[str] = []

    for relative_path in TARGETS:
        path = root / relative_path
        if not path.exists():
            errors.append(f"missing file: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        if len(lines) > 600:
            errors.append(f"{relative_path}: file too long: {len(lines)} > 600")

        if len(lines) < 2 or lines[0] != "# -*- coding: utf-8 -*-":
            errors.append(f"{relative_path}: missing utf-8 header")
        if len(lines) < 2 or lines[1] != "from __future__ import annotations":
            errors.append(f"{relative_path}: missing future annotations header")

        for forbidden in FORBIDDEN:
            if forbidden in text:
                errors.append(f"{relative_path}: forbidden pattern found: {forbidden}")

        try:
            tree = ast.parse(text, filename=str(relative_path))
        except SyntaxError as exc:
            errors.append(f"{relative_path}: syntax error: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.end_lineno is None:
                    continue
                length = node.end_lineno - node.lineno + 1
                if length > 80:
                    errors.append(
                        f"{relative_path}:{node.lineno} function {node.name!r} too long: {length} > 80"
                    )

    if errors:
        raise SystemExit("
".join(errors))

    print("two_round_visual code-rule audit passed")


if __name__ == "__main__":
    main()
