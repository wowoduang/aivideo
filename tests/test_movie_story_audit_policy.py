from app.services.movie_story import audit_policy


def test_legacy_stages_are_hidden_by_default(monkeypatch):
    monkeypatch.delenv("MOVIE_STORY_AUDIT_INCLUDE_LEGACY_STAGES", raising=False)

    assert audit_policy.should_skip_stage("01_plot_chunks") is True


def test_legacy_stages_can_be_included_for_migration_audit(monkeypatch):
    monkeypatch.setenv("MOVIE_STORY_AUDIT_INCLUDE_LEGACY_STAGES", "1")

    assert audit_policy.should_skip_stage("01_plot_chunks") is False
    assert "01_plot_chunks" in audit_policy.keep_stages()
    assert audit_policy.production_stage_summary()["legacy_stages_included"] is True


def test_legacy_stages_can_be_included_for_current_run_only(monkeypatch):
    monkeypatch.delenv("MOVIE_STORY_AUDIT_INCLUDE_LEGACY_STAGES", raising=False)

    assert audit_policy.should_skip_stage("02_scene_evidence", include_legacy=True) is False
    assert "02_scene_evidence" in audit_policy.keep_stages(include_legacy=True)
    assert audit_policy.should_skip_stage("02_scene_evidence") is True
