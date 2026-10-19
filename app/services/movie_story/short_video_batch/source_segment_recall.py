# -*- coding: utf-8 -*-
from __future__ import annotations

"""
source_segment_recall.py

Deterministic candidate recall for long-video to multiple short videos.

Input rows are neutral source segments. In the current MVP, those rows may come
from existing movie_story highlight artifacts, manually selected time ranges, or
future scene/event detectors. The public function name intentionally uses the neutral source_segments concept.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.source_segment_recall",
    "entry_points": [
        "recall_short_video_candidates_from_source_segments",
    ],
    "called_by": [
        "batch_pipeline.py",
    ],
    "decisions": [
        "2026-05: Use neutral source_segments as input; existing movie_story highlight artifacts are only one possible producer.",
        "2026-05: MVP is deterministic and does not call LLM.",
    ],
    "pending": [
        "Add scene/subtitle density candidate recall after source-segment MVP is stable.",
        "Add visual evidence score when shared visual timeline is ready.",
    ],
    "ai_constraints": [
        "Do not infer final short-video scripts in this module.",
        "Do not call LLM here; this module is deterministic candidate recall.",
    ],
}

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.movie_story.short_video_batch.contracts import ShortVideoCandidate
from app.services.narration_text_sanitizer import (
    sanitize_deliverable_narration_text,
    sanitize_deliverable_title_text,
)


_TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}(?:[,.]\d{1,3})?|\d+(?:\.\d+)?)\s*[-~—]\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}(?:[,.]\d{1,3})?|\d+(?:\.\d+)?)"
)


def _to_float(value: Any) -> float | None:
    """Convert numeric-like values to float seconds."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("s"):
        text = text[:-1]

    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _parse_clock_time(value: str) -> float | None:
    """Parse HH:MM:SS.mmm or plain seconds into seconds."""
    numeric = _to_float(value)
    if numeric is not None:
        return numeric

    parts = value.replace(",", ".").split(":")
    if len(parts) != 3:
        return None

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return None

    return hours * 3600 + minutes * 60 + seconds


def _extract_time_range(row: Mapping[str, Any]) -> tuple[float, float] | None:
    """Extract a source time range from known source-segment schemas."""
    direct_pairs = (
        ("video_start", "video_end"),
        ("start_sec", "end_sec"),
        ("start", "end"),
        ("start_time", "end_time"),
    )

    for start_key, end_key in direct_pairs:
        start = _to_float(row.get(start_key))
        end = _to_float(row.get(end_key))
        if start is not None and end is not None and end > start:
            return start, end

    timestamp = str(row.get("timestamp") or "").strip()
    match = _TIMESTAMP_RE.search(timestamp)
    if not match:
        return None

    start = _parse_clock_time(match.group("start"))
    end = _parse_clock_time(match.group("end"))
    if start is None or end is None or end <= start:
        return None

    return start, end


def _candidate_score(row: Mapping[str, Any]) -> float:
    """Extract a normalized candidate score."""
    raw_score = row.get("candidate_score", row.get("highlight_score", row.get("score")))
    if raw_score is None and isinstance(row.get("scores"), Mapping):
        scores = row["scores"]
        raw_score = (
            scores.get("candidate_score")
            or scores.get("highlight_score")
            or scores.get("story_score")
            or scores.get("emotion_score")
            or scores.get("visual_score")
            or 0.0
        )

    score = _to_float(raw_score)
    if score is None:
        return 0.0

    if score > 1:
        score = score / 100.0

    return max(0.0, min(1.0, score))


def _first_non_empty(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    """Return first non-empty string value."""
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _candidate_id(*, index: int, start_sec: float, end_sec: float, title: str) -> str:
    """Build stable candidate id from source time and title."""
    digest = hashlib.md5(f"{index}:{start_sec:.3f}:{end_sec:.3f}:{title}".encode("utf-8")).hexdigest()
    return f"svc_{digest[:10]}"


def _selection_reasons(row: Mapping[str, Any], summary: str) -> list[str]:
    """Normalize selection reasons."""
    raw_reasons = row.get("selection_reasons") or row.get("reasons") or []
    if isinstance(raw_reasons, str):
        reasons = [raw_reasons.strip()] if raw_reasons.strip() else []
    elif isinstance(raw_reasons, Sequence):
        reasons = [str(item).strip() for item in raw_reasons if str(item).strip()]
    else:
        reasons = []

    if not reasons and summary:
        reasons.append(summary[:80])

    return reasons[:5]


def recall_short_video_candidates_from_source_segments(
    source_segments: Sequence[Mapping[str, Any]],
    *,
    max_candidates: int = 12,
    min_duration_sec: float = 8.0,
    max_duration_sec: float = 240.0,
) -> list[ShortVideoCandidate]:
    """
    Recall standalone short-video candidates from source segments.

    This function is deterministic. It only normalizes and ranks candidate events;
    it does not generate scripts and does not call LLM.
    """
    candidates: list[ShortVideoCandidate] = []

    for index, row in enumerate(source_segments, start=1):
        time_range = _extract_time_range(row)
        if time_range is None:
            continue

        start_sec, end_sec = time_range
        duration = end_sec - start_sec
        if duration < min_duration_sec or duration > max_duration_sec:
            continue

        summary = sanitize_deliverable_narration_text(
            _first_non_empty(row, ("summary", "reason", "theme_or_emo_line", "text", "content"))
        )
        raw_title = _first_non_empty(row, ("title", "section_title", "topic"))
        title = sanitize_deliverable_title_text(raw_title, fallback_text=summary)
        if not title:
            title = f"短视频候选 {index}"

        source_type = str(row.get("source_type") or row.get("source") or "source_segment")
        candidate = ShortVideoCandidate(
            candidate_id=_candidate_id(index=index, start_sec=start_sec, end_sec=end_sec, title=title),
            title=title,
            summary=summary,
            start_sec=start_sec,
            end_sec=end_sec,
            score=_candidate_score(row),
            source_type=source_type,
            selection_reasons=_selection_reasons(row, summary),
            evidence={
                "raw_index": index,
                "raw_id": row.get("id") or row.get("segment_id") or row.get("highlight_id"),
                "timestamp": row.get("timestamp"),
                "producer": source_type,
            },
        )
        candidates.append(candidate)

    return sorted(candidates, key=lambda item: (-item.score, item.start_sec))[:max_candidates]
