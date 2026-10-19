import os
from pathlib import Path

from app.services.movie_story import timeline_runtime as rt
from app.services.movie_story.story_runtime import _store_plot_map, extract_highlights
from tools.verify_movie_story_migration_stage import verify_stage_a


def test_stage_a_runtime_writes_04_and_06_even_with_old_keep_config(tmp_path, monkeypatch):
    out = tmp_path / "script.json"
    video = tmp_path / "video.mp4"
    rt._LAST_OUTPUT_PATH = str(out)
    rt._LAST_VIDEO_PATH = str(video)
    monkeypatch.setenv("AIVIDEO_AUDIT_RUN_ID", "run_stage_a_runtime")
    monkeypatch.setenv("AIVIDEO_PIPELINE_AUDIT_RUN_ID", "run_stage_a_runtime")
    # Simulate an old user config/env that only kept pre-migration stages.
    monkeypatch.setenv("MOVIE_STORY_AUDIT_KEEP_STAGES", "00c_boundary_summary,01_shot_candidates,02_scene_candidates,03_story_candidates,05_selected_highlights")

    scenes = [
        {"scene_id": "s1", "start": 0, "end": 5, "subtitle_text": "皇上，再过两个月可臣妾的生日了，银库早已空虚。"},
        {"scene_id": "s2", "start": 5, "end": 12, "subtitle_text": "朕现在就任命你为钦差大臣，赴各地催征税银。皇上，可如今遍地饥民。"},
        {"scene_id": "s3", "start": 12, "end": 18, "subtitle_text": "灾民不是抗税，是实在活不下去了。"},
    ]
    _store_plot_map(scenes)
    highlights = extract_highlights(scenes, highlight_selectivity="loose")
    assert highlights

    run_dir = tmp_path / "_movie_story_pipeline_audit_clips" / "run_stage_a_runtime"
    assert (run_dir / "story_audit" / "04_story_audit_global_context" / "manifest.json").exists()
    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "manifest.json").exists()
    assert (run_dir / "story_audit" / "06_story_audit_scene_evidence_for_narration" / "items_full.json").exists()

    report = verify_stage_a(audit_dir=run_dir)
    assert report["overall_passed"] is True
