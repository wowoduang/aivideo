# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path


def _stage_dir(audit_dir, stage_name):
    rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))
    for row in rows:
        if row.get("source_stage") == stage_name or str(row.get("stage", "")).endswith("/" + stage_name):
            return Path(row["dir"])
    raise AssertionError(f"stage not found: {stage_name}")


def test_timeline_runtime_writes_success_judgement_video_export_stages(tmp_path, monkeypatch):
    from app.services.movie_story import timeline_runtime as rt

    out_path = tmp_path / "scripts" / "movie_story.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = "run_test_diagnostic_video_export_stages"
    monkeypatch.setenv("AIVIDEO_PIPELINE_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("MOVIE_STORY_AUDIT_KEEP_STAGES", "")
    monkeypatch.setenv("AIVIDEO_MOVIE_STORY_AUDIT_KEEP_STAGES", "")
    monkeypatch.setenv("MOVIE_STORY_DIAGNOSTIC_VIDEO_EXPORT", "1")

    segments = [
        {"start": 0.0, "end": 8.0, "text": "男主发现真相，他决定继续调查。"},
        {"start": 10.0, "end": 20.0, "text": "女主开始怀疑身边的人，秘密逐渐曝光。"},
        {"start": 22.0, "end": 32.0, "text": "反派安排计划，冲突突然升级。"},
        {"start": 35.0, "end": 46.0, "text": "他终于做出关键决定，所有人都陷入危险。"},
        {"start": 48.0, "end": 60.0, "text": "众人开始反击，真正的危机还没有结束。"},
    ]

    rt.build_authoritative_plot_chunks(
        segments,
        output_script_path=str(out_path),
        visual_mode="off",
        target_duration_minutes=2,
        highlight_selectivity="very_loose",
        narrative_strategy="mixed",
    )

    audit_dir = out_path.parent / "_movie_story_pipeline_audit_clips" / run_id
    stage_rows = json.loads((audit_dir / "_stage_index.json").read_text(encoding="utf-8"))
    stages = [row.get("source_stage") or str(row.get("stage", "")).split("/")[-1] for row in stage_rows]
    expected = [
        "01a_shot_boundary_video_samples",
        "03a_evidence_video_samples",
        "04b_highlight_pre_selection_video_pool",
        "05a_selected_highlight_videos",
        "05b_selection_coverage_gate",
        "06b_rejected_near_miss_videos",
        "10a_script_review_videos",
    ]
    missing = [name for name in expected if name not in stages]
    assert not missing, f"missing diagnostic video stages: {missing}; got={stages}"

    coverage = json.loads((_stage_dir(audit_dir, "05b_selection_coverage_gate") / "items_full.json").read_text(encoding="utf-8"))[0]["payload"]
    assert "coverage_ratio" in coverage
    assert coverage["policy"] == "selection_should_be_long_enough_for_requested_target_minutes"
