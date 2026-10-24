# -*- coding: utf-8 -*-
from __future__ import annotations

"""Legacy/native movie_story guard.

This file is intentionally the single whitelist/denylist boundary for old movie_story
modes. The current official runtime must refuse legacy/native flow instead of
reintroducing it via fallback logic.
"""

LEGACY_MOVIE_STORY_MODES = {
    "native",
    "legacy",
    "native_runtime",
    "legacy_understanding",
    "subtitle_first_pipeline",
    "plot_first_pipeline",
}


def assert_mainline_movie_story_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if not normalized:
        return "two_round"
    if normalized in LEGACY_MOVIE_STORY_MODES:
        raise RuntimeError(
            "movie_story mainline mode is forbidden: "
            f"{normalized}. use two_round or two_round_visual only; "
            "legacy/native fallback is disabled."
        )
    return normalized

__all__ = ["LEGACY_MOVIE_STORY_MODES", "assert_mainline_movie_story_mode"]
