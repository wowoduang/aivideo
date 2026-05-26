# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.movie_story.shot_boundary_detector import detect_shot_boundaries


@pytest.mark.parametrize("missing_path", ["/tmp/not_found.mp4", "Z:/missing.mp4"])
def test_detect_shot_boundaries_missing_video_raises(missing_path: str) -> None:
    with pytest.raises(FileNotFoundError):
        detect_shot_boundaries(video_path=Path(missing_path))
