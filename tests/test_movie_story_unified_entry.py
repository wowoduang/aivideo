from __future__ import annotations

import sys
import types

from app.services.movie_story import edit_modes
from app.services.movie_story import unified_entry


def test_resolve_unified_mode_for_movie_story_request():
    mode = edit_modes.resolve_unified_mode("movie-story-script", {"target_duration_minutes": 6, "highlight_only": False})
    assert mode.entry == edit_modes.ENTRY_MOVIE_STORY_SCRIPT
    assert mode.mode == edit_modes.MOVIE_STORY
    assert mode.generates_narration is True
    assert mode.uses_external_narration is False


def test_resolve_unified_mode_promotes_external_narration_to_narrated_highlight():
    mode = edit_modes.resolve_unified_mode(
        "highlight-script",
        {"mode": "highlight_recut", "narration_text": "Opening hook. Then reveal."},
    )
    assert mode.entry == edit_modes.ENTRY_HIGHLIGHT_SCRIPT
    assert mode.mode == edit_modes.NARRATED_HIGHLIGHT_EDIT
    assert mode.uses_external_narration is True


def test_movie_story_overrides_preserve_advanced_controls():
    overrides = unified_entry.movie_story_scene_overrides_from_request(
        {
            "target_duration_minutes": 9,
            "video_theme": "Test Movie",
            "highlight_selectivity": "strict",
            "movie_story_enable_highlight_plan_llm": True,
            "scene_threshold": 31,
        }
    )
    assert overrides["target_duration_minutes"] == 9
    assert overrides["video_title"] == "Test Movie"
    assert overrides["short_name"] == "Test Movie"
    assert overrides["highlight_selectivity"] == "strict"
    assert overrides["movie_story_enable_highlight_plan_llm"] is True
    assert overrides["scene_threshold"] == 31


def test_run_highlight_request_normalizes_raw_highlight(monkeypatch):
    captured = {}

    def fake_run_highlight_edit_engine(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [], "composition_plan": {"mode": kwargs["mode"], "segments": []}}

    monkeypatch.setattr(unified_entry, "run_highlight_edit_engine", fake_run_highlight_edit_engine)

    result = unified_entry.run_unified_edit_request(
        entry="highlight_script",
        request={"video_path": "demo.mp4", "mode": "raw_highlight", "prefer_raw_audio": False},
    )

    assert result["success"] is True
    assert result["unified_entry"] == edit_modes.ENTRY_HIGHLIGHT_SCRIPT
    assert result["unified_mode"] == edit_modes.RAW_HIGHLIGHT
    assert captured["mode"] == edit_modes.HIGHLIGHT_RECUT
    assert captured["prefer_raw_audio"] is True


def test_run_movie_story_request_uses_task_output_path_and_returns_unified_metadata(monkeypatch):
    captured = {}

    def fake_run_subtitle_first_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "script_items": [{"start": 1.0, "end": 2.0, "text": "Demo"}],
            "composition_plan": {"mode": "movie_story", "segments": []},
            "script_path": kwargs["output_script_path"],
        }

    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=fake_run_subtitle_first_pipeline)
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    result = unified_entry.run_unified_edit_request(
        entry="movie_story_script",
        request={"video_path": "demo.mp4", "video_theme": "Demo", "cache_mode": "reuse"},
        output_script_path="E:/tmp/movie_story_script.json",
    )

    assert result["success"] is True
    assert result["unified_entry"] == edit_modes.ENTRY_MOVIE_STORY_SCRIPT
    assert result["unified_mode"] == edit_modes.MOVIE_STORY
    assert result["script_path"] == "E:/tmp/movie_story_script.json"
    assert captured["output_script_path"] == "E:/tmp/movie_story_script.json"
    assert captured["scene_overrides"]["video_title"] == "Demo"
    assert captured["regenerate_subtitle"] is False
