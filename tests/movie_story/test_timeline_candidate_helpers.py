# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.timeline_candidate_helpers import (
    TimelineCandidate,
    build_timeline_candidate,
    candidate_overlap_ratio,
    candidate_overlap_seconds,
    coverage_bin_index,
    coverage_bins_for_candidates,
    coverage_ratio,
    dedupe_timeline_candidates,
    expand_candidate_window,
    normalize_scene_boundaries,
    select_top_candidates_per_bin,
    timeline_candidate_to_dict,
)


def test_build_timeline_candidate_validates_required_fields() -> None:
    """候选构造必须直接暴露非法时间范围。"""
    with pytest.raises(ValueError, match="end_must_be_greater"):
        build_timeline_candidate(
            start_seconds=3,
            end_seconds=1,
            score=0.5,
            source="scene",
            reason="unit",
        )


def test_candidate_overlap_helpers_use_shorter_candidate_denominator() -> None:
    """重叠比例使用较短候选作为分母。"""
    left = TimelineCandidate(start_seconds=0, end_seconds=10, score=0.5, source="a", reason="x")
    right = TimelineCandidate(start_seconds=5, end_seconds=9, score=0.5, source="b", reason="y")

    assert candidate_overlap_seconds(left, right) == 4
    assert candidate_overlap_ratio(left, right) == 1


def test_dedupe_timeline_candidates_keeps_highest_score() -> None:
    """高重叠候选应保留分数更高的候选。"""
    candidates = (
        TimelineCandidate(start_seconds=0, end_seconds=10, score=0.2, source="a", reason="x"),
        TimelineCandidate(start_seconds=1, end_seconds=9, score=0.8, source="b", reason="y"),
        TimelineCandidate(start_seconds=20, end_seconds=25, score=0.4, source="c", reason="z"),
    )

    selected = dedupe_timeline_candidates(candidates=candidates, max_overlap_ratio=0.5)

    assert selected == (
        TimelineCandidate(start_seconds=1, end_seconds=9, score=0.8, source="b", reason="y"),
        TimelineCandidate(start_seconds=20, end_seconds=25, score=0.4, source="c", reason="z"),
    )


def test_coverage_bin_index_clamps_to_last_bin() -> None:
    """媒体末尾时间点应落入最后一个覆盖桶。"""
    assert coverage_bin_index(start_seconds=100, media_duration_seconds=100, bin_count=5) == 4


def test_coverage_ratio_counts_unique_bins() -> None:
    """覆盖率按唯一时间桶计算。"""
    candidates = (
        TimelineCandidate(start_seconds=0, end_seconds=1, score=0.5, source="a", reason="x"),
        TimelineCandidate(start_seconds=5, end_seconds=6, score=0.5, source="b", reason="y"),
        TimelineCandidate(start_seconds=90, end_seconds=95, score=0.5, source="c", reason="z"),
    )

    assert coverage_bins_for_candidates(
        candidates=candidates,
        media_duration_seconds=100,
        bin_count=10,
    ) == (0, 9)
    assert coverage_ratio(
        candidates=candidates,
        media_duration_seconds=100,
        bin_count=10,
    ) == 0.2


def test_select_top_candidates_per_bin_keeps_best_in_each_bin() -> None:
    """每个时间桶只选择分数最高的候选。"""
    candidates = (
        TimelineCandidate(start_seconds=0, end_seconds=1, score=0.1, source="a", reason="x"),
        TimelineCandidate(start_seconds=2, end_seconds=3, score=0.9, source="b", reason="y"),
        TimelineCandidate(start_seconds=50, end_seconds=55, score=0.4, source="c", reason="z"),
    )

    selected = select_top_candidates_per_bin(
        candidates=candidates,
        media_duration_seconds=100,
        bin_count=2,
        per_bin=1,
    )

    assert selected == (
        TimelineCandidate(start_seconds=2, end_seconds=3, score=0.9, source="b", reason="y"),
        TimelineCandidate(start_seconds=50, end_seconds=55, score=0.4, source="c", reason="z"),
    )


def test_normalize_scene_boundaries_builds_candidates_without_semantic_reasoning() -> None:
    """场景边界规范化只保留时间与来源，不引入剧情解释。"""
    candidates = normalize_scene_boundaries(
        boundaries=((0, 10), (20, 30)),
        source="scene",
        default_score=0.6,
    )

    assert candidates[0].reason == "normalized_scene_boundary"
    assert candidates[1].score == 0.6


def test_expand_candidate_window_keeps_media_bounds() -> None:
    """候选扩展必须限制在媒体时长内。"""
    candidate = TimelineCandidate(start_seconds=1, end_seconds=2, score=0.5, source="a", reason="x")

    expanded = expand_candidate_window(
        candidate=candidate,
        target_duration_seconds=4,
        media_duration_seconds=10,
    )

    assert expanded == TimelineCandidate(
        start_seconds=0,
        end_seconds=4,
        score=0.5,
        source="a",
        reason="x",
    )


def test_timeline_candidate_to_dict_is_serializable() -> None:
    """序列化字段必须保留 seconds 单位。"""
    payload = timeline_candidate_to_dict(
        TimelineCandidate(start_seconds=1, end_seconds=2, score=0.5, source="a", reason="x")
    )

    assert payload == {
        "start_seconds": 1,
        "end_seconds": 2,
        "score": 0.5,
        "source": "a",
        "reason": "x",
    }
