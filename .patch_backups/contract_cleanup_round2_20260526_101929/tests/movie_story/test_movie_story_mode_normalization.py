# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_movie_story_mode_normalization.py

Guards stale project/frontend movie_story strategy migration after legacy/native
mainflows were removed from the active dispatch path.
"""

from app.services.movie_story.unified_entry import _normalize_movie_story_mode


def test_legacy_understanding_migrates_to_two_round() -> None:
    assert _normalize_movie_story_mode("legacy_understanding") == "two_round"


def test_native_runtime_migrates_to_two_round() -> None:
    assert _normalize_movie_story_mode("native_runtime") == "two_round"


def test_two_round_visual_is_not_downgraded() -> None:
    assert _normalize_movie_story_mode("two_round_visual") == "two_round_visual"


def test_unknown_mode_still_reaches_dispatcher_as_error() -> None:
    assert _normalize_movie_story_mode("unknown_mode") == "unknown_mode"
