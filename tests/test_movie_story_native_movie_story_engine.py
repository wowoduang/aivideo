from __future__ import annotations

from app.services.movie_story import engine_policy
from app.services.movie_story.native_engines import run_native_movie_story_engine


def test_movie_story_native_policy_is_ready():
    decision = engine_policy.decide_engine_backend(
        engine_kind=engine_policy.ENGINE_KIND_MOVIE_STORY,
        requested_backend="auto",
        compatibility_engine="subtitle_first_pipeline",
    )
    assert decision.selected_backend == engine_policy.BACKEND_NATIVE
    assert decision.native_ready is True


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
