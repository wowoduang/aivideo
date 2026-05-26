# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import shutil
from pathlib import Path


def test_legacy_understanding_does_not_run_native_timeline_closure(monkeypatch):
    from app.services.movie_story import timeline_runtime as rt

    base = Path(".-workspace") / "test_chain_isolation"
    if base.exists():
        shutil.rmtree(base)
    out_path = base / "scripts" / "movie_story.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = "run_test_legacy_chain_isolation"
    monkeypatch.setenv("AIVIDEO_PIPELINE_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("MOVIE_STORY_AUDIT_KEEP_STAGES", "")
    monkeypatch.setenv("AIVIDEO_MOVIE_STORY_AUDIT_KEEP_STAGES", "")

    segments = [
        {"start": 0.0, "end": 8.0, "text": "主角发现线索，危机开始出现。"},
        {"start": 10.0, "end": 18.0, "text": "对手继续施压，人物被迫做选择。"},
        {"start": 21.0, "end": 30.0, "text": "真相露出一角，冲突继续升级。"},
    ]

    chunks = rt.build_authoritative_plot_chunks(
        segments,
        output_script_path=str(out_path),
        visual_mode="off",
        target_duration_minutes=2,
        highlight_selectivity="balanced",
        narrative_strategy="chronological",
        movie_story_strategy="legacy_understanding",
    )

    assert chunks
    audit_dir = out_path.parent / "_movie_story_pipeline_audit_clips" / run_id
    stages = [
        row["stage"]
        for row in json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))
    ]

    assert "01_shot_candidates" in stages
    assert "02_scene_candidates" in stages
    assert "03_evidence_segments" not in stages
    assert "05_selected_highlights" not in stages
    assert "13_movie_story_full_closure_summary" not in stages

    marker = json.loads((audit_dir / "00_active_movie_story_runtime" / "items_full.json").read_text(encoding="utf-8"))
    assert marker[0]["movie_story_chain"] == "legacy_understanding"
