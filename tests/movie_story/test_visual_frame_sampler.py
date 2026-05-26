# -*- coding: utf-8 -*-
from __future__ import annotations

"""Tests for two-stage visual_frame_sampler planning functions."""

from app.services.movie_story.visual_frame_sampler import candidate_fact_frame_budget
from app.services.movie_story.visual_frame_sampler import sample_times_for_candidate_fact
from app.services.movie_story.visual_frame_sampler import sample_times_for_selected_highlight
from app.services.movie_story.visual_frame_sampler import selected_highlight_frame_budget


def test_candidate_fact_frame_budget_is_small() -> None:
    assert candidate_fact_frame_budget(0.0, 6.0) == 1
    assert candidate_fact_frame_budget(0.0, 20.0) == 2


def test_selected_highlight_frame_budget_is_richer_after_selection() -> None:
    assert selected_highlight_frame_budget(0.0, 8.0) == 2
    assert selected_highlight_frame_budget(0.0, 20.0) == 3
    assert selected_highlight_frame_budget(0.0, 45.0) == 5
    assert selected_highlight_frame_budget(0.0, 90.0) == 6


def test_sampling_times_are_deterministic() -> None:
    # Candidate fact stage is deliberately cheap.
    assert sample_times_for_candidate_fact(10.0, 20.0) == [13.3, 16.7]

    # A selected highlight of exactly 10 seconds still uses the short-segment
    # detail budget: two frames.
    assert sample_times_for_selected_highlight(10.0, 20.0) == [13.3, 16.7]

    # Once the selected highlight is longer than 10 seconds, detail sampling
    # uses three frames.
    assert sample_times_for_selected_highlight(10.0, 21.0) == [12.2, 15.5, 18.8]
