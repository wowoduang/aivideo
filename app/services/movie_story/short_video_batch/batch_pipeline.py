# -*- coding: utf-8 -*-
from __future__ import annotations

"""
batch_pipeline.py

MVP entry for long-video to multiple short-video planning.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.batch_pipeline",
    "entry_points": [
        "build_short_video_batch_from_source_segments",
    ],
    "called_by": [
        "future API route",
        "future background task worker",
    ],
    "decisions": [
        "2026-05: Start with neutral source_segments input and deterministic planning before adding UI/API integration.",
        "2026-05: Current output is title + one theme/emotion line; no full script generation.",
    ],
    "pending": [
        "Load source_segments from existing movie_story highlight artifacts in a separate adapter.",
        "Add API route and frontend /projects/:id/shorts page.",
        "Add optional one-line LLM theme writer after deterministic MVP.",
    ],
    "ai_constraints": [
        "Do not add legacy/native fallback.",
        "Do not call LLM in this MVP pipeline.",
        "Do not generate full narration scripts in this stage.",
        "Raise ValueError when no candidates are available.",
    ],
}

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.movie_story.short_video_batch.artifact_writer import (
    write_short_video_batch_artifacts,
)
from app.services.movie_story.short_video_batch.batch_planner import (
    build_short_video_plans,
)
from app.services.movie_story.short_video_batch.source_segment_recall import (
    recall_short_video_candidates_from_source_segments,
)


def build_short_video_batch_from_source_segments(
    source_segments: Sequence[Mapping[str, Any]],
    *,
    output_dir: str | Path,
    max_candidates: int = 12,
    max_shorts: int = 6,
    target_duration_sec: float = 90.0,
) -> dict[str, Any]:
    """
    Build MVP short-video candidates/plans from source segments.

    Source segments are neutral input rows produced by existing movie_story
    highlight artifacts, manual time selections, or future scene/event detectors.
    """
    candidates = recall_short_video_candidates_from_source_segments(
        source_segments,
        max_candidates=max_candidates,
    )
    if not candidates:
        raise ValueError("未能从 source_segments 中召回可用短视频候选")

    plans = build_short_video_plans(
        candidates,
        max_shorts=max_shorts,
        target_duration_sec=target_duration_sec,
    )
    if not plans:
        raise ValueError("短视频候选存在，但未能生成 short video plans")

    artifacts = write_short_video_batch_artifacts(
        output_dir,
        candidates=candidates,
        plans=plans,
    )

    return {
        "candidates": [candidate.to_dict() for candidate in candidates],
        "plans": [plan.to_dict() for plan in plans],
        "artifacts": artifacts,
    }
