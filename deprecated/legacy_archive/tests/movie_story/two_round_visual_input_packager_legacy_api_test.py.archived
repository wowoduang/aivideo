# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.two_round_visual_input_packager import build_visual_first_round_context


def test_build_visual_first_round_context_marks_focus_as_non_final() -> None:
    context = build_visual_first_round_context(
        scene_segments=[{"scene_id": "scene_001", "start": 0, "end": 60, "subtitle_excerpt": "你好"}],
        visual_focus_segments=[{"visual_focus_id": "visual_focus_001", "start": 10, "end": 40, "reason": "dialogue"}],
        low_density_keyframes=[{"frame_id": "scene_001_frame_01", "timestamp": 30, "sampling_stage": "scene_context_low_density", "frame_path": "a.jpg"}],
        focus_keyframes=[{"frame_id": "focus_001_frame_01", "timestamp": 20, "sampling_stage": "visual_focus_detail", "frame_path": "b.jpg"}],
    )

    assert "不是最终剪辑片段" in context
    assert "谁在说话" in context
    assert "visual_focus_001" in context


def test_build_visual_first_round_context_requires_focus_frames() -> None:
    with pytest.raises(ValueError, match="focus_keyframes"):
        build_visual_first_round_context(
            scene_segments=[{"scene_id": "scene_001", "start": 0, "end": 60}],
            visual_focus_segments=[{"visual_focus_id": "visual_focus_001", "start": 10, "end": 40}],
            low_density_keyframes=[{"frame_id": "scene_frame", "timestamp": 20, "frame_path": "a.jpg"}],
            focus_keyframes=[],
        )
