# -*- coding: utf-8 -*-
from __future__ import annotations

"""
batch_planner.py

Deterministic MVP planner that turns recalled candidates into short-video plans.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.batch_planner",
    "entry_points": [
        "build_short_video_plans",
    ],
    "called_by": [
        "batch_pipeline.py",
    ],
    "decisions": [
        "2026-05: MVP creates one short-video plan per strong candidate to validate artifact contracts before adding an LLM planner.",
        "2026-05: Each plan stores one theme/emotion line only, not full narration.",
    ],
    "pending": [
        "Add optional LLM one-line theme/emo writer after API contracts are stable.",
    ],
    "ai_constraints": [
        "Do not run full two_round_visual once per short video.",
        "Do not generate a full short-video script in this module.",
        "Do not treat visual_focus_segments as final source_segments.",
    ],
}

from collections.abc import Sequence

from app.services.movie_story.short_video_batch.contracts import (
    ShortVideoCandidate,
    ShortVideoPlan,
    ShortVideoSegment,
)
from app.services.narration_text_sanitizer import sanitize_deliverable_narration_text


def _overlap_ratio(left: ShortVideoCandidate, right: ShortVideoCandidate) -> float:
    """Return overlap ratio relative to the shorter candidate."""
    overlap_start = max(left.start_sec, right.start_sec)
    overlap_end = min(left.end_sec, right.end_sec)
    overlap = max(0.0, overlap_end - overlap_start)
    shorter = max(0.001, min(left.duration_sec, right.duration_sec))
    return overlap / shorter


def _make_theme_or_emo_line(candidate: ShortVideoCandidate) -> tuple[str, str]:
    """
    Build one card-display line for the short.

    This is intentionally not a narration script. It is a one-sentence topic or
    emotion line used to help users decide whether this short is worth producing.
    """
    cleaned_summary = sanitize_deliverable_narration_text(candidate.summary)
    if cleaned_summary:
        return cleaned_summary[:90], "emo"

    return f"这条短视频的核心看点是：{candidate.title}", "theme"


def build_short_video_plans(
    candidates: Sequence[ShortVideoCandidate],
    *,
    max_shorts: int = 6,
    target_duration_sec: float = 90.0,
    max_overlap_ratio: float = 0.65,
) -> list[ShortVideoPlan]:
    """
    Build independent short-video plans from recalled candidates.

    The output is a planning artifact only. It intentionally contains no full
    narration field; later stages can expand selected plans into scripts.
    """
    selected: list[ShortVideoCandidate] = []
    plans: list[ShortVideoPlan] = []

    for candidate in candidates:
        if len(selected) >= max_shorts:
            break

        if any(_overlap_ratio(candidate, existing) >= max_overlap_ratio for existing in selected):
            continue

        selected.append(candidate)
        short_index = len(selected)
        theme_or_emo_line, line_type = _make_theme_or_emo_line(candidate)
        plan = ShortVideoPlan(
            short_id=f"short_{short_index:03d}",
            title=candidate.title,
            theme_or_emo_line=theme_or_emo_line,
            line_type=line_type,
            target_duration_sec=target_duration_sec,
            source_segments=[
                ShortVideoSegment(
                    start_sec=candidate.start_sec,
                    end_sec=candidate.end_sec,
                    source_type=candidate.source_type,
                )
            ],
            source_candidate_ids=[candidate.candidate_id],
        )
        plans.append(plan)

    return plans
