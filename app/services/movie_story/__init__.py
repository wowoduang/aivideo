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
    "run_movie_story_engine",
    "run_highlight_edit_engine",
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
    if name in {"run_movie_story_engine", "run_highlight_edit_engine"}:
        from .engines import run_highlight_edit_engine, run_movie_story_engine

        if name == "run_movie_story_engine":
            return run_movie_story_engine
        return run_highlight_edit_engine
    raise AttributeError(name)
