from app.services.movie_story import highlight_edit_composition as composition


def test_build_composition_plan_splits_grouped_narration_into_subshots():
    clip = {
        "clip_id": "scene_clip_001",
        "source": "scene",
        "start": 10.0,
        "end": 18.0,
        "duration": 8.0,
        "scene_summary": "主角和反派对峙",
        "subtitle_text": "主角和反派对峙",
        "raw_audio_worthy": True,
        "tags": ["scene_refined"],
        "selection_reason": ["scene_anchor"],
        "boundary_candidates": [12.5, 15.0],
    }
    match = {
        "text": "主角终于摊牌。反派开始动摇。局势彻底反转。",
        "clip_group": [clip],
        "story_stage": "climax",
        "match_strategy": "semantic",
        "rhythm_profile": "fast",
        "rhythm_config": {"preferred_group_size": 3, "min_shot_seconds": 1.0, "max_shot_seconds": 2.5},
        "target_seconds": 6.0,
    }

    plan = composition.build_composition_plan(
        mode="narrated_highlight_edit",
        video_path="/tmp/demo.mp4",
        movie_title="Demo",
        target_duration_seconds=60,
        visual_mode="auto",
        highlight_profile={"id": "general"},
        highlight_capabilities={},
        candidate_stats={},
        selected_clips=[clip],
        narration_text=match["text"],
        narration_audio_path="/tmp/narration.wav",
        prefer_raw_audio=True,
        narration_matches=[match],
    )

    assert plan["mode"] == "narrated_highlight_edit"
    assert len(plan["segments"]) >= 2
    assert plan["metadata"]["grouped_match_mode"] is True
    assert all(seg["timeline_end"] > seg["timeline_start"] for seg in plan["segments"])
    assert any("intra_scene_cut" in seg["selection_reason"] for seg in plan["segments"])


def test_decide_group_audio_plan_prefers_raw_for_climax_keyline():
    result = composition.decide_group_audio_plan(
        match={"story_stage": "climax", "target_seconds": 2.5},
        clip={"raw_audio_worthy": True},
        group_idx=1,
        group_size=2,
        prefer_raw_audio=True,
        has_narration=True,
    )

    assert result["audio_mode"] == "ducked_raw"
    assert result["carry_narration"] is True
