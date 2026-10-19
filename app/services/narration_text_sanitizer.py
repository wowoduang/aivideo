# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Final narration text sanitizer.

This module owns the last-mile contract for text delivered to frontend preview,
TTS, subtitle rendering, and video composition. It removes structural prompt
scaffolding while keeping actual narration content and paragraph boundaries.
"""

import re
from typing import Any, Mapping


__CONTEXT__ = {
    "module": "app.services.narration_text_sanitizer",
    "purpose": "Strip Markdown separators and structural labels from deliverable narration text.",
    "producers": [
        "generate_narration_script raw_srt/two_round output",
        "job result normalization",
    ],
    "consumers": [
        "frontend narration preview",
        "TTS",
        "subtitle/video composition",
    ],
    "design": "Final narration fields must contain only speakable body text, not prompt scaffolding.",
}


_MARKDOWN_SEPARATOR_RE = re.compile(r"^\s*(?:-{2,}|—{2,}|–{2,}|_{3,}|\*{3,})\s*$")

_STRUCTURE_WORD = (
    r"开场|片头|引子|主论点|主题|核心主题|核心观点|"
    r"分论点(?:[一二三四五六七八九十百千万0-9]+)?|"
    r"论点(?:[一二三四五六七八九十百千万0-9]+)?|"
    r"当下回响|回响|收尾|结尾|结语|"
    r"正式文案|最终文案|成片文案|文案正文|正文|"
    r"时间码|时间范围|片段时间|结构性事实(?:[一二三四五六七八九十百千万0-9]+)?"
)

_STRUCTURE_ONLY_RE = re.compile(
    rf"^\s*(?:[#>*\-\s]*)(?:\*\*)?(?:【|\[|（|\()?({_STRUCTURE_WORD})(?:】|\]|）|\))?(?:\*\*)?\s*[：:：\-—]*\s*$"
)

_STRUCTURE_PREFIX_RE = re.compile(
    rf"^\s*(?:[#>*\-\s]*)(?:\*\*)?(?:【|\[|（|\()?({_STRUCTURE_WORD})(?:】|\]|）|\))?(?:\*\*)?\s*[：:：\-—]+\s*"
)

_METADATA_ONLY_RE = re.compile(
    r"^\s*(?:[#>*\-\s]*)(?:时间范围|时间码|对应结构性事实编号|选择主线|选定主线|副主线|分论点序列)\s*[：:].*$"
)


def _normalize_line(line: str) -> str:
    text = str(line or "").strip()
    text = text.strip("\ufeff").strip()
    text = text.removeprefix("```").removesuffix("```").strip()
    text = text.strip("*").strip()
    return text


def _is_non_narration_line(line: str) -> bool:
    if not line:
        return True
    if _MARKDOWN_SEPARATOR_RE.match(line):
        return True
    if _STRUCTURE_ONLY_RE.match(line):
        return True
    if _METADATA_ONLY_RE.match(line):
        return True
    return False


def _append_paragraph_break(lines: list[str]) -> None:
    if lines and lines[-1] != "":
        lines.append("")


def _strip_edge_paragraph_breaks(lines: list[str]) -> list[str]:
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _collapse_paragraph_breaks(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = is_blank

    return _strip_edge_paragraph_breaks(collapsed)


def sanitize_deliverable_narration_text(text: str) -> str:
    """Return narration body text safe for frontend/TTS/subtitle delivery."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []

    for original_line in raw.split("\n"):
        line = _normalize_line(original_line)

        if not line:
            _append_paragraph_break(lines)
            continue

        if _is_non_narration_line(line):
            continue

        line = _STRUCTURE_PREFIX_RE.sub("", line, count=1).strip()
        line = line.strip("*").strip()

        if _is_non_narration_line(line):
            continue

        lines.append(line)

    return "\n".join(_collapse_paragraph_breaks(lines)).strip()


def sanitize_script_item_narration(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with narration/text fields normalized to deliverable text."""
    row = dict(item)
    narration = sanitize_deliverable_narration_text(
        str(
            row.get("narration")
            or row.get("text")
            or row.get("content")
            or ""
        )
    )
    row["narration"] = narration
    row["text"] = narration
    return row

def sanitize_deliverable_title_text(text: str, *, fallback_text: str = "") -> str:
    """Return a display-safe title without structural prompt labels."""
    cleaned = sanitize_deliverable_narration_text(str(text or ""))
    cleaned = " ".join(cleaned.split()).strip()
    if cleaned:
        return cleaned[:80]

    fallback = sanitize_deliverable_narration_text(str(fallback_text or ""))
    fallback = " ".join(fallback.split()).strip()
    return fallback[:80]
