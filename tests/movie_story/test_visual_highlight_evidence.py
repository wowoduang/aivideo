# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for two-stage visual_highlight_evidence package building."""

from app.services.movie_story.visual_highlight_evidence import build_visual_evidence_by_highlight


def test_build_visual_evidence_by_highlight_keeps_sampling_stage_facts() -> None:
    result = build_visual_evidence_by_highlight(
        [{"highlight_id": "highlight_001", "source": "auto_candidate", "start": 10.0, "end": 20.0}],
        [
            {
                "highlight_id": "highlight_001",
                "timestamp": 12.0,
                "frame_path": "frames/h1.jpg",
                "reason": "candidate_fact_1",
                "sampling_stage": "candidate_fact",
            }
        ],
        shot_candidates=[{"shot_id": "shot_001", "start": 9.0, "end": 13.0}],
        scene_candidates=[{"scene_id": "scene_001", "start": 8.0, "end": 25.0}],
        highlight_narration_segments=[{"highlight_id": "highlight_001", "start": 10.0, "end": 20.0, "subtitle_text": "字幕证据"}],
    )

    assert result[0]["highlight_id"] == "highlight_001"
    assert result[0]["sampling_stages"] == ["candidate_fact"]
    assert result[0]["overlapping_shot_ids"] == ["shot_001"]
    assert result[0]["overlapping_scene_ids"] == ["scene_001"]
    assert result[0]["backend_visual_facts"] == []
