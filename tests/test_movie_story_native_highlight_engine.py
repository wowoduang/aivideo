from __future__ import annotations

import os
import tempfile

from app.services.movie_story import engine_policy
from app.services.movie_story import highlight_native_engine as native
from app.services.movie_story.engines import run_highlight_edit_engine, run_movie_story_engine


def _placeholder_video() -> str:
    path = os.path.join(tempfile.gettempdir(), "aivideo_stage_q_placeholder.mp4")
    if not os.path.exists(path):
        with open(path, "wb") as handle:
            handle.write(b"")
    return path


def _patch_native_runtime(monkeypatch):
    monkeypatch.setattr(native, "build_subtitle_segments", lambda *args, **kwargs: {"segments": [
        {"seg_id": "sub_001", "start": 0.0, "end": 4.0, "text": "开场冲突"},
    ]})
    monkeypatch.setattr(native, "build_video_boundary_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(native, "build_scenes", lambda *args, **kwargs: [{
        "scene_id": "scene_001",
        "start": 0.0,
        "end": 4.0,
        "duration": 4.0,
        "subtitle_ids": ["sub_001"],
        "subtitle_texts": ["开场冲突"],
        "subtitle_text": "开场冲突",
    }])
    monkeypatch.setattr(native, "build_plot_chunks_from_subtitles", lambda *args, **kwargs: [{
        "start": 0.0,
        "end": 4.0,
        "highlight_score": 0.9,
        "importance_level": "high",
        "attraction_level": "high",
        "narration_level": "brief",
        "plot_function": "hook",
        "plot_role": "opening",
        "aligned_subtitle_text": "开场冲突",
        "real_narrative_state": "冲突出现",
        "surface_dialogue_meaning": "冲突出现",
        "raw_voice_retain_suggestion": True,
        "subtitle_ids": ["sub_001"],
        "scene_id": "scene_001",
    }])
    monkeypatch.setattr(native.context_runtime, "build_shared_audio_signal_context", lambda video_path: {})
    monkeypatch.setattr(native.context_runtime, "annotate_audio_signal_context", lambda video_path, clips, audio_context=None: (
        list(clips),
        {
            "audio_signal_used": False,
            "audio_signal_clip_count": 0,
            "audio_raw_candidate_count": 0,
            "audio_signal_mean": 0.0,
            "audio_peak_mean": 0.0,
        },
    ))
    monkeypatch.setattr(native.output_runtime, "write_outputs", lambda *args, **kwargs: {
        "composition_plan_path": "",
        "script_path": "",
    })


def test_highlight_policy_auto_now_selects_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_HIGHLIGHT_EDIT,
        requested_backend="auto",
        compatibility_engine="highlight_edit_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True


def test_movie_story_policy_now_selects_native():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True


def test_native_highlight_engine_runs_without_legacy_pipeline(monkeypatch):
    _patch_native_runtime(monkeypatch)

    payload = run_highlight_edit_engine(
        video_path=_placeholder_video(),
        mode="highlight_recut",
        target_duration_seconds=60,
        visual_mode="off",
        engine_backend="native",
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "native"
    assert payload["engine_backend_info"]["selected_backend"] == "native"
    assert payload["composition_plan"]
    assert payload["script_items"]
    assert payload["candidate_stats"]["plot_candidate_count"] >= 1


def test_highlight_legacy_backend_is_still_available(monkeypatch):
    captured = {}

    def fake_legacy(*args, **kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [], "composition_plan": {"segments": []}}

    import app.services.movie_story.engines as engines

    monkeypatch.setattr(engines, "run_legacy_highlight_edit_engine", fake_legacy)

    payload = run_highlight_edit_engine(
        video_path="demo.mp4",
        mode="highlight_recut",
        engine_backend="legacy",
    )

    assert payload["success"] is True
    assert payload["engine_backend"] == "legacy"
    assert payload["engine_backend_info"]["selected_backend"] == "legacy"
    assert captured["video_path"] == "demo.mp4"
