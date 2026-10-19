# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


CURRENT_SHORT_VIDEO_DOCSTRING_PATHS = (
    "app/services/movie_story/highlight_edit_composition.py",
    "app/services/movie_story/highlight_runtime.py",
    "app/services/movie_story/composition_bridge.py",
)


def _function_docstrings(relative_path: str) -> dict[str, str | None]:
    """读取当前 active 文件中的函数 docstring。"""
    path = PROJECT_ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: ast.get_docstring(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_current_short_video_docstring_files_exist() -> None:
    """当前长视频拆短视频链路的核心文件必须存在。"""
    missing = [
        relative_path
        for relative_path in CURRENT_SHORT_VIDEO_DOCSTRING_PATHS
        if not (PROJECT_ROOT / relative_path).exists()
    ]

    assert missing == []


def test_current_short_video_modules_have_function_docstrings() -> None:
    """当前长视频拆短视频链路应保留函数职责注释。"""
    missing_docstrings: list[str] = []

    for relative_path in CURRENT_SHORT_VIDEO_DOCSTRING_PATHS:
        docstrings = _function_docstrings(relative_path)
        if not any(value for value in docstrings.values()):
            missing_docstrings.append(relative_path)

    assert missing_docstrings == []


def test_current_short_video_docstrings_describe_composition_pipeline() -> None:
    """当前注释应描述短视频合成链路职责。"""
    joined = "\n".join(
        "\n".join(value or "" for value in _function_docstrings(path).values())
        for path in CURRENT_SHORT_VIDEO_DOCSTRING_PATHS
    )

    assert "长视频拆短视频" in joined or "短视频" in joined
    assert "合成计划" in joined or "CompositionPlan" in joined
