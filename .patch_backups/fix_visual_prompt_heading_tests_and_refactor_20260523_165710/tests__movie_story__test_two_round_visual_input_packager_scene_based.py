# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.movie_story.two_round_visual_input_packager import build_two_round_visual_input_package


def test_build_two_round_visual_input_package_contains_expected_sections() -> None:
    package = build_two_round_visual_input_package(
        raw_srt_text="1\n00:00:01,000 --> 00:00:03,000\n甲：你来了\n",
        scene_segments=[{"scene_id": "scene_0001", "start": 0.0, "end": 10.0, "shot_ids": ["shot_0001"], "subtitle_count": 1}],
        focus_segments=[{"segment_id": "focus_001", "start": 0.0, "end": 10.0, "source": "auto", "reason": "x"}],
        global_frames=[{"frame_id": "global_001", "path": "/tmp/a.jpg", "timestamp": 5.0, "scene_id": "scene_0001", "role": "global_scene_overview"}],
        focus_frames=[{"frame_id": "focus_001_01", "path": "/tmp/b.jpg", "timestamp": 3.0, "segment_id": "focus_001", "role": "focus_segment_detail"}],
    )
    context = package["prompt_context"]
    assert "【场景边界】" in context
    assert "【视觉重点片段（仅用于详细抽帧，不是最终剪辑片段）】" in context
    assert len(package["image_paths"]) == 2
