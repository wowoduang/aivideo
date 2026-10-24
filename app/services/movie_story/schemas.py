# -*- coding: utf-8 -*-
from __future__ import annotations

"""Movie-story pipeline package.

``movie_story`` is the mainline capability layer for narrative-minded video jobs.
It is intentionally limited to the current mainline modes:
- two_round
- two_round_visual

Legacy/native/plot-first variants are not valid entry points and are rejected at
runtime rather than silently downgraded.
"""

from app.services.movie_story.legacy_entry_guard import LEGACY_MOVIE_STORY_MODES
from app.services.movie_story.schemas import (
    BeatWindowCandidate,
    DraftStoryCandidate,
    EvidenceSegment,
    EventGroundingEntry,
    FactSegment,
    NarrativeBeat,
    NarrationItem,
    NarrationSentence,
    SceneCandidate,
    SelectedHighlight,
    StoryProductionPlan,
    SubtitleUnit,
)

MAINLINE_MOVIE_STORY_MODES = {"two_round", "two_round_visual"}
FORBIDDEN_MOVIE_STORY_MODES = set(LEGACY_MOVIE_STORY_MODES)

__all__ = [
    "run_first_three_stages",
    "run_unified_edit_request",
    "movie_story_scene_overrides_from_request",
    "get_engine_status",
    "MAINLINE_MOVIE_STORY_MODES",
    "FORBIDDEN_MOVIE_STORY_MODES",
    "SubtitleUnit",
    "SceneCandidate",
    "DraftStoryCandidate",
    "EvidenceSegment",
    "SelectedHighlight",
    "EventGroundingEntry",
    "BeatWindowCandidate",
    "NarrationSentence",
    "StoryProductionPlan",
    "FactSegment",
    "NarrativeBeat",
    "NarrationItem",
]


def __getattr__(name: str):
    if name == "run_first_three_stages":
        from .pipeline import run_first_three_stages
        return run_first_three_stages
    if name in {"run_unified_edit_request", "movie_story_scene_overrides_from_request"}:
        from .unified_entry import movie_story_scene_overrides_from_request, run_unified_edit_request
        if name == "run_unified_edit_request":
            return run_unified_edit_request
        return movie_story_scene_overrides_from_request
    if name == "get_engine_status":
        from .engine_status import get_engine_status
        return get_engine_status
    raise AttributeError(name)
