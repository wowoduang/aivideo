# -*- coding: utf-8 -*-
from __future__ import annotations

"""Guard movie_story mainflow from accidentally selecting old Native Runtime."""

from app.services.movie_story.engine_policy import (
    BACKEND_AUTO,
    BACKEND_NATIVE,
    ENGINE_KIND_MOVIE_STORY,
    decide_engine_backend,
    native_ready_for,
)


def test_movie_story_auto_does_not_select_old_native_runtime() -> None:
    decision = decide_engine_backend(
        engine_kind=ENGINE_KIND_MOVIE_STORY,
        requested_backend=BACKEND_AUTO,
        compatibility_engine="subtitle_first_pipeline",
    )

    assert native_ready_for(ENGINE_KIND_MOVIE_STORY) is False
    assert decision.selected_backend != BACKEND_NATIVE
    assert decision.reason != "auto_selected_native"
