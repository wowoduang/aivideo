# -*- coding: utf-8 -*-
from __future__ import annotations

"""
source_segment_adapter.py

Adapter from existing movie_story artifact JSON into short_video_batch
source_segments.

This module is the bridge from current movie_story outputs to the new
Douyin/TikTok-like multiple-short-video planning chain. It does not generate
full narration scripts. It only extracts neutral source segment rows that can
be ranked and converted into short video cards.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.source_segment_adapter",
    "entry_points": [
        "load_source_segments_from_movie_story_artifact",
        "build_short_video_batch_from_movie_story_artifact",
    ],
    "called_by": [
        "tools/build_short_video_batch_from_movie_story_artifact.py",
        "future API route for /projects/{id}/shorts",
    ],
    "decisions": [
        "2026-05: Use explicit artifact file input instead of scanning task directories implicitly.",
        "2026-05: Convert existing movie_story artifacts to neutral source_segments before short-video planning.",
        "2026-05: Keep the first stage theme-only; do not write full narration scripts.",
    ],
    "pending": [
        "Add API route after the manual tool validates real task artifacts.",
        "Add frontend short-card page after source_segments artifacts are stable.",
    ],
    "ai_constraints": [
        "Do not call LLM in this adapter.",
        "Do not silently scan alternative artifact files when the explicit file is invalid.",
        "Do not add legacy/native fallback.",
    ],
}

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.movie_story.short_video_batch.batch_pipeline import (
    build_short_video_batch_from_source_segments,
)
from app.services.narration_text_sanitizer import (
    sanitize_deliverable_narration_text,
    sanitize_deliverable_title_text,
)


SUPPORTED_ITEM_KEYS = (
    "items",
    "segments",
    "highlights",
    "script_segments",
    "narration_segments",
)


def _first_non_empty(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    """Return first non-empty string value from known artifact keys."""
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _one_line(text: str, *, max_chars: int = 90) -> str:
    """Convert artifact text into one card-display line."""
    cleaned = sanitize_deliverable_narration_text(text)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned[:max_chars]


def _extract_items(payload: Any) -> list[Mapping[str, Any]]:
    """Extract item rows from supported movie_story artifact schemas."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in SUPPORTED_ITEM_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        if items is None:
            raise ValueError(
                "不支持的 movie_story artifact 结构：未找到 items/segments/highlights/script_segments/narration_segments"
            )
    else:
        raise ValueError("不支持的 movie_story artifact 结构：根节点必须是 list 或 dict")

    invalid = [index for index, item in enumerate(items, start=1) if not isinstance(item, Mapping)]
    if invalid:
        raise ValueError(f"movie_story artifact 中存在非对象条目: {invalid[:5]}")

    return list(items)


def _normalize_source_segment(row: Mapping[str, Any], *, index: int, source_type: str) -> dict[str, Any]:
    """
    Normalize one movie_story artifact row into a source_segment row.

    The output remains a candidate source segment, not a final short video.
    """
    raw_summary = _first_non_empty(
        row,
        (
            "theme_or_emo_line",
            "summary",
            "reason",
            "narration",
            "text",
            "source_text",
            "content",
        ),
    )
    summary = _one_line(raw_summary)

    raw_title = _first_non_empty(row, ("title", "section_title", "topic"))
    title = sanitize_deliverable_title_text(raw_title, fallback_text=summary)
    if not title:
        title = f"短视频候选 {index}"

    normalized: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "source_type": source_type,
        "selection_reasons": row.get("selection_reasons") or row.get("reasons") or [],
        "id": row.get("id") or row.get("segment_id") or row.get("highlight_id") or f"source_{index:03d}",
    }

    for key in (
        "video_start",
        "video_end",
        "start_sec",
        "end_sec",
        "start",
        "end",
        "start_time",
        "end_time",
        "timestamp",
        "candidate_score",
        "highlight_score",
        "score",
        "scores",
    ):
        if key in row:
            normalized[key] = row[key]

    return normalized


def load_source_segments_from_movie_story_artifact(
    artifact_path: str | Path,
    *,
    source_type: str = "movie_story_highlight",
) -> list[dict[str, Any]]:
    """
    Load source_segments from one explicit movie_story artifact file.

    The caller must pass the exact artifact file to use. This keeps the chain
    deterministic and avoids guessing across multiple task files.
    """
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(f"movie_story artifact 不存在: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError(f"movie_story artifact 必须是 JSON 文件: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    items = _extract_items(payload)
    source_segments = [
        _normalize_source_segment(item, index=index, source_type=source_type)
        for index, item in enumerate(items, start=1)
    ]

    if not source_segments:
        raise ValueError(f"movie_story artifact 中没有可用条目: {path}")

    return source_segments


def build_short_video_batch_from_movie_story_artifact(
    artifact_path: str | Path,
    *,
    output_dir: str | Path,
    source_type: str = "movie_story_highlight",
    max_candidates: int = 12,
    max_shorts: int = 6,
    target_duration_sec: float = 90.0,
) -> dict[str, Any]:
    """
    Build theme-only short-video candidates/plans from one movie_story artifact.

    This function writes short_video_candidates.json and short_video_plans.json.
    It does not create narration scripts or rendered videos.
    """
    source_segments = load_source_segments_from_movie_story_artifact(
        artifact_path,
        source_type=source_type,
    )
    return build_short_video_batch_from_source_segments(
        source_segments,
        output_dir=output_dir,
        max_candidates=max_candidates,
        max_shorts=max_shorts,
        target_duration_sec=target_duration_sec,
    )
