# -*- coding: utf-8 -*-
from __future__ import annotations

"""
audit_aivideo_post_cleanup_contracts.py

Post-cleanup contract audit for the aivideo project.

This script is intentionally read-only. It scans the current working tree after
old selected-highlight visual evidence cleanup and reports remaining contract
violations before the next patch is designed.
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


ARCHIVE_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".patch_backups",
    "deprecated",
    "legacy_archive",
    "dist",
    "node_modules",
    ".venv",
    "venv",
}

ACTIVE_SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}
PY_SUFFIX = ".py"

OLD_SELECTED_HIGHLIGHT_VISUAL_TOKENS = {
    "movie_story_enable_visual_evidence",
    "movie_story_selected_highlight_max_frames",
    "selected_highlight_visual_evidence_workflow",
    "build_selected_highlight_visual_evidence_package",
    "selected_highlight_visual_evidence",
    "selected_highlight_contact_sheet",
    "movie_story_script_selected_highlight_keyframes",
    "movie_story_script_selected_highlight_visual_evidence",
}

LEGACY_NATIVE_TOKENS = {
    "run_legacy_movie_story_engine",
    "run_native_movie_story_engine",
    "movie_story_native_engine",
    "native movie_story",
    "legacy movie_story",
    "engine_backend",
}

LEGACY_NATIVE_ALLOWED_PATH_PATTERNS = {
    "app/services/movie_story/engine_policy.py",
    "app/services/movie_story/engines.py",
    "tests/movie_story/test_movie_story_old_engine_dispatch_guard.py",
    "docs/",
    "PENDING.md",
    "CLAUDE.md",
}

KEY_MOVIE_STORY_MODULES = {
    "app/services/movie_story/two_round_feature_modes.py",
    "app/services/movie_story/two_round_visual_narration.py",
    "app/services/movie_story/two_round_visual_input_packager.py",
    "app/services/movie_story/visual_focus_segments.py",
    "app/services/movie_story/visual_timeline_sampler.py",
    "app/services/movie_story/scene_segmenter.py",
    "app/services/movie_story/shot_boundary_detector.py",
    "app/services/movie_story/unified_entry.py",
}

REQUIRED_TWO_ROUND_VISUAL_TOKENS = {
    "generate_two_round_visual_narration_items",
    "build_two_round_visual_input_package",
    "visual_focus_segments",
    "call_multimodal_first_round_strict",
}

DIRECT_LLM_PATTERNS = {
    "openai.chat.completions.create",
    "litellm.completion",
    "litellm.acompletion",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    path: str
    detail: str


@dataclass
class AuditResult:
    findings: list[Finding] = field(default_factory=list)

    def add(self, *, severity: str, category: str, path: str, detail: str) -> None:
        self.findings.append(
            Finding(severity=severity, category=category, path=path, detail=detail)
        )

    def fail_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "FAIL")

    def warn_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "WARN")


def _normalize_path(path: Path) -> str:
    return path.as_posix()


def _relative_path(path: Path, *, root: Path) -> str:
    return _normalize_path(path.relative_to(root))


def _is_archived(path: Path, *, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in ARCHIVE_PARTS for part in rel_parts)


def _iter_active_files(root: Path, *, suffixes: set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_archived(path, root=root):
            continue
        if path.suffix.lower() not in suffixes:
            continue
        yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _line_numbers_for_token(text: str, token: str) -> list[int]:
    numbers: list[int] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if token in line:
            numbers.append(index)
    return numbers


def _path_allowed(path_text: str, patterns: set[str]) -> bool:
    return any(path_text == pattern or path_text.startswith(pattern) for pattern in patterns)


def audit_old_selected_highlight_visual(root: Path, result: AuditResult) -> None:
    for path in _iter_active_files(root, suffixes=ACTIVE_SCAN_SUFFIXES):
        rel = _relative_path(path, root=root)
        text = _read_text(path)
        for token in sorted(OLD_SELECTED_HIGHLIGHT_VISUAL_TOKENS):
            lines = _line_numbers_for_token(text, token)
            if not lines:
                continue
            result.add(
                severity="FAIL",
                category="old-selected-highlight-visual-residue",
                path=rel,
                detail=f"active file still contains `{token}` at lines {lines[:8]}",
            )


def audit_legacy_native_active_refs(root: Path, result: AuditResult) -> None:
    for path in _iter_active_files(root, suffixes=ACTIVE_SCAN_SUFFIXES):
        rel = _relative_path(path, root=root)
        if _path_allowed(rel, LEGACY_NATIVE_ALLOWED_PATH_PATTERNS):
            continue
        text = _read_text(path)
        for token in sorted(LEGACY_NATIVE_TOKENS):
            lines = _line_numbers_for_token(text, token)
            if not lines:
                continue
            result.add(
                severity="WARN",
                category="legacy-native-active-reference",
                path=rel,
                detail=f"review whether `{token}` is still needed at lines {lines[:8]}",
            )


def audit_key_module_headers(root: Path, result: AuditResult) -> None:
    for rel in sorted(KEY_MOVIE_STORY_MODULES):
        path = root / rel
        if not path.exists():
            result.add(
                severity="WARN",
                category="key-module-missing",
                path=rel,
                detail="expected movie_story module is missing; verify whether it was renamed intentionally",
            )
            continue
        text = _read_text(path)
        lines = text.splitlines()
        if len(lines) < 2 or lines[0].strip() != "# -*- coding: utf-8 -*-" or lines[1].strip() != "from __future__ import annotations":
            result.add(
                severity="WARN",
                category="module-header",
                path=rel,
                detail="missing standard file header in first two lines",
            )
        if "__CONTEXT__" not in text:
            result.add(
                severity="WARN",
                category="module-context",
                path=rel,
                detail="missing module-level __CONTEXT__ block",
            )


def audit_duplicate_functions_and_original_alias(root: Path, result: AuditResult) -> None:
    for path in _iter_active_files(root, suffixes={PY_SUFFIX}):
        rel = _relative_path(path, root=root)
        text = _read_text(path)
        if "_ORIGINAL_" in text:
            lines = _line_numbers_for_token(text, "_ORIGINAL_")
            result.add(
                severity="FAIL",
                category="original-alias",
                path=rel,
                detail=f"contains `_ORIGINAL_` alias pattern at lines {lines[:8]}",
            )
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            result.add(
                severity="FAIL",
                category="syntax-parse",
                path=rel,
                detail=f"cannot parse Python file: {exc}",
            )
            continue
        seen: dict[str, list[int]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.setdefault(node.name, []).append(node.lineno)
        for name, lines in sorted(seen.items()):
            if len(lines) > 1:
                result.add(
                    severity="FAIL",
                    category="duplicate-function-definition",
                    path=rel,
                    detail=f"function `{name}` defined multiple times at lines {lines}",
                )


def audit_print_logging_and_direct_llm(root: Path, result: AuditResult) -> None:
    for path in _iter_active_files(root, suffixes={PY_SUFFIX}):
        rel = _relative_path(path, root=root)
        text = _read_text(path)
        if rel.startswith("tools/") or rel.startswith("scripts/"):
            continue
        print_lines = [
            index
            for index, line in enumerate(text.splitlines(), start=1)
            if re.search(r"(^|[^\w.])print\s*\(", line)
        ]
        if print_lines:
            result.add(
                severity="WARN",
                category="print-usage",
                path=rel,
                detail=f"contains print() at lines {print_lines[:10]}",
            )
        logging_lines = [
            index
            for index, line in enumerate(text.splitlines(), start=1)
            if "import logging" in line or re.search(r"(^|[^\w.])logging\.", line)
        ]
        if logging_lines:
            result.add(
                severity="WARN",
                category="logging-module-usage",
                path=rel,
                detail=f"contains logging module usage at lines {logging_lines[:10]}",
            )
        for pattern in sorted(DIRECT_LLM_PATTERNS):
            lines = _line_numbers_for_token(text, pattern)
            if not lines:
                continue
            result.add(
                severity="WARN",
                category="direct-llm-call",
                path=rel,
                detail=f"contains direct LLM call `{pattern}` at lines {lines[:8]}; verify it uses project wrapper",
            )


def audit_two_round_visual_contract(root: Path, result: AuditResult) -> None:
    rel = "app/services/movie_story/two_round_visual_narration.py"
    path = root / rel
    if not path.exists():
        result.add(
            severity="FAIL",
            category="two-round-visual-contract",
            path=rel,
            detail="formal two_round_visual narration module is missing",
        )
        return
    text = _read_text(path)
    for token in sorted(REQUIRED_TWO_ROUND_VISUAL_TOKENS):
        if token not in text:
            result.add(
                severity="FAIL",
                category="two-round-visual-contract",
                path=rel,
                detail=f"missing required contract token `{token}`",
            )
    forbidden_local_tokens = {
        "selected_highlight_visual_evidence",
        "build_selected_highlight_visual_evidence_package",
        "movie_story_enable_visual_evidence",
    }
    for token in sorted(forbidden_local_tokens):
        lines = _line_numbers_for_token(text, token)
        if lines:
            result.add(
                severity="FAIL",
                category="two-round-visual-postprocessor-leak",
                path=rel,
                detail=f"formal visual chain still references old postprocessor token `{token}` at lines {lines[:8]}",
            )


def audit_api_focus_segment_mapping(root: Path, result: AuditResult) -> None:
    schema_rel = "app/api/schemas/jobs.py"
    feature_rel = "app/services/movie_story/two_round_feature_modes.py"
    visual_rel = "app/services/movie_story/two_round_visual_narration.py"
    schema_text = _read_text(root / schema_rel) if (root / schema_rel).exists() else ""
    feature_text = _read_text(root / feature_rel) if (root / feature_rel).exists() else ""
    visual_text = _read_text(root / visual_rel) if (root / visual_rel).exists() else ""

    schema_has_api_field = "movie_story_visual_focus_segments" in schema_text
    runtime_has_api_field = "movie_story_visual_focus_segments" in feature_text or "movie_story_visual_focus_segments" in visual_text
    runtime_has_internal_field = "visual_focus_segments" in feature_text or "visual_focus_segments" in visual_text

    if schema_has_api_field and not runtime_has_api_field:
        result.add(
            severity="WARN",
            category="visual-focus-api-field-mapping",
            path=f"{feature_rel} / {visual_rel}",
            detail="schema exposes movie_story_visual_focus_segments but runtime does not reference that exact API field; verify mapping to internal visual_focus_segments",
        )
    if not runtime_has_internal_field:
        result.add(
            severity="FAIL",
            category="visual-focus-runtime-contract",
            path=f"{feature_rel} / {visual_rel}",
            detail="runtime does not appear to use visual_focus_segments",
        )


def build_report(root: Path, result: AuditResult) -> str:
    lines: list[str] = []
    lines.append("# aivideo post-cleanup contract audit")
    lines.append("")
    lines.append(f"Project: `{root}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- FAIL: {result.fail_count()}")
    lines.append(f"- WARN: {result.warn_count()}")
    lines.append(f"- TOTAL: {len(result.findings)}")
    lines.append("")

    if not result.findings:
        lines.append("No findings. Current contracts look clean for the audited rules.")
        lines.append("")
        return "\n".join(lines)

    for severity in ("FAIL", "WARN"):
        items = [item for item in result.findings if item.severity == severity]
        if not items:
            continue
        lines.append(f"## {severity}")
        lines.append("")
        for item in items:
            lines.append(f"- **{item.category}** — `{item.path}`")
            lines.append(f"  - {item.detail}")
        lines.append("")
    return "\n".join(lines)


def run_audit(project: Path) -> AuditResult:
    root = project.resolve()
    result = AuditResult()
    audit_old_selected_highlight_visual(root, result)
    audit_legacy_native_active_refs(root, result)
    audit_key_module_headers(root, result)
    audit_duplicate_functions_and_original_alias(root, result)
    audit_print_logging_and_direct_llm(root, result)
    audit_two_round_visual_contract(root, result)
    audit_api_focus_segment_mapping(root, result)
    return result


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only audit for aivideo post-cleanup architecture contracts."
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Project root. Example: --project .",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional report path, for example reports/aivideo_post_cleanup_audit.md",
    )
    parser.add_argument(
        "--no-fail-exit",
        action="store_true",
        help="Always exit 0 even when FAIL findings exist.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    root = Path(args.project).resolve()
    if not root.exists():
        sys.stderr.write(f"Project path does not exist: {root}\n")
        return 2
    result = run_audit(root)
    report = build_report(root, result)
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report + "\n", encoding="utf-8")
        sys.stdout.write(f"audit_report: {out_path}\n")
    sys.stdout.write(report + "\n")
    if result.fail_count() and not args.no_fail_exit:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
