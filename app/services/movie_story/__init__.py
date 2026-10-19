# -*- coding: utf-8 -*-
"""Movie-story pipeline package.

``movie_story`` is the shared capability layer for movie-story narration and
highlight recut flows. Keep package imports lightweight: heavy runtime modules
are imported lazily by explicit submodule paths or through ``__getattr__``.
"""

__all__ = [
    "run_first_three_stages",
    "run_unified_edit_request",
    "movie_story_scene_overrides_from_request",
    "get_engine_status",
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
