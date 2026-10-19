# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


REMOVED_SOURCE_PATHS = {
    "app/services/movie_story/architecture_guard.py",
    "app/services/movie_story/direct_clean_v11.py",
    "app/services/movie_story/direct_cut_runtime.py",
    "app/services/movie_story/direct_runtime_v2.py",
    "app/services/movie_story/direct_runtime_v4.py",
    "app/services/movie_story/direct_runtime_v5.py",
    "app/services/movie_story/direct_runtime_v6.py",
    "app/services/movie_story/direct_runtime_v8.py",
    "app/services/movie_story/direct_runtime_v9_audit_visible.py",
    "app/services/movie_story/direct_runtime_v10_fast_visible_audit.py",
    "app/services/movie_story/direct_runtime_v11_consolidated.py",
    "app/services/movie_story/engine_status.py",
    "app/services/movie_story/engines.py",
    "app/services/movie_story/functional_boundaries.py",
    "app/services/movie_story/functional_contracts.py",
    "app/services/movie_story/highlight_native_engine.py",
    "app/services/movie_story/legacy_engines.py",
    "app/services/movie_story/legacy_segment_understanding.py",
    "app/services/movie_story/legacy_understanding_adapter.py",
    "app/services/movie_story/movie_story_native_engine.py",
    "app/services/movie_story/native_engines.py",
    "app/services/subtitle_first_pipeline.py",
    "app/services/subtitle_first_script.py",
    "tools/audit_movie_story_functional_boundaries.py",
    "tools/audit_movie_story_native_migration.py",
    "tools/audit_movie_story_runtime_usage.py",
}


REMOVED_MODULES = {
    path.removesuffix(".py").replace("/", ".")
    for path in REMOVED_SOURCE_PATHS
    if path.endswith(".py") and path.startswith(("app/", "tools/"))
}


DISALLOWED_CODE_PATH_TOKENS = (
    "architecture_guard",
    "direct_clean",
    "direct_runtime",
    "engine_status",
    "functional_boundaries",
    "functional_contracts",
    "highlight_native_engine",
    "legacy",
    "movie_story_native_engine",
    "native_engines",
    "old_chain",
    "retired",
    "retirement",
    "subtitle_first",
)


THIS_TEST = "tests/test_removed_pipeline_final_contract.py"


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def _matches_module(candidate: str, target: str) -> bool:
    return candidate == target or candidate.startswith(target + ".")


def _imports_removed_module(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for target in REMOVED_MODULES:
                    if _matches_module(alias.name, target):
                        findings.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for target in REMOVED_MODULES:
                if _matches_module(module, target):
                    findings.append(module)
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                for target in REMOVED_MODULES:
                    if _matches_module(candidate, target):
                        findings.append(candidate)

    return findings


def _iter_python_files(*, roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def _file_contains_removed_module_token(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [token for token in sorted(REMOVED_MODULES) if token in text]


def test_removed_pipeline_sources_are_absent() -> None:
    """已回收的旧链路源码、工具和脚本不应回流到项目主树。"""
    present = [
        relative
        for relative in sorted(REMOVED_SOURCE_PATHS)
        if (PROJECT_ROOT / relative).exists()
    ]

    assert present == []


def test_no_python_code_imports_removed_pipeline_modules() -> None:
    """app/tests/tools 不应 import 已回收旧链路模块。"""
    violations: list[str] = []

    for path in _iter_python_files(roots=("app", "tests", "tools")):
        relative = _normalize(path.relative_to(PROJECT_ROOT))
        if relative == THIS_TEST:
            continue

        imports = _imports_removed_module(path)
        if imports:
            violations.append(f"{relative}: {sorted(imports)}")

    assert violations == []


def test_removed_pipeline_path_tokens_do_not_reappear_in_code_tree() -> None:
    """app/tools/tests 中旧链路命名的 Python 路径只允许存在于本最终契约。"""
    violations: list[str] = []

    for path in _iter_python_files(roots=("app", "tools", "tests")):
        relative = _normalize(path.relative_to(PROJECT_ROOT))
        if relative == THIS_TEST:
            continue

        lowered = relative.lower()
        for token in DISALLOWED_CODE_PATH_TOKENS:
            if token in lowered:
                violations.append(f"{relative}: {token}")

    assert violations == []


def test_removed_pipeline_module_tokens_do_not_reappear_in_runtime_code() -> None:
    """app/tools/tests 中不应以字符串方式写回已回收模块；本最终契约除外。"""
    violations: list[str] = []

    for path in _iter_python_files(roots=("app", "tools", "tests")):
        relative = _normalize(path.relative_to(PROJECT_ROOT))
        if relative == THIS_TEST:
            continue

        tokens = _file_contains_removed_module_token(path)
        if tokens:
            violations.append(f"{relative}: {tokens}")

    assert violations == []


def test_docs_do_not_contain_removed_module_tokens() -> None:
    """docs 内容中不应再写入已回收旧链路模块 token。"""
    docs_root = PROJECT_ROOT / "docs"
    if not docs_root.exists():
        return

    violations: list[str] = []
    for path in docs_root.rglob("*"):
        if not path.is_file():
            continue

        tokens = _file_contains_removed_module_token(path)
        if tokens:
            violations.append(f"{_normalize(path.relative_to(PROJECT_ROOT))}: {tokens}")

    assert violations == []


def test_pending_does_not_contain_removed_module_tokens() -> None:
    """PENDING 只保留当前任务记录，不应继续携带已回收模块 token。"""
    pending = PROJECT_ROOT / "PENDING.md"
    if not pending.exists():
        return

    tokens = _file_contains_removed_module_token(pending)
    assert tokens == []
