# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for pipeline audit stage index metadata."""

import json
from pathlib import Path


def test_pipeline_stage_index_uses_namespace(tmp_path: Path, monkeypatch) -> None:
    """pipeline _stage_index.json must match pipeline/<stage> directories."""
    from app.services.movie_story import audit_runtime as ar

    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_test_pipeline_stage_index")

    output_script = tmp_path / "job-001" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    ar._audit_video_snapshot(
        "04_global_story_context",
        [
            {
                "candidate_id": "ctx",
                "start": 0.0,
                "end": 0.001,
                "subtitle_text": "测试",
            }
        ],
        {
            "output_script_path": str(output_script),
            "movie_story_strategy": "native_runtime",
            "video_path": "",
        },
    )

    run_dir = output_script.parent / "_movie_story_pipeline_audit_clips" / "run_test_pipeline_stage_index"
    index = json.loads((run_dir / "_stage_index.json").read_text(encoding="utf-8"))
    entry = index[-1]

    assert entry["stage"] == "pipeline/04_pipeline_global_story_context"
    assert entry["source_stage"] == "04_global_story_context"
    assert entry["producer"] == "pipeline"
    assert Path(entry["dir"]) == run_dir / "pipeline" / "04_pipeline_global_story_context"
