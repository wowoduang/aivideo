from app.services.composition_plan_adapter import composition_plan_to_script_items
from app.services.movie_story.composition_bridge import (
    build_movie_story_composition_plan,
    validate_composition_plan,
)


def test_build_movie_story_composition_plan_preserves_semantic_windows_and_audio_modes():
    script_items = [
        {
            "_id": 1,
            "scene_id": "h1",
            "highlight_id": "h1",
            "start": 10.0,
            "end": 16.0,
            "narration": "主角终于意识到账本被人动过手脚。",
            "OST": 2,
            "llm_raw_voice_keep": True,
            "semantic_start": 10.5,
            "semantic_end": 15.5,
            "movie_story_validation": {"status": "pass"},
        }
    ]
    evidence = [
        {
            "highlight_id": "h1",
            "scene_id": "h1",
            "start": 10.0,
            "end": 16.0,
            "subtitle_text": "他终于发现账本是假的。",
            "plot_function": "信息揭露",
            "raw_voice": True,
            "visual_summary": [{"desc": "主角翻开账本"}],
        }
    ]
    highlights = [{"highlight_id": "h1", "start": 10.0, "end": 16.0, "highlight_type": "information_reveal"}]

    plan = build_movie_story_composition_plan(
        video_path="/tmp/demo.mp4",
        movie_title="Demo",
        target_duration_seconds=120,
        script_items=script_items,
        narration_evidence=evidence,
        story_highlights=highlights,
        generation_mode="balanced",
        visual_mode="auto",
    )

    assert plan["mode"] == "movie_story"
    assert plan["metadata"]["composition_bridge_stage"] == "stage_m"
    assert len(plan["segments"]) == 1
    segment = plan["segments"][0]
    assert segment["audio_mode"] == "ducked_raw"
    assert segment["source_clip_id"] == "h1"
    assert segment["semantic_start"] == 10.5
    assert segment["semantic_end"] == 15.5
    assert segment["movie_story_validation"]["status"] == "pass"
    assert "type:information_reveal" in segment["selection_reason"]

    report = validate_composition_plan(plan)
    assert report["passed"] is True
    assert report["segment_count"] == 1


def test_movie_story_composition_plan_round_trips_to_legacy_script_items():
    plan = build_movie_story_composition_plan(
        video_path="/tmp/demo.mp4",
        script_items=[
            {
                "scene_id": "h2",
                "start": 1.0,
                "end": 3.0,
                "narration": "",
                "OST": 1,
                "picture": "保留原声对白",
                "semantic_start": 1.0,
                "semantic_end": 3.0,
            }
        ],
        narration_evidence=[{"scene_id": "h2", "start": 1.0, "end": 3.0, "raw_voice": True}],
        story_highlights=[{"highlight_id": "h2", "start": 1.0, "end": 3.0, "highlight_type": "key_line"}],
    )

    items = composition_plan_to_script_items(plan)

    assert len(items) == 1
    assert items[0]["OST"] == 1
    assert items[0]["highlight_id"] == "h2"
    assert items[0]["semantic_start"] == 1.0
    assert items[0]["story_highlight_type"] == "key_line"
