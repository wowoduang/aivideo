# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.movie_story.visual_focus_segments import build_visual_focus_segments


def test_build_visual_focus_segments_prefers_dialogue_dense_scenes() -> None:
    scenes = [
        {"scene_id": "scene_0001", "start": 0.0, "end": 20.0, "duration": 20.0, "subtitle_count": 1},
        {"scene_id": "scene_0002", "start": 20.0, "end": 40.0, "duration": 20.0, "subtitle_count": 6},
    ]
    subtitles = [
        {"start": 1.0, "end": 2.0, "text": "背景介绍"},
        {"start": 21.0, "end": 22.0, "text": "你为什么来这里？"},
        {"start": 23.0, "end": 24.0, "text": "我来找你。"},
        {"start": 25.0, "end": 26.0, "text": "他就在这儿。"},
        {"start": 27.0, "end": 28.0, "text": "你别骗我！"},
        {"start": 29.0, "end": 30.0, "text": "到底是谁？"},
        {"start": 31.0, "end": 32.0, "text": "就是他。"},
    ]
    result = build_visual_focus_segments(scene_segments=scenes, subtitles=subtitles, max_segments=1)
    assert len(result) == 1
    assert result[0]["scene_id"] == "scene_0002"
