# -*- coding: utf-8 -*-
from __future__ import annotations

from app.services.movie_story.visual_focus_segments import build_visual_focus_segments


def test_build_visual_focus_segments_combines_visual_and_subtitle_structure() -> None:
    scenes = [
        {"scene_id": "scene_0001", "start": 0.0, "end": 20.0, "duration": 20.0, "shot_ids": ["shot_0001"]},
        {"scene_id": "scene_0002", "start": 20.0, "end": 40.0, "duration": 20.0, "shot_ids": ["shot_0002", "shot_0003", "shot_0004"]},
        {"scene_id": "scene_0003", "start": 40.0, "end": 60.0, "duration": 20.0, "shot_ids": ["shot_0005"]},
    ]
    shots = [
        {"shot_id": "shot_0001", "cut_score": 2.0},
        {"shot_id": "shot_0002", "cut_score": 20.0},
        {"shot_id": "shot_0003", "cut_score": 21.0},
        {"shot_id": "shot_0004", "cut_score": 19.0},
        {"shot_id": "shot_0005", "cut_score": 1.0},
    ]
    subtitles = [
        {"start": 21.0, "end": 22.0, "text": "A：......"},
        {"start": 23.0, "end": 24.0, "text": "B：......！"},
        {"start": 25.0, "end": 26.0, "text": "A：......？"},
    ]
    result = build_visual_focus_segments(
        scene_segments=scenes,
        shot_boundaries=shots,
        subtitles=subtitles,
        max_segments=1,
    )
    assert len(result) == 1
    assert result[0]["scene_id"] == "scene_0002"
    assert result[0]["source"] == "auto_hybrid_visual_audio_subtitle_structure"
    assert "subtitle_structure" in result[0]["reason"]


def test_build_visual_focus_segments_does_not_need_semantic_keywords() -> None:
    scenes = [
        {"scene_id": "scene_0001", "start": 0.0, "end": 30.0, "duration": 30.0, "shot_ids": ["shot_0001"]},
        {"scene_id": "scene_0002", "start": 30.0, "end": 60.0, "duration": 30.0, "shot_ids": ["shot_0002", "shot_0003"]},
    ]
    result = build_visual_focus_segments(
        scene_segments=scenes,
        shot_boundaries=[{"shot_id": "shot_0002", "cut_score": 25.0}, {"shot_id": "shot_0003", "cut_score": 25.0}],
        subtitles=[{"start": 31.0, "end": 32.0, "text": "......"}],
        max_segments=1,
    )
    assert result[0]["scene_id"] == "scene_0002"


def test_build_visual_focus_segments_supports_manual_override() -> None:
    scenes = [{"scene_id": "scene_0001", "start": 0.0, "end": 20.0, "duration": 20.0, "shot_ids": []}]
    result = build_visual_focus_segments(
        scene_segments=scenes,
        shot_boundaries=[],
        manual_segments=[{"start": 5.0, "end": 9.0}],
        max_segments=1,
    )
    assert result[0]["source"] == "manual"
