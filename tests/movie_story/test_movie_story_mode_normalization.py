# -*- coding: utf-8 -*-
from __future__ import annotations

"""
test_movie_story_mode_normalization.py

Guards that stale legacy/native labels do not silently migrate into current
movie_story mainflows.
"""

import pytest

from app.services.movie_story.unified_entry import run_movie_story_request


@pytest.mark.parametrize("old_mode", ["legacy_understanding", "native_runtime", "legacy", "native"])
def test_old_movie_story_modes_are_disabled(old_mode: str) -> None:
    with pytest.raises(RuntimeError, match="old native/legacy movie_story mainflow is disabled"):
        run_movie_story_request(
            request={"movie_story_mode": old_mode, "video_path": "demo.mp4"},
            output_script_path="E:/tmp/movie_story_script.json",
        )


def test_unknown_mode_still_reaches_dispatcher_as_error() -> None:
    with pytest.raises(ValueError, match="unsupported_movie_story_mode:unknown_mode"):
        run_movie_story_request(
            request={"movie_story_mode": "unknown_mode", "video_path": "demo.mp4"},
            output_script_path="E:/tmp/movie_story_script.json",
        )
