"""Native movie_story engine entry points.

Final migration promotes both highlight_edit and movie_story to native backend entry points. Legacy engines remain available as fallback adapters.
"""

from __future__ import annotations

from typing import Any


class NativeEngineNotReady(RuntimeError):
    """Raised when a native backend is requested before parity is available."""


def run_native_movie_story_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from app.services.movie_story.movie_story_native_engine import run_movie_story_native_engine as _run

    return _run(*args, **kwargs)


def run_native_highlight_edit_engine(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from app.services.movie_story.highlight_native_engine import run_native_highlight_edit_engine as _run

    return _run(*args, **kwargs)


__all__ = [
    "NativeEngineNotReady",
    "run_native_movie_story_engine",
    "run_native_highlight_edit_engine",
]
