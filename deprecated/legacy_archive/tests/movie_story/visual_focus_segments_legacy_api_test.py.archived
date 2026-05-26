# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.visual_focus_segments import (
    build_scene_segments_from_raw_srt,
    build_visual_focus_segments,
    parse_srt_units,
)


SRT_TEXT = """1
00:00:01,000 --> 00:00:03,000
你为什么回来？

2
00:00:08,000 --> 00:00:12,000
我不是来找你的。

3
00:00:20,000 --> 00:00:24,000
他刚刚在门口说什么？

4
00:01:05,000 --> 00:01:10,000
你看清楚是谁动手了吗？
"""


def test_parse_srt_units_standard_input() -> None:
    units = parse_srt_units(SRT_TEXT)

    assert len(units) == 4
    assert units[0]["start"] == 1.0
    assert "为什么" in units[0]["text"]


def test_build_visual_focus_segments_from_manual_request() -> None:
    segments = build_visual_focus_segments(
        SRT_TEXT,
        {"movie_story_visual_focus_segments": [{"start": 10.0, "end": 45.0, "reason": "用户补选人物关系误判处"}]},
    )

    assert segments[0]["visual_focus_id"] == "visual_focus_001"
    assert segments[0]["is_ai_recommended_highlight"] is False
    assert segments[0]["is_final_clip"] is False


def test_build_visual_focus_segments_from_subtitle_density() -> None:
    segments = build_visual_focus_segments(SRT_TEXT, {}, max_segments=2)

    assert segments
    assert all(segment["purpose"] == "first_round_detailed_frame_sampling_only" for segment in segments)
    assert all(segment["is_ai_recommended_highlight"] is False for segment in segments)


def test_build_scene_segments_from_empty_srt_raises() -> None:
    with pytest.raises(ValueError, match="parseable SRT"):
        build_scene_segments_from_raw_srt("not a subtitle")
