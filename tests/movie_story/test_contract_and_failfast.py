# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.movie_story.narration_contract import validate_stage_result
from app.services.movie_story.unified_entry import _require_movie_story_inputs, _resolve_movie_story_mode


def test_validate_fact_segment_payload():
    payload = {
        "facts": [
            {
                "segment_id": "f1",
                "title": "进入会议",
                "summary": "人物进入会议室",
                "time_range": "00:00:10-00:00:25",
            }
        ]
    }
    validate_stage_result("fact_segment", payload)


def test_validate_narrative_beat_payload():
    payload = {
        "beats": [
            {
                "beat_id": "b1",
                "phase": "hook",
                "hook": "这件事的关键是什么？",
                "content": "人物之间发生冲突",
                "time_range": "00:00:10-00:00:25",
            }
        ]
    }
    validate_stage_result("narrative_beat", payload)


def test_validate_narration_item_payload():
    payload = {
        "script_items": [
            {
                "item_id": "i1",
                "script_text": "这里是最终解说文案。",
                "time_range": "00:00:10-00:00:25",
            }
        ]
    }
    validate_stage_result("narration_item", payload)


def test_resolve_mode_rejects_legacy():
    request = {"movie_story_mode": "legacy"}
    assert _resolve_movie_story_mode(request) == "legacy"


def test_requires_video_path_for_movie_story():
    request = {"movie_story_mode": "two_round"}
    try:
        _require_movie_story_inputs(request)
        assert False, "should raise"
    except ValueError as exc:
        assert "movie_story_request_missing_video_path" in str(exc)


def test_requires_visual_focus_for_two_round_visual():
    request = {"movie_story_mode": "two_round_visual", "video_path": "/tmp/video.mp4"}
    try:
        _require_movie_story_inputs(request)
        assert False, "should raise"
    except ValueError as exc:
        assert "movie_story_request_missing_visual_focus_segments" in str(exc)


def test_accepts_visual_focus_for_two_round_visual():
    request = {
        "movie_story_mode": "two_round_visual",
        "video_path": "/tmp/video.mp4",
        "visual_focus_segments": [{"start": 10.0, "end": 20.0}],
    }
    _require_movie_story_inputs(request)


__all__ = [
    "test_validate_fact_segment_payload",
    "test_validate_narrative_beat_payload",
    "test_validate_narration_item_payload",
    "test_resolve_mode_rejects_legacy",
    "test_requires_video_path_for_movie_story",
    "test_requires_visual_focus_for_two_round_visual",
    "test_accepts_visual_focus_for_two_round_visual",
]
