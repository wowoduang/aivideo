# -*- coding: utf-8 -*-
from __future__ import annotations

"""Guard movie_story dispatch from old Native/Legacy mainflow."""

from pathlib import Path


def test_movie_story_engine_dispatch_has_old_mainflow_guard() -> None:
    source = Path("app/services/movie_story/engines.py").read_text(encoding="utf-8")

    assert "old Native/Legacy movie_story mainflow is disabled" in source
    assert "selected_highlight_visual_evidence_workflow" not in source
    assert "multi_short_video_pipeline" in source
