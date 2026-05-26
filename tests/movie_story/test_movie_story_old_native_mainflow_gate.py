# -*- coding: utf-8 -*-
from __future__ import annotations

"""Guard old Native Runtime LLM stages from re-entering movie_story mainflow."""

from pathlib import Path

from app.services.movie_story.engine_policy import (
    BACKEND_AUTO,
    BACKEND_NATIVE,
    ENGINE_KIND_MOVIE_STORY,
    decide_engine_backend,
    native_ready_for,
)


def test_movie_story_auto_does_not_select_old_native_runtime() -> None:
    decision = decide_engine_backend(
        engine_kind=ENGINE_KIND_MOVIE_STORY,
        requested_backend=BACKEND_AUTO,
        compatibility_engine="subtitle_first_pipeline",
    )

    assert native_ready_for(ENGINE_KIND_MOVIE_STORY) is False
    assert decision.selected_backend != BACKEND_NATIVE
    assert decision.reason != "auto_selected_native"


def test_old_segment_visual_understanding_default_is_disabled() -> None:
    source = Path("app/services/segment_visual_understanding.py").read_text(encoding="utf-8")
    assert '"enabled": _as_bool(_get_cfg("enable_segment_visual_understanding", False), False),' in source


def test_native_runtime_no_longer_defaults_to_full_subtitle_llm_or_visual_card_llm() -> None:
    source = Path("app/services/movie_story/movie_story_native_engine.py").read_text(encoding="utf-8")

    assert (
        'has_llm if use_legacy_understanding else has_llm and narration_llm_mode in {"hybrid", "full", "batch"}'
        not in source
    )
    assert 'has_llm if use_legacy_understanding else has_llm and narration_llm_mode == "full"' not in source
    assert "lambda: enrich_scene_evidence_with_visual_cards(narration_evidence, global_summary)" not in source
    assert "lambda: narration_evidence" in source
