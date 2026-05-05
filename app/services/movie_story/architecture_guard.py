"""Architecture guardrails for the movie_story native migration.

The native migration keeps legacy pipelines available, but direct imports of
those retired pipelines must remain isolated in one module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

LEGACY_PIPELINE_PATTERNS = (
    "app.services.subtitle_first_pipeline",
    "app.services.highlight_edit_pipeline",
)

DEFAULT_ALLOWED_RELATIVE_PATHS = {
    Path("app/services/movie_story/legacy_engines.py"),
    Path("services/movie_story/legacy_engines.py"),
}

_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(app\.services\.(?:subtitle_first_pipeline|highlight_edit_pipeline))\b",
    re.MULTILINE,
)


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def find_direct_legacy_imports(
    root: str | Path,
    *,
    allowed_relative_paths: Sequence[str | Path] | None = None,
) -> Dict[str, object]:
    """Scan Python files for direct imports of retired pipeline modules."""

    root_path = Path(root).resolve()
    allowed = {Path(p).as_posix() for p in (allowed_relative_paths or DEFAULT_ALLOWED_RELATIVE_PATHS)}
    violations: List[Dict[str, object]] = []
    allowed_hits: List[Dict[str, object]] = []

    for path in _iter_python_files(root_path):
        rel_path = path.relative_to(root_path).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        for match in _IMPORT_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hit = {
                "path": rel_path,
                "line": line_no,
                "module": match.group(1),
                "statement": match.group(0).strip(),
            }
            if rel_path in allowed:
                allowed_hits.append(hit)
            else:
                violations.append(hit)

    return {
        "success": not violations,
        "violations": violations,
        "allowed_hits": allowed_hits,
        "allowed_relative_paths": sorted(allowed),
        "patterns": list(LEGACY_PIPELINE_PATTERNS),
    }


def assert_no_direct_legacy_imports(root: str | Path) -> None:
    """Raise AssertionError if code imports retired pipeline modules directly."""

    report = find_direct_legacy_imports(root)
    if report["violations"]:
        raise AssertionError(f"direct legacy pipeline imports found: {report['violations']}")


__all__ = [
    "DEFAULT_ALLOWED_RELATIVE_PATHS",
    "LEGACY_PIPELINE_PATTERNS",
    "assert_no_direct_legacy_imports",
    "find_direct_legacy_imports",
]
