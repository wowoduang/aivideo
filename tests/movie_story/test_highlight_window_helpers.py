# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.highlight_window_helpers import (
    HighlightWindow,
    build_highlight_window,
    dedupe_windows_by_overlap,
    expand_window_within_media,
    highlight_window_to_dict,
    merge_clip_metadata,
    stable_window_id,
    weighted_score,
    window_overlap_ratio,
    window_overlap_seconds,
)


def test_build_highlight_window_validates_range_and_clamps_score() -> None:
    """候选窗口必须显式校验时间范围，并限制分数到 0..1。"""
    window = build_highlight_window(
        start_seconds=1,
        end_seconds=3,
        score=2,
        source="unit",
    )

    assert window.score == 1.0

    with pytest.raises(ValueError, match="end_must_be_greater"):
        build_highlight_window(start_seconds=3, end_seconds=1, score=0.5, source="unit")


def test_expand_window_within_media_keeps_bounds() -> None:
    """候选窗口扩展不能超出媒体边界。"""
    window = build_highlight_window(
        start_seconds=1,
        end_seconds=2,
        score=0.5,
        source="unit",
    )

    expanded = expand_window_within_media(
        window=window,
        target_duration_seconds=4,
        media_duration_seconds=10,
    )

    assert expanded == HighlightWindow(
        start_seconds=0,
        end_seconds=4,
        score=0.5,
        source="unit",
    )


def test_window_overlap_helpers() -> None:
    """窗口重叠 helper 使用较短窗口作为比例分母。"""
    left = HighlightWindow(start_seconds=0, end_seconds=10, score=0.5, source="a")
    right = HighlightWindow(start_seconds=5, end_seconds=9, score=0.5, source="b")

    assert window_overlap_seconds(left, right) == 4
    assert window_overlap_ratio(left, right) == 1


def test_dedupe_windows_by_overlap_keeps_highest_score() -> None:
    """高重叠候选应保留分数更高的窗口。"""
    windows = (
        HighlightWindow(start_seconds=0, end_seconds=10, score=0.3, source="a"),
        HighlightWindow(start_seconds=1, end_seconds=9, score=0.9, source="b"),
        HighlightWindow(start_seconds=20, end_seconds=30, score=0.5, source="c"),
    )

    selected = dedupe_windows_by_overlap(windows=windows, max_overlap_ratio=0.5)

    assert selected == (
        HighlightWindow(start_seconds=1, end_seconds=9, score=0.9, source="b"),
        HighlightWindow(start_seconds=20, end_seconds=30, score=0.5, source="c"),
    )


def test_weighted_score_uses_intersection_of_parts_and_weights() -> None:
    """加权分数只使用有权重的子分数。"""
    result = weighted_score(
        parts={"text": 0.2, "visual": 0.8, "unused": 1.0},
        weights={"text": 1.0, "visual": 3.0},
    )

    assert result.value == pytest.approx(0.65)
    assert result.parts["unused"] == 1.0


def test_weighted_score_rejects_missing_positive_weight() -> None:
    """没有正权重时不能产生候选总分。"""
    with pytest.raises(ValueError, match="positive_score_weight"):
        weighted_score(parts={"text": 0.2}, weights={"text": 0.0})


def test_merge_clip_metadata_merges_list_keys() -> None:
    """候选元数据合并应支持列表字段去重。"""
    merged = merge_clip_metadata(
        base={"tags": ["a"], "score": 1},
        overlay={"tags": ["a", "b"], "score": 2},
        list_keys=("tags",),
    )

    assert merged == {"tags": ["a", "b"], "score": 2}


def test_stable_window_id_is_deterministic() -> None:
    """候选窗口 ID 不能依赖临时文件路径。"""
    window = HighlightWindow(start_seconds=1, end_seconds=2.5, score=0.5, source="unit")

    assert stable_window_id(prefix="peak", window=window, index=3) == "peak_003_1.000_2.500"


def test_highlight_window_to_dict_is_serializable() -> None:
    """候选窗口序列化字段必须明确保留 seconds 单位。"""
    payload = highlight_window_to_dict(
        HighlightWindow(start_seconds=1, end_seconds=2, score=0.5, source="unit")
    )

    assert payload == {
        "start_seconds": 1,
        "end_seconds": 2,
        "score": 0.5,
        "source": "unit",
    }
