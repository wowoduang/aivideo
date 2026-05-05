import json
from pathlib import Path

from app.services.movie_story.highlight_typing import classify_scene
from app.services.movie_story.story_runtime import extract_highlights, refresh_authoritative_plot_map


def test_plot_function_only_scene_can_be_typed_highlight():
    item = {
        "scene_id": "plot_001",
        "start": 1.0,
        "end": 4.0,
        "subtitle_text": "",
        "plot_function": "信息揭露",
        "highlight_score": 0.321,
    }
    labels = classify_scene(item, min_confidence=0.52, fallback_confidence=0.45)
    assert labels
    assert any(x["highlight_type_key"] == "information_reveal" for x in labels)


def test_extract_highlights_from_manifest_like_plot_only_records():
    scenes = []
    for idx in range(12):
        scenes.append({
            "scene_id": f"plot_{idx:03d}",
            "segment_id": f"plot_{idx:03d}",
            "start": idx * 5.0,
            "end": idx * 5.0 + 3.0,
            "subtitle_text": "",
            "plot_function": "信息揭露",
            "importance_level": "medium",
        })
    refresh_authoritative_plot_map(scenes, stage="test")
    highlights = extract_highlights(scenes, cut_points=[], highlight_selectivity="balanced")
    assert highlights
    assert all(x.get("highlight_filter_selected") for x in highlights)
