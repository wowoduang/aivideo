# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for timeline_runtime audit root resolution."""

from pathlib import Path


def test_timeline_audit_base_prefers_output_path_even_when_video_exists(tmp_path: Path) -> None:
    """Explicit output_path is the only valid source of runtime audit root."""
    from app.services.movie_story import timeline_runtime as rt

    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    output_script = tmp_path / "tasks" / "job-001" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    root = rt.audit_base(str(video_path), str(output_script))

    assert root == output_script.parent / "_movie_story_pipeline_audit_clips"


def test_timeline_audit_base_rejects_video_path_only(tmp_path: Path) -> None:
    """video_path.parent must not be used as an audit output root."""
    from app.services.movie_story import timeline_runtime as rt

    video_path = tmp_path / "frontend_uploads" / "video" / "input.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake")

    try:
        rt.audit_base(str(video_path), "")
    except RuntimeError as exc:
        assert "requires output_script_path/output_path" in str(exc)
    else:
        raise AssertionError("audit_base should reject video_path-only input")
