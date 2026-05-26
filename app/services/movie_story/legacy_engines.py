"""Legacy-compatible engine calls.

This is the only module that should import the old large pipeline files.
Keeping those imports here makes future retirement explicit and searchable.
"""

from __future__ import annotations

from typing import Any


def _without_engine_keys(kwargs: dict[str, Any], *keys: str) -> dict[str, Any]:
    clean = dict(kwargs)
    for key in keys:
        clean.pop(key, None)
    return clean


def run_legacy_movie_story_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the current subtitle-first movie-story compatibility engine."""

    clean_kwargs = _without_engine_keys(
        kwargs,
        "engine_backend",
        "movie_story_engine_backend",
    )
    from app.services.subtitle_first_pipeline import run_subtitle_first_pipeline

    return run_subtitle_first_pipeline(*args, **clean_kwargs)


def run_legacy_highlight_edit_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the current highlight-edit compatibility engine."""

    clean_kwargs = _without_engine_keys(
        kwargs,
        "engine_backend",
        "edit_engine_backend",
        "highlight_engine_backend",
    )
    from app.services.highlight_edit_pipeline import run_highlight_edit_pipeline

    return run_highlight_edit_pipeline(*args, **clean_kwargs)


__all__ = [
    "run_legacy_movie_story_engine",
    "run_legacy_highlight_edit_engine",
]
