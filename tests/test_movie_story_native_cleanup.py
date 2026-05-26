from __future__ import annotations


def test_movie_story_native_engine_exports_new_primary_name():
    from app.services.movie_story import movie_story_native_engine as native

    assert hasattr(native, "run_movie_story_native_engine")
    assert native.run_subtitle_first_pipeline is not native.run_movie_story_native_engine
    assert callable(native.run_movie_story_native_engine)
    assert callable(native.run_subtitle_first_pipeline)


def test_subtitle_first_adapter_reexports_native_primary_name():
    import app.services.subtitle_first_pipeline as adapter

    assert hasattr(adapter, "run_movie_story_native_engine")
    assert hasattr(adapter, "run_subtitle_first_pipeline")


def test_composition_bridge_uses_native_source_metadata():
    from app.services.movie_story.composition_bridge import build_movie_story_composition_plan

    plan = build_movie_story_composition_plan(
        video_path="demo.mp4",
        script_items=[{"start": 0.0, "end": 2.0, "text": "demo"}],
        story_highlights=[],
        narration_evidence=[],
        target_duration_seconds=60,
    )

    data = plan.model_dump() if hasattr(plan, "model_dump") else dict(plan)
    metadata = data.get("metadata") or {}
    assert metadata.get("source_pipeline") == "movie_story_native_engine"
