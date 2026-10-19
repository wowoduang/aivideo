# -*- coding: utf-8 -*-
from __future__ import annotations

"""
contracts.py

Typed contracts for the short-video batch chain.
"""

__CONTEXT__ = {
    "layer": "service",
    "domain": "movie_story.short_video_batch.contracts",
    "entry_points": [
        "ShortVideoCandidate",
        "ShortVideoPlan",
        "ShortVideoSegment",
    ],
    "called_by": [
        "source_segment_recall.py",
        "batch_planner.py",
        "artifact_writer.py",
        "batch_pipeline.py",
    ],
    "decisions": [
        "2026-05: Use dedicated short_video_* contracts instead of reusing highlight as the final business object.",
        "2026-05: Current MVP stores only title + theme_or_emo_line; full script fields are intentionally absent.",
    ],
    "pending": [
        "Add ShortVideoScript and ShortVideoExport only when script writing and rendering are connected.",
    ],
    "ai_constraints": [
        "Keep these contracts small and serializable.",
        "Do not add narration/script fields to ShortVideoPlan in the current MVP.",
        "Do not mix raw prompt/response debug data into final short-video contracts.",
    ],
}

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ShortVideoSegment:
    """Source video time range selected for one short-video plan."""

    start_sec: float
    end_sec: float
    source_type: str = "source_segment"

    @property
    def duration_sec(self) -> float:
        """Return segment duration in seconds."""
        return max(0.0, self.end_sec - self.start_sec)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation."""
        data = asdict(self)
        data["duration_sec"] = self.duration_sec
        return data


@dataclass(frozen=True)
class ShortVideoCandidate:
    """Candidate source event that may become a standalone short video."""

    candidate_id: str
    title: str
    summary: str
    start_sec: float
    end_sec: float
    score: float
    source_type: str
    selection_reasons: list[str]
    evidence: dict[str, Any]

    @property
    def duration_sec(self) -> float:
        """Return candidate duration in seconds."""
        return max(0.0, self.end_sec - self.start_sec)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation."""
        data = asdict(self)
        data["duration_sec"] = self.duration_sec
        return data


@dataclass(frozen=True)
class ShortVideoPlan:
    """
    Independent plan for one short video.

    Current MVP deliberately stores a single theme/emotion line rather than a
    full narration script. This supports a Douyin/TikTok-like card workflow:
    users first pick which short ideas are worth producing, then later stages
    can expand selected plans into scripts and rendered videos.
    """

    short_id: str
    title: str
    theme_or_emo_line: str
    line_type: str
    target_duration_sec: float
    source_segments: list[ShortVideoSegment]
    source_candidate_ids: list[str]
    status: str = "planned"

    @property
    def source_duration_sec(self) -> float:
        """Return total source clip duration."""
        return sum(segment.duration_sec for segment in self.source_segments)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation."""
        data = asdict(self)
        data["source_segments"] = [segment.to_dict() for segment in self.source_segments]
        data["source_duration_sec"] = self.source_duration_sec
        return data
