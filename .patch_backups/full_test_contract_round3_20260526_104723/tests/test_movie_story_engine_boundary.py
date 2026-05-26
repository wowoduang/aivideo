from __future__ import annotations

import sys
import types

from app.services.movie_story import engine_policy
from app.services.movie_story.engines import run_highlight_edit_engine, run_movie_story_engine
from app.services.movie_story.unified_entry import movie_story_scene_overrides_from_request
from app.services.movie_story.narration_runtime import _build_disabled_migration_script_items


def test_movie_story_policy_auto_defaults_to_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True
    assert decision.reason == "auto_selected_native"


def test_highlight_policy_auto_defaults_to_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_HIGHLIGHT_EDIT,
        requested_backend="auto",
        compatibility_engine="highlight_edit_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True
    assert decision.reason == "auto_selected_native"


def test_native_highlight_request_uses_native_backend(monkeypatch):
    captured = {}

    def fake_native_highlight(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [], "composition_plan": {"segments": []}}

    import app.services.movie_story.engines as engines

    monkeypatch.setattr(engines, "run_native_highlight_edit_engine", fake_native_highlight)

    payload = run_highlight_edit_engine(
        video_path="demo.mp4",
        mode="highlight_recut",
        engine_backend="native",
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "native"
    assert payload["engine_backend_info"]["requested_backend"] == "native"
    assert payload["engine_backend_info"]["selected_backend"] == "native"
    assert captured["video_path"] == "demo.mp4"
    assert "engine_backend" not in captured


def test_legacy_highlight_backend_still_available(monkeypatch):
    captured = {}

    def fake_legacy_highlight(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [], "composition_plan": {"segments": []}}

    import app.services.movie_story.engines as engines

    monkeypatch.setattr(engines, "run_legacy_highlight_edit_engine", fake_legacy_highlight)

    payload = run_highlight_edit_engine(
        video_path="demo.mp4",
        mode="highlight_recut",
        engine_backend="legacy",
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "legacy"
    assert payload["engine_backend_info"]["selected_backend"] == "legacy"
    assert "engine_backend" not in captured


def test_legacy_movie_story_engine_keeps_old_call_shape(monkeypatch):
    captured = {}

    def fake_movie_story_pipeline(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [{"text": "demo"}]}

    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=fake_movie_story_pipeline)
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    payload = run_movie_story_engine(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        engine_backend="legacy",
        scene_overrides={"target_duration_minutes": 6},
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "legacy"
    assert payload["engine_backend_info"]["compatibility_engine"] == "subtitle_first_pipeline"
    assert "engine_backend" not in captured
    assert captured["scene_overrides"]["target_duration_minutes"] == 6


def test_auto_native_highlight_failure_falls_back_to_legacy(monkeypatch):
    calls = {"native": 0, "legacy": 0}

    def fake_native_highlight(**kwargs):
        calls["native"] += 1
        return {"success": False, "error": "native failed"}

    def fake_legacy_highlight(**kwargs):
        calls["legacy"] += 1
        return {"success": True, "script_items": [], "composition_plan": {"segments": []}}

    import app.services.movie_story.engines as engines

    monkeypatch.setattr(engines, "run_native_highlight_edit_engine", fake_native_highlight)
    monkeypatch.setattr(engines, "run_legacy_highlight_edit_engine", fake_legacy_highlight)

    payload = run_highlight_edit_engine(
        video_path="demo.mp4",
        mode="highlight_recut",
    )

    assert payload["success"] is True
    assert calls == {"native": 1, "legacy": 1}
    assert payload["engine_backend"] == "legacy"
    assert payload["engine_backend_info"]["requested_backend"] == "auto"
    assert payload["engine_backend_info"]["selected_backend"] == "legacy"
    assert payload["engine_backend_info"]["reason"] == "native_payload_failed_auto_failover_legacy"
    assert payload["native_failure_payload"]["error"] == "native failed"


def test_explicit_native_highlight_failure_does_not_fallback(monkeypatch):
    calls = {"native": 0, "legacy": 0}

    def fake_native_highlight(**kwargs):
        calls["native"] += 1
        return {"success": False, "error": "native failed"}

    def fake_legacy_highlight(**kwargs):
        calls["legacy"] += 1
        return {"success": True}

    import app.services.movie_story.engines as engines

    monkeypatch.setattr(engines, "run_native_highlight_edit_engine", fake_native_highlight)
    monkeypatch.setattr(engines, "run_legacy_highlight_edit_engine", fake_legacy_highlight)

    payload = run_highlight_edit_engine(
        video_path="demo.mp4",
        mode="highlight_recut",
        engine_backend="native",
    )

    assert payload["success"] is False
    assert calls == {"native": 1, "legacy": 0}
    assert payload["engine_backend"] == "native"
    assert payload["engine_backend_info"]["requested_backend"] == "native"
    assert payload["engine_backend_info"]["selected_backend"] == "native"


def test_scene_overrides_engine_backend_is_stripped(monkeypatch):
    captured = {}

    def fake_movie_story_pipeline(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": []}

    fake_module = types.SimpleNamespace(run_subtitle_first_pipeline=fake_movie_story_pipeline)
    monkeypatch.setitem(sys.modules, "app.services.subtitle_first_pipeline", fake_module)

    payload = run_movie_story_engine(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        scene_overrides={"engine_backend": "legacy", "target_duration_minutes": 5},
    )

    assert payload["success"] is True
    assert "engine_backend" not in captured["scene_overrides"]
    assert captured["scene_overrides"]["target_duration_minutes"] == 5


def test_movie_story_skip_llm_request_is_preserved():
    overrides = movie_story_scene_overrides_from_request({
        "target_duration_minutes": 8,
        "skip_llm": True,
        "movie_story_strategy": "legacy_understanding",
    })

    assert overrides["skip_llm"] is True


def test_disabled_narration_accepts_srt_timecodes_without_llm():
    items = _build_disabled_migration_script_items([
        {
            "segment_id": "s1",
            "start": "00:08:41,018",
            "end": "00:08:45,518",
            "main_text_evidence": "demo",
        }
    ])

    assert items[0]["llm_skipped"] is True
    assert items[0]["start"] == 521.018
    assert items[0]["end"] == 525.518
    assert "流程测试占位" in items[0]["narration"]
