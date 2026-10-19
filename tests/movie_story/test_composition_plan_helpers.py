# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.composition_plan_helpers import (
    TimeRange,
    allocate_durations_by_weights,
    build_composition_group_id,
    build_time_range,
    expand_range_to_min_duration,
    merge_time_ranges,
    split_duration_evenly,
    time_range_to_dict,
    validate_time_range_within_media,
)


def test_build_time_range_rejects_invalid_range() -> None:
    """时间段 helper 必须直接暴露非法输入。"""
    with pytest.raises(ValueError, match="end_must_be_greater"):
        build_time_range(start_seconds=10, end_seconds=10, source="unit")


def test_validate_time_range_within_media_rejects_overflow() -> None:
    """越界时间段不能自动截断，否则会掩盖上游时间轴错误。"""
    time_range = build_time_range(start_seconds=8, end_seconds=12, source="unit")

    with pytest.raises(ValueError, match="exceeds_media_duration"):
        validate_time_range_within_media(time_range=time_range, media_duration_seconds=10)


def test_expand_range_to_min_duration_keeps_media_bounds() -> None:
    """最小时长扩展应保持在媒体范围内。"""
    time_range = build_time_range(start_seconds=1, end_seconds=2, source="unit")

    expanded = expand_range_to_min_duration(
        time_range=time_range,
        min_duration_seconds=4,
        media_duration_seconds=10,
    )

    assert expanded.start_seconds == 0
    assert expanded.end_seconds == 4
    assert expanded.duration_seconds == 4


def test_split_duration_evenly_requires_enough_total_duration() -> None:
    """均分时长必须满足每个片段最小时长。"""
    with pytest.raises(ValueError, match="total_duration_too_short"):
        split_duration_evenly(
            total_duration_seconds=5,
            item_count=3,
            min_duration_seconds=2,
        )


def test_allocate_durations_by_weights_preserves_total() -> None:
    """权重分配应保持总时长不变并满足最小时长。"""
    allocation = allocate_durations_by_weights(
        total_duration_seconds=12,
        weights=(1, 3),
        min_duration_seconds=2,
    )

    assert allocation.durations_seconds == (4, 8)
    assert sum(allocation.durations_seconds) == allocation.total_duration_seconds


def test_allocate_durations_by_weights_rejects_zero_weight_sum() -> None:
    """权重不能全为 0，否则排序信号无意义。"""
    with pytest.raises(ValueError, match="at_least_one_weight"):
        allocate_durations_by_weights(
            total_duration_seconds=10,
            weights=(0, 0),
            min_duration_seconds=2,
        )


def test_merge_time_ranges_merges_close_ranges() -> None:
    """相邻时间段在 gap 内应合并，减少重复剪辑窗口。"""
    ranges = (
        TimeRange(start_seconds=0, end_seconds=3, source="a"),
        TimeRange(start_seconds=3.5, end_seconds=5, source="b"),
        TimeRange(start_seconds=10, end_seconds=12, source="c"),
    )

    merged = merge_time_ranges(ranges=ranges, max_gap_seconds=1, merged_source="merged")

    assert merged == (
        TimeRange(start_seconds=0, end_seconds=5, source="merged"),
        TimeRange(start_seconds=10, end_seconds=12, source="c"),
    )


def test_time_range_to_dict_uses_explicit_seconds_fields() -> None:
    """序列化字段应保留 seconds 后缀，避免单位歧义。"""
    payload = time_range_to_dict(TimeRange(start_seconds=1, end_seconds=2, source="unit"))

    assert payload == {"start_seconds": 1, "end_seconds": 2, "source": "unit"}


def test_build_composition_group_id_is_stable() -> None:
    """composition group ID 应只由稳定前缀和序号构造。"""
    assert build_composition_group_id(prefix="group", index=7) == "group_007"
