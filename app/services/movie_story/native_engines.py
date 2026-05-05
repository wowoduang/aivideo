"""Native movie_story engine entry points.

Stage-Q makes highlight_edit the first real native backend.  Movie-story
narration still falls back to legacy until its parity path is implemented.
"""

from __future__ import annotations

from typing import Any


class NativeEngineNotReady(RuntimeError):
    """Raised when a native backend is requested before parity is available."""


def run_native_movie_story_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise NativeEngineNotReady("native movie_story engine is not ready yet")


def run_native_highlight_edit_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from app.services.movie_story.highlight_native_engine import run_native_highlight_edit_engine as _run

    return _run(*args, **kwargs)


__all__ = [
    "NativeEngineNotReady",
    "run_native_movie_story_engine",
    "run_native_highlight_edit_engine",
]
