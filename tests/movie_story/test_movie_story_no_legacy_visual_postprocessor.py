# -*- coding: utf-8 -*-
from __future__ import annotations

"""Guards against reconnecting the old selected-highlight visual post-processor."""

from pathlib import Path


def test_local_job_runner_does_not_trigger_legacy_visual_evidence_postprocessor() -> None:
    source = Path("app/services/local_job_runner.py").read_text(encoding="utf-8")

    assert "movie_story_enable_visual_evidence" not in source
    assert "selected_highlight_visual_evidence_workflow" not in source
    assert "build_selected_highlight_visual_evidence_package" not in source


def test_frontend_and_schema_do_not_expose_legacy_visual_evidence_switch() -> None:
    checked_paths = [
        Path("app/api/schemas/jobs.py"),
        Path("web/src/lib/api.ts"),
        Path("web/src/pages/editor/Analysis.tsx"),
        Path("web/src/pages/editor/Material.tsx"),
    ]

    for path in checked_paths:
        source = path.read_text(encoding="utf-8")
        assert "movie_story_enable_visual_evidence" not in source
        assert "movie_story_selected_highlight_max_frames" not in source
