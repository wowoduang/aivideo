# -*- coding: utf-8 -*-
from __future__ import annotations

"""
short_video_batch

Independent chain for Douyin/TikTok-like "one long video produces multiple
short videos".

Current MVP does not write full narration scripts. Each planned short video
only carries a display title and one theme/emotion line. Full script writing,
composition, TTS, and rendering will be added as later stages.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch",
    "entry_points": [
        "build_short_video_batch_from_source_segments",
    ],
    "called_by": [
        "future api route for /projects/{id}/shorts",
        "future batch export worker",
    ],
    "decisions": [
        "2026-05: Create an independent short_video_batch package instead of adding more code to two_round_feature_modes.py.",
        "2026-05: MVP only outputs title + one theme/emotion line, not full narration scripts.",
        "2026-05: Use source_segments as the neutral input concept; use neutral source_segments naming.",
    ],
    "pending": [
        "Connect API route after MVP artifacts pass local contract tests.",
        "Add optional one-line LLM theme writer after deterministic planning is stable.",
        "Add script/composition/render stages after product UI confirms the short-card workflow.",
    ],
    "ai_constraints": [
        "Do not place this chain inside the single-video two_round writer.",
        "Do not generate full narration scripts in the current MVP.",
        "Do not use visual_focus_segments as final clip selections.",
        "Do not add fallback to legacy/native pipelines.",
    ],
}

from app.services.movie_story.short_video_batch.batch_pipeline import (
    build_short_video_batch_from_source_segments,
)
from app.services.movie_story.short_video_batch.contracts import (
    ShortVideoCandidate,
    ShortVideoPlan,
    ShortVideoSegment,
)

__all__ = [
    "ShortVideoCandidate",
    "ShortVideoPlan",
    "ShortVideoSegment",
    "build_short_video_batch_from_source_segments",
]
