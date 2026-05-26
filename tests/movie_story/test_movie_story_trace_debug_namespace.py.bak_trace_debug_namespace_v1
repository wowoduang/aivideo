# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for separating movie_story trace/debug audit stages from pipeline outputs."""

import json
from pathlib import Path


def test_trace_stage_goes_to_debug_trace_namespace(tmp_path: Path, monkeypatch) -> None:
    """LLM before/after snapshots are TRACE / DEBUG, not formal pipeline outputs."""
    from app.services.movie_story import audit_runtime as ar

    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_test_trace_debug_namespace")

    output_script = tmp_path / "job-001" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    ar._audit_video_snapshot(
        "04a_llm_highlight_plan_before",
        [
            {
                "candidate_id": "trace_marker",
                "start": 0.0,
                "end": 0.001,
                "subtitle_text": "trace only",
            }
        ],
        {
            "output_script_path": str(output_script),
            "movie_story_strategy": "native_runtime",
            "video_path": "",
        },
    )

    run_dir = output_script.parent / "_movie_story_pipeline_audit_clips" / "run_test_trace_debug_namespace"
    stage_dir = run_dir / "debug" / "trace" / "04a_llm_highlight_plan_before"
    assert stage_dir.exists()
    assert (stage_dir / "items_full.json").exists()
    assert not (run_dir / "pipeline" / "04a_llm_highlight_plan_before").exists()

    index = json.loads((run_dir / "_stage_index.json").read_text(encoding="utf-8"))
    entry = index[-1]
    assert entry["stage"] == "debug/trace/04a_llm_highlight_plan_before"
    assert entry["source_stage"] == "04a_llm_highlight_plan_before"
    assert entry["producer"] == "debug/trace"
    assert Path(entry["dir"]) == stage_dir


def test_formal_pipeline_stage_stays_in_pipeline_namespace(tmp_path: Path, monkeypatch) -> None:
    """Formal business snapshots remain under pipeline/."""
    from app.services.movie_story import audit_runtime as ar

    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_test_formal_pipeline_namespace")

    output_script = tmp_path / "job-002" / "movie_story_script.json"
    output_script.parent.mkdir(parents=True, exist_ok=True)

    ar._audit_video_snapshot(
        "05_selected_highlights",
        [
            {
                "candidate_id": "highlight_001",
                "start": 1.0,
                "end": 10.0,
                "subtitle_text": "formal highlight",
            }
        ],
        {
            "output_script_path": str(output_script),
            "movie_story_strategy": "native_runtime",
            "video_path": "",
        },
    )

    run_dir = output_script.parent / "_movie_story_pipeline_audit_clips" / "run_test_formal_pipeline_namespace"
    stage_dir = run_dir / "pipeline" / "05_final_highlights"
    assert stage_dir.exists()

    index = json.loads((run_dir / "_stage_index.json").read_text(encoding="utf-8"))
    entry = index[-1]
    assert entry["stage"] == "pipeline/05_final_highlights"
    assert entry["source_stage"] == "05_selected_highlights"
    assert entry["producer"] == "pipeline"
    assert Path(entry["dir"]) == stage_dir
