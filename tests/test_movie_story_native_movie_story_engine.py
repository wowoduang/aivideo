from __future__ import annotations

import shutil

import pytest
from pathlib import Path

from app.utils import workspace

from app.services.movie_story import engine_policy
from app.services.movie_story.native_engines import run_native_movie_story_engine


def test_movie_story_native_policy_is_not_current_mainflow():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_LEGACY
    assert decision.native_ready is False


def test_native_movie_story_entry_delegates_to_moved_engine(monkeypatch):
    import app.services.movie_story.movie_story_native_engine as native_module
    import app.services.movie_story.native_engines as native_engines

    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"success": True, "script_items": [{"text": "ok"}], "composition_plan": {"segments": []}}

    monkeypatch.setattr(native_module, "run_movie_story_native_engine", fake_run, raising=False)
    monkeypatch.setattr(native_engines, "run_movie_story_native_engine", fake_run, raising=False)

    payload = run_native_movie_story_engine(video_path="demo.mp4", subtitle_path="demo.srt")

    assert payload["success"] is True
    assert captured["video_path"] == "demo.mp4"
    assert captured["subtitle_path"] == "demo.srt"


def test_apply_highlight_plan_nonblocking_skips_on_bad_plan(monkeypatch):
    import app.services.movie_story.movie_story_native_engine as native

    audit = {}

    def broken_apply(*args, **kwargs):
        raise ValueError("could not convert string to float: '00:08:41,018'")

    monkeypatch.setattr(native, "_apply_llm_highlight_plan", broken_apply)
    monkeypatch.setattr(native, "_audit_pipeline_marker", lambda stage, payload, local_vars: audit.update({"stage": stage, "payload": payload}))

    result = native._apply_llm_highlight_plan_nonblocking(
        [{"segment_id": "s1", "start": 1, "end": 2, "llm_window_selected": True}],
        {},
        {"plan_policy": "legacy_llm_full_understanding_plan"},
        {},
    )

    assert result[0]["segment_id"] == "s1"
    assert result[0]["llm_highlight_selected"] is True
    assert result[0]["llm_highlight_plan_skipped"] is True
    assert audit["stage"] == "04b_apply_highlight_plan_skipped"
    assert audit["payload"]["fallback"] == "use_unannotated_scene_evidence"


def test_direct_cut_contract_keeps_raw_audio_and_highlight_flags():
    from app.services.movie_story.direct_cut_runtime import force_direct_cut_script_contract

    items = force_direct_cut_script_contract(
        [
            {
                "segment_id": "s1",
                "direct_cut_first": True,
                "start": 0,
                "end": 60,
                "narration": "should be cleared",
                "OST": 2,
                "composition_audio_mode": "tts",
            }
        ]
    )

    assert items[0]["direct_cut_first"] is True
    assert items[0]["narration"] == ""
    assert items[0]["OST"] == 1
    assert items[0]["composition_audio_mode"] == "raw"
    assert items[0]["llm_raw_voice_keep"] is True
    assert items[0]["raw_voice_retain_suggestion"] is True
    assert items[0]["highlight_filter_selected"] is True


def test_historical_drama_direct_cut_returns_before_scene_detection(monkeypatch):
    import app.services.movie_story.movie_story_native_engine as native

    output_dir = Path(workspace.temp_dir("tests/test_historical_direct_cut_native_engine", create=True))
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "movie_story.json"

    monkeypatch.setattr(native, "_ensure_llm_ready", lambda *args: ("", "", ""))
    monkeypatch.setattr(native, "_has_real_llm_config", lambda api_key, model: False)
    monkeypatch.setattr(native, "_audit_video_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(native, "_audit_pipeline_marker", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        native,
        "build_subtitle_segments",
        lambda **kwargs: {
            "segments": [
                {"start": 0, "end": 15, "text": "a"},
                {"start": 15, "end": 35, "text": "b"},
                {"start": 35, "end": 60, "text": "c"},
            ],
            "source": "test",
            "backend": "test",
        },
    )
    monkeypatch.setattr(
        native,
        "build_video_boundary_candidates",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scene detection should be skipped")),
    )
    monkeypatch.setattr(
        native,
        "build_authoritative_plot_chunks",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("plot chain should be skipped")),
    )

    result = native._run(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        text_api_key="",
        text_base_url="",
        text_model="",
        style="historical_drama",
        output_script_path=str(output_path),
        generation_mode="balanced",
        visual_mode="auto",
        scene_overrides={},
        progress=lambda *args, **kwargs: None,
        asr_backend="test",
        regenerate_subtitle=False,
    )

    assert result["success"] is True
    assert result["direct_cut_first"] is True
    assert result["video_boundary_candidate_count"] == 0
    assert all(item["direct_cut_first"] for item in result["script_items"])
    assert all(item["OST"] == 1 for item in result["script_items"])


@pytest.mark.skip(reason="old native movie_story finalize path is archived; current mainflows are two_round/two_round_visual/multi_short_video")
def test_legacy_understanding_highlight_mode_uses_old_finalize_path(monkeypatch):
    import app.services.movie_story.movie_story_native_engine as native

    calls = []
    output_dir = Path(workspace.temp_dir("tests/test_legacy_understanding_native_engine", create=True))
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "movie_story.json"

    monkeypatch.setattr(native.utils, "temp_dir", lambda name="": str(output_dir / "temp" / str(name or "")))
    monkeypatch.setattr(native, "_ensure_llm_ready", lambda *args: ("key", "url", "model"))
    monkeypatch.setattr(native, "_has_real_llm_config", lambda api_key, model: True)
    monkeypatch.setattr(native, "_audit_video_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(native, "_audit_pipeline_marker", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        native,
        "build_subtitle_segments",
        lambda **kwargs: {"segments": [{"start": 0, "end": 5, "text": "story"}], "source": "test", "backend": "test"},
    )
    monkeypatch.setattr(
        native,
        "build_legacy_full_subtitle_understanding",
        lambda **kwargs: ({"subtitle_understanding_status": "ok", "highlight_windows": [{"start": 0, "end": 5}]}, [], []),
    )
    monkeypatch.setattr(native, "build_video_boundary_candidates", lambda **kwargs: [])
    monkeypatch.setattr(
        native,
        "build_authoritative_plot_chunks",
        lambda *args, **kwargs: [{"scene_id": "s1", "segment_id": "s1", "start": 0, "end": 5, "subtitle_text": "story"}],
    )
    monkeypatch.setattr(native, "build_global_summary", lambda *args, **kwargs: {"main_storyline": "old global"})
    monkeypatch.setattr(native, "build_global_story_context", lambda **kwargs: kwargs["existing_global_summary"])
    monkeypatch.setattr(native, "collect_candidate_boundaries", lambda segments: [])
    monkeypatch.setattr(native, "align_story_boundaries", lambda chunks, **kwargs: chunks)
    monkeypatch.setattr(native, "_apply_full_subtitle_plan_to_chunks", lambda chunks, full: chunks)
    monkeypatch.setattr(native, "refresh_authoritative_plot_map", lambda chunks, stage="": chunks)
    monkeypatch.setattr(native, "extract_representative_frames_for_scenes", lambda **kwargs: [])
    monkeypatch.setattr(
        native,
        "fuse_scene_evidence",
        lambda scenes, frame_records, visual_observations: [
            {"segment_id": "s1", "scene_id": "s1", "start": 0, "end": 5, "subtitle_text": "story"}
        ],
    )
    monkeypatch.setattr(native, "_enrich_evidence", lambda evidence, chunks, global_summary: None)
    monkeypatch.setattr(
        native,
        "add_local_understanding",
        lambda evidence, **kwargs: [dict(x, local_understanding={"core_event": "truth"}) for x in evidence],
    )
    monkeypatch.setattr(native, "enrich_evidence_items", lambda items, global_summary: list(items))
    monkeypatch.setattr(native, "enrich_legacy_segment_understanding", lambda items: list(items))
    monkeypatch.setattr(
        native,
        "validate_story_segments",
        lambda evidence, **kwargs: [dict(x, story_validation={"validator_status": "pass"}) for x in evidence],
    )

    def fake_plan(*args, **kwargs):
        assert kwargs["allow_llm"] is True
        return {"selected_segment_ids": ["s1"], "must_keep_ranges": []}

    monkeypatch.setattr(native, "_safe_plan_story_highlights", fake_plan)
    monkeypatch.setattr(native, "_apply_llm_highlight_plan", lambda evidence, full, plan: list(evidence))
    monkeypatch.setattr(native, "_select_final_story_evidence", lambda evidence: list(evidence))

    def fake_collect_legacy(video_path, segments, scene_overrides):
        calls.append("legacy_cut_points")
        return [0.0, 5.0]

    monkeypatch.setattr(native, "_collect_scene_cut_points", fake_collect_legacy)
    monkeypatch.setattr(
        native,
        "_collect_scene_cut_points_from_existing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("native cut points used")),
    )
    monkeypatch.setattr(
        native,
        "select_story_highlights_with_legacy_priority",
        lambda **kwargs: ([{"highlight_id": "h1", "segment_id": "s1", "start": 0, "end": 5}], {"selection_source": "legacy"}),
    )
    monkeypatch.setattr(
        native,
        "_build_highlight_narration_segments",
        lambda **kwargs: [{"segment_id": "s1", "scene_id": "s1", "start": 0, "end": 5, "highlight_id": "h1"}],
    )
    monkeypatch.setattr(native, "evaluate_evidence_items", lambda items: {"passed": True})
    monkeypatch.setattr(native, "_ensure_full_subtitle_highlight_windows", lambda **kwargs: kwargs["full_subtitle_understanding"])
    monkeypatch.setattr(
        native,
        "_select_narration_evidence_for_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("native narration evidence selector used")),
    )

    def fake_highlight_script(items):
        calls.append("legacy_highlight_script")
        return [{"segment_id": "s1", "start": 0, "end": 5, "narration": "old highlight", "OST": 2}]

    monkeypatch.setattr(native, "_build_highlight_only_script", fake_highlight_script)
    monkeypatch.setattr(
        native,
        "_generate_narration_with_mode",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("native narration generator used")),
    )
    monkeypatch.setattr(native, "_align_script_items_to_scene_cuts", lambda items, cut_points: list(items))
    monkeypatch.setattr(native, "_filter_script_items_by_highlights", lambda items, highlights: list(items))
    monkeypatch.setattr(native, "ensure_script_shape", lambda items: list(items))
    monkeypatch.setattr(native, "finalize_narration_script", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("native finalize used")))
    monkeypatch.setattr(native, "build_understanding_baseline_report", lambda **kwargs: {"passed": True})
    monkeypatch.setattr(native, "_validate_pipeline_quality", lambda **kwargs: [])
    monkeypatch.setattr(native, "validate_script_items", lambda items: None)
    monkeypatch.setattr(native, "build_understanding_script_payload", lambda **kwargs: {"artifact": "movie_story_understanding_script"})
    monkeypatch.setattr(native, "build_movie_story_composition_plan", lambda **kwargs: {"segments": []})
    monkeypatch.setattr(native, "validate_composition_plan", lambda plan: {"passed": True})
    monkeypatch.setattr(native, "_build_story_audit_payload", lambda **kwargs: {})

    result = native._run(
        video_path="demo.mp4",
        subtitle_path="demo.srt",
        text_api_key="",
        text_base_url="",
        text_model="",
        style="general",
        output_script_path=str(output_path),
        generation_mode="balanced",
        visual_mode="auto",
        scene_overrides={"movie_story_strategy": "legacy_understanding", "highlight_only": True},
        progress=lambda *args, **kwargs: None,
        asr_backend="test",
        regenerate_subtitle=False,
    )

    assert result["success"] is True
    assert result["narration_finalize_report"]["pipeline"] == "legacy_subtitle_first_finalize"
    assert calls == ["legacy_cut_points", "legacy_highlight_script"]
