# -*- coding: utf-8 -*-
from __future__ import annotations

import json


def test_timeline_runtime_writes_full_post_02_closure_stages(tmp_path, monkeypatch):
    from app.services.movie_story import timeline_runtime as rt

    out_path = tmp_path / "scripts" / "movie_story.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = "run_test_full_movie_story_closure"
    monkeypatch.setenv("AIVIDEO_PIPELINE_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", run_id)
    monkeypatch.setenv("MOVIE_STORY_AUDIT_KEEP_STAGES", "")
    monkeypatch.setenv("AIVIDEO_MOVIE_STORY_AUDIT_KEEP_STAGES", "")

    segments = [
        {"start": 0.0, "end": 9.0, "text": "男主发现真相，他决定继续调查。"},
        {"start": 12.0, "end": 22.0, "text": "女主开始怀疑身边的人，秘密逐渐曝光。"},
        {"start": 25.0, "end": 34.0, "text": "反派安排计划，冲突突然升级。"},
        {"start": 38.0, "end": 48.0, "text": "他终于做出关键决定，所有人都陷入危险。"},
    ]

    chunks = rt.build_authoritative_plot_chunks(
        segments,
        output_script_path=str(out_path),
        visual_mode="off",
        target_duration_minutes=2,
        highlight_selectivity="very_loose",
        narrative_strategy="mixed",
    )

    assert chunks
    audit_dir = out_path.parent / "_movie_story_pipeline_audit_clips" / run_id
    index_path = audit_dir / "_stage_index.json"
    assert index_path.exists()
    stages = [row["stage"] for row in json.loads(index_path.read_text(encoding="utf-8"))]

    expected = [
        "01_shot_candidates",
        "02_scene_candidates",
        "03_evidence_segments",
        "04_split_merge_suggestions",
        "05_selected_highlights",
        "06_rejected_candidates",
        "06_scene_evidence_for_narration",
        "07_human_narration_director",
        "08_opening_hooks",
        "09_transition_sentences",
        "10_humanized_script_items",
        "11_subtitle_design_cues",
        "12_production_quality_gate",
        "13_movie_story_full_closure_summary",
    ]
    missing = [name for name in expected if name not in stages]
    assert not missing, f"missing closure stages: {missing}; got={stages}"

    evidence = json.loads((audit_dir / "03_evidence_segments" / "items_full.json").read_text(encoding="utf-8"))
    selected = json.loads((audit_dir / "05_selected_highlights" / "items_full.json").read_text(encoding="utf-8"))
    script_items = json.loads((audit_dir / "10_humanized_script_items" / "items_full.json").read_text(encoding="utf-8"))
    quality_gate = json.loads((audit_dir / "12_production_quality_gate" / "items_full.json").read_text(encoding="utf-8"))

    assert len(evidence) >= len(chunks)
    assert selected
    assert script_items
    assert quality_gate and quality_gate[0]["payload"]["passed"] is True
    for item in selected:
        assert item["video_end"] > item["video_start"]
        assert item.get("time_policy") == "video_start_video_end_authoritative_no_tts_retime"
