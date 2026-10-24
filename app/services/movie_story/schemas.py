# -*- coding: utf-8 -*-
from __future__ import annotations

"""Movie-story pipeline package.

``movie_story`` 是电影叙事与长视频短视频主线的统一能力层。

当前正式主线：
- movie_story: two_round / two_round_visual
- highlight: 独立产品链，不混入 movie_story 主流程
- legacy / native / subtitle_first_pipeline: 不作为主流程，也不允许作为 fallback

所有新接手代码必须遵守：
1. 先做事实理解（grounding）
2. 再做节拍设计（beat planning）
3. 最后做最终定稿（narration finalize）
"""

__CONTEXT__ = {
    "layer": "package",
    "domain": "movie_story",
    "mainline_modes": ["two_round", "two_round_visual"],
    "forbidden_modes": [
        "native",
        "legacy",
        "native_runtime",
        "legacy_understanding",
        "subtitle_first_pipeline",
        "plot_first_pipeline",
    ],
    "pipeline_contracts": [
        "EventGroundingEntry",
        "BeatWindowCandidate",
        "NarrationSentence",
        "StoryProductionPlan",
        "FactSegment",
        "NarrativeBeat",
        "NarrationItem",
    ],
}

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
FORBIDDEN_MOVIE_STORY_MODES = {
    "native",
    "legacy",
    "native_runtime",
    "legacy_understanding",
    "subtitle_first_pipeline",
    "plot_first_pipeline",
}

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
