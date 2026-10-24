# -*- coding: utf-8 -*-
from __future__ import annotations

"""Legacy/native movie_story guard.

This module intentionally centralizes the set of forbidden movie_story entry modes.
The project must never silently resurrect old native/legacy branches under the
movie_story mainline.
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
    """Reject legacy/native movie_story modes before dispatch."""

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
