from app.services.movie_story.narration_evidence import _build_highlight_narration_segments
from app.services.movie_story.narration_finalize import finalize_narration_script


def test_build_highlight_narration_segments_keeps_rich_metadata():
    highlights = [
        {
            "highlight_id": "h1",
            "start": 10.0,
            "end": 16.0,
            "highlight_type": "information_reveal",
            "highlight_score": 0.8,
            "segment_ids": ["s1"],
            "scene_ids": ["s1"],
        }
    ]
    scene_evidence = [
        {
            "segment_id": "s1",
            "scene_id": "s1",
            "start": 10.0,
            "end": 16.0,
            "subtitle_text": "他终于发现账本是假的。",
            "plot_function": "信息揭露",
            "local_understanding": {"core_event": "发现账本造假", "emotion": "震惊", "characters": ["主角"]},
            "story_validation": {"validator_status": "pass", "validator_hints": []},
            "visual_summary": [{"frame": "f.jpg", "desc": "主角翻开账本"}],
        }
    ]
    rows = _build_highlight_narration_segments(highlights, scene_evidence, [], {"main_storyline": "查账"})

    assert len(rows) == 1
    assert rows[0]["subtitle_text"]
    assert rows[0]["local_understanding"]["core_event"] == "发现账本造假"
    assert rows[0]["story_validation"]["validator_status"] == "pass"
    assert rows[0]["_global_summary"]["main_storyline"] == "查账"


def test_finalize_narration_script_adds_validation_and_preserves_evidence_window():
    evidence = [
        {
            "highlight_id": "h1",
            "scene_id": "h1",
            "segment_id": "h1",
            "start": 10.0,
            "end": 16.0,
            "semantic_start": 10.0,
            "semantic_end": 16.0,
            "subtitle_text": "他终于发现账本是假的。",
            "real_narrative_state": "主角发现账本造假，冲突升级。",
        }
    ]
    script = [{"_id": 1, "scene_id": "h1", "start": 10.0, "end": 16.0, "narration": "主角终于意识到账本被人动过手脚。"}]

    final_items, report = finalize_narration_script(script, narration_evidence=evidence, story_highlights=evidence)

    assert report["stage"] == "07c_final_narration_validation"
    assert report["final_script_items"] == 1
    assert final_items[0]["movie_story_validation"]["status"] in {"pass", "review"}
    assert final_items[0]["semantic_start"] == 10.0
    assert final_items[0]["semantic_end"] == 16.0
