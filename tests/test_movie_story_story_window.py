from __future__ import annotations

from app.services.movie_story.story_window import _apply_llm_highlight_plan


def test_apply_llm_highlight_plan_accepts_srt_timecode_windows():
    scene_evidence = [
        {
            "segment_id": "seg_001",
            "scene_id": "scene_001",
            "start": "00:08:40,000",
            "end": "00:08:44,000",
            "subtitle_text": "key scene",
        }
    ]
    llm_highlight_plan = {
        "must_keep_ranges": [
            {
                "start": "00:08:41,018",
                "end": "00:08:42,500",
                "reason": "srt_window",
                "raw_voice_priority": "high",
            }
        ]
    }

    annotated = _apply_llm_highlight_plan(scene_evidence, {}, llm_highlight_plan)

    assert annotated[0]["llm_highlight_selected"] is True
    assert annotated[0]["llm_highlight_reason"] == "highlight_window"
    assert annotated[0]["llm_raw_voice_keep"] is True
    assert annotated[0]["llm_window_reasons"] == ["srt_window"]


def test_apply_llm_highlight_plan_accepts_timestamp_only_scene_ranges():
    scene_evidence = [
        {
            "segment_id": "seg_001",
            "scene_id": "scene_001",
            "timestamp": "00:08:41,018-00:09:09,196",
            "subtitle_text": "key scene",
        }
    ]
    llm_highlight_plan = {
        "must_keep_ranges": [
            {
                "start": "00:08:50,000",
                "end": "00:08:55,000",
                "reason": "timestamp_range_scene",
            }
        ]
    }

    annotated = _apply_llm_highlight_plan(scene_evidence, {}, llm_highlight_plan)

    assert annotated[0]["llm_highlight_selected"] is True
    assert annotated[0]["llm_highlight_reason"] == "highlight_window"
    assert annotated[0]["llm_window_reasons"] == ["timestamp_range_scene"]
