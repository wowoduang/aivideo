# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for movie_story audit producer namespaces."""

import json
from pathlib import Path


def test_runtime_audit_stage_writes_runtime_namespace(tmp_path: Path) -> None:
    """timeline_runtime.audit_stage writes low-level diagnostics under runtime/."""
    from app.services.movie_story import timeline_runtime as rt

    output_script = tmp_path / "job-001" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    stage_dir = rt.audit_stage(
        "05_selected_highlights",
        [{"candidate_id": "h1", "start": 0, "end": 1, "subtitle_text": "测试"}],
        video_path="",
        output_path=str(output_script),
        export_clips=False,
    )

    assert "/runtime/05_runtime_selected_highlight_candidates" in str(stage_dir).replace("\\", "/")
    index = json.loads((stage_dir.parents[1] / "_stage_index.json").read_text(encoding="utf-8"))
    assert index[-1]["stage"] == "runtime/05_runtime_selected_highlight_candidates"
    assert index[-1]["source_stage"] == "05_selected_highlights"
    assert index[-1]["producer"] == "runtime"


def test_pipeline_audit_snapshot_writes_pipeline_namespace(tmp_path: Path) -> None:
    """audit_runtime._audit_video_snapshot writes native-engine snapshots under pipeline/."""
    from app.services.movie_story import audit_runtime as ar

    output_script = tmp_path / "job-002" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    ar._audit_video_snapshot(
        "05_selected_highlights",
        [{"candidate_id": "h1", "start": 0, "end": 1, "subtitle_text": "测试"}],
        {
            "output_script_path": str(output_script),
            "movie_story_strategy": "native_runtime",
            "video_path": "",
        },
    )

    root = output_script.parent / "_movie_story_pipeline_audit_clips"
    runs = sorted(root.glob("run_*"))
    assert runs
    assert (runs[-1] / "pipeline" / "05_final_highlights" / "items_full.json").exists()


def test_audit_root_does_not_fallback_to_video_parent() -> None:
    """audit_runtime must not write to frontend_uploads/video from video_path only."""
    from app.services.movie_story import audit_runtime as ar

    try:
        ar._audit_root_v41({"video_path": "E:/aivideo-workspace/frontend_uploads/video/demo.mp4"})
    except RuntimeError as exc:
        assert "requires output_script_path/output_path/audit_root" in str(exc)
    else:
        raise AssertionError("_audit_root_v41 should reject video_path-only input")
