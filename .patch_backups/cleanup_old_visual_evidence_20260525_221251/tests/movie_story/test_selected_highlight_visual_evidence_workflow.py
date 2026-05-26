# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for selected_highlight_visual_evidence_workflow path naming."""

from pathlib import Path

from app.services.movie_story.selected_highlight_visual_evidence_workflow import (
    derive_selected_highlight_visual_evidence_paths,
)


def test_derive_selected_highlight_visual_evidence_paths() -> None:
    paths = derive_selected_highlight_visual_evidence_paths(Path("task/movie_story_script.json"))

    assert str(paths["highlights"]).replace("\\", "/") == "task/movie_story_script_highlights.json"
    assert str(paths["narration_segments"]).replace("\\", "/") == "task/movie_story_script_highlight_narration_segments.json"
    assert str(paths["keyframes"]).replace("\\", "/") == "task/movie_story_script_selected_highlight_keyframes.json"
    assert str(paths["visual_evidence"]).replace("\\", "/") == "task/movie_story_script_selected_highlight_visual_evidence.json"
    assert str(paths["two_round_packages"]).replace("\\", "/") == "task/movie_story_script_two_round_input_packages.json"
    assert str(paths["frame_dir"]).replace("\\", "/") == "task/movie_story_script_visual_frames/selected_highlight_detail"
    assert str(paths["contact_sheet"]).replace("\\", "/") == "task/movie_story_script_selected_highlight_contact_sheet.jpg"
