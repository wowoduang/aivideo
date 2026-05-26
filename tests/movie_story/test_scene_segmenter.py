# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.movie_story.scene_segmenter import build_scene_segments


def test_build_scene_segments_groups_shots() -> None:
    shots = [
        {"shot_id": "shot_0001", "start": 0.0, "end": 10.0},
        {"shot_id": "shot_0002", "start": 10.0, "end": 20.0},
        {"shot_id": "shot_0003", "start": 20.0, "end": 35.0},
        {"shot_id": "shot_0004", "start": 35.0, "end": 60.0},
    ]
    subtitles = [
        {"start": 2.0, "end": 4.0, "text": "甲说话"},
        {"start": 22.0, "end": 25.0, "text": "乙回答"},
        {"start": 41.0, "end": 43.0, "text": "丙进入场景"},
    ]
    scenes = build_scene_segments(shot_boundaries=shots, subtitles=subtitles, target_scene_duration_sec=25.0)
    assert len(scenes) >= 2
    assert scenes[0]["scene_id"].startswith("scene_")
    assert scenes[0]["subtitle_count"] >= 1
