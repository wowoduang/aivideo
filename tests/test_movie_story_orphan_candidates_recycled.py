# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


RECYCLED_ORPHAN_PATHS = {
    "app/services/movie_story/commentary_pipeline.py",
    "app/services/movie_story/engine_failover.py",
    "app/services/movie_story/quality_gate.py",
    "app/services/movie_story/scene_alignment.py",
}


RECYCLED_ORPHAN_MODULES = {
    path.removesuffix(".py").replace("/", ".")
    for path in RECYCLED_ORPHAN_PATHS
}


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def _matches_module(candidate: str, target: str) -> bool:
    return candidate == target or candidate.startswith(target + ".")


def _imports_recycled_orphan(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for target in RECYCLED_ORPHAN_MODULES:
                    if _matches_module(alias.name, target):
                        findings.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for target in RECYCLED_ORPHAN_MODULES:
                if _matches_module(module, target):
                    findings.append(module)
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                for target in RECYCLED_ORPHAN_MODULES:
                    if _matches_module(candidate, target):
                        findings.append(candidate)

    return findings


def test_orphan_candidate_sources_are_absent() -> None:
    """静态无引用的 orphan candidate 模块已移出 app 主源码树。"""
    present = [
        relative
        for relative in sorted(RECYCLED_ORPHAN_PATHS)
        if (PROJECT_ROOT / relative).exists()
    ]

    assert present == []


def test_no_code_imports_recycled_orphan_candidates() -> None:
    """app/tests/tools 不应再 import 已回收 orphan candidate。"""
    violations: list[str] = []

    for root_name in ("app", "tests", "tools"):
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            relative = _normalize(path.relative_to(PROJECT_ROOT))
            if relative == "tests/test_movie_story_orphan_candidates_recycled.py":
                continue

            imports = _imports_recycled_orphan(path)
            if imports:
                violations.append(f"{relative}: {sorted(imports)}")

    assert violations == []
