from __future__ import annotations

from app.services.movie_story.engine_status import explain_engine_policy, get_engine_status


def test_engine_status_reports_current_backend_readiness():
    status = get_engine_status()
    assert status["success"] is True
    assert status["native_ready"]["movie_story"] is False
    assert status["native_ready"]["highlight_edit"] is True
    assert status["engines"]["movie_story"]["selected_backend"] == "legacy"
    assert status["engines"]["highlight_edit"]["selected_backend"] == "native"


def test_engine_policy_explain_legacy_request():
    info = explain_engine_policy(engine_kind="movie_story", requested_backend="legacy")
    assert info["requested_backend"] == "legacy"
    assert info["selected_backend"] == "legacy"
    assert info["compatibility_engine"] == "subtitle_first_pipeline"
