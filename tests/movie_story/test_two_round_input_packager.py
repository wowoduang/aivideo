# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for two_round_input_packager."""

from app.services.movie_story.two_round_input_packager import build_two_round_input_packages


def test_build_two_round_input_packages_after_selection() -> None:
    packages = build_two_round_input_packages(
        [{"highlight_id": "highlight_001", "source": "selected_highlight", "start": 10.0, "end": 20.0}],
        [{"highlight_id": "highlight_001", "start": 10.0, "end": 20.0, "subtitle_text": "字幕证据"}],
        [{"highlight_id": "highlight_001", "sampling_stages": ["selected_highlight_detail"], "keyframes": [{"time": 12.0, "frame_path": "x.jpg"}]}],
        speech_cues_by_highlight=[{"highlight_id": "highlight_001", "speaker_turn_count": 2}],
    )

    assert packages[0]["highlight_id"] == "highlight_001"
    assert packages[0]["source"] == "selected_highlight"
    assert packages[0]["subtitle_evidence"]["text"] == "字幕证据"
    assert packages[0]["visual_evidence"]["keyframes"][0]["frame_path"] == "x.jpg"
    assert packages[0]["llm_input_policy"]["highlight_is_selected_before_detailed_visual_sampling"] is True
