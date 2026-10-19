# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from app.services.movie_story.narration_timecode_helpers import (
    NarrationWindow,
    build_narration_window,
    count_cjk_aware_text_chars,
    duration_estimate_to_dict,
    estimate_narration_duration,
    expand_window_to_required_duration,
    narration_window_to_dict,
    required_window_for_text,
    sort_windows_chronologically,
    validate_window_within_media,
    window_overlap_seconds,
)


def test_count_cjk_aware_text_chars_ignores_whitespace() -> None:
    """字符计数应忽略换行和空格。"""
    assert count_cjk_aware_text_chars("你 好\nworld") == 7


def test_estimate_narration_duration_uses_project_default_floor() -> None:
    """默认按字符/4，并与 60 秒下限取最大值。"""
    estimate = estimate_narration_duration(text="一" * 100)

    assert estimate.char_count == 100
    assert estimate.estimated_seconds == 25
    assert estimate.required_seconds == 60


def test_estimate_narration_duration_can_exceed_floor() -> None:
    """长文案所需时长可以超过 60 秒下限。"""
    estimate = estimate_narration_duration(text="一" * 400)

    assert estimate.estimated_seconds == 100
    assert estimate.required_seconds == 100


def test_build_narration_window_rejects_invalid_range() -> None:
    """非法时间窗口必须直接报错。"""
    with pytest.raises(ValueError, match="end_must_be_greater"):
        build_narration_window(start_seconds=2, end_seconds=2, source="round1", reason="unit")


def test_validate_window_within_media_rejects_overflow() -> None:
    """越界窗口不能自动截断。"""
    window = build_narration_window(start_seconds=8, end_seconds=12, source="round1", reason="unit")

    with pytest.raises(ValueError, match="exceeds_media_duration"):
        validate_window_within_media(window=window, media_duration_seconds=10)


def test_expand_window_to_required_duration_keeps_media_bounds() -> None:
    """窗口扩展应围绕中心点并保持在媒体边界内。"""
    window = build_narration_window(start_seconds=1, end_seconds=2, source="round1", reason="unit")

    expanded = expand_window_to_required_duration(
        window=window,
        required_seconds=4,
        media_duration_seconds=10,
    )

    assert expanded == NarrationWindow(
        start_seconds=0,
        end_seconds=4,
        source="round1",
        reason="unit",
    )


def test_required_window_for_text_returns_window_and_estimate() -> None:
    """根据文案计算所需窗口时，应同时返回审计用估算结果。"""
    window = build_narration_window(start_seconds=20, end_seconds=30, source="round1", reason="unit")

    expanded, estimate = required_window_for_text(
        text="一" * 100,
        base_window=window,
        media_duration_seconds=120,
    )

    assert estimate.required_seconds == 60
    assert expanded.duration_seconds == 60


def test_sort_windows_chronologically_orders_by_time() -> None:
    """时间窗口排序只按时间，不判断论证顺序。"""
    later = NarrationWindow(start_seconds=20, end_seconds=30, source="a", reason="x")
    earlier = NarrationWindow(start_seconds=1, end_seconds=2, source="b", reason="y")

    assert sort_windows_chronologically((later, earlier)) == (earlier, later)


def test_window_overlap_seconds() -> None:
    """重叠秒数用于后续时间码冲突检测。"""
    left = NarrationWindow(start_seconds=0, end_seconds=10, source="a", reason="x")
    right = NarrationWindow(start_seconds=5, end_seconds=12, source="b", reason="y")

    assert window_overlap_seconds(left, right) == 5


def test_serializers_use_explicit_fields() -> None:
    """序列化结果应保留明确字段名，方便写入审计信息。"""
    window = NarrationWindow(start_seconds=1, end_seconds=2, source="a", reason="x")
    estimate = estimate_narration_duration(text="一" * 4, min_seconds=1)

    assert narration_window_to_dict(window) == {
        "start_seconds": 1,
        "end_seconds": 2,
        "source": "a",
        "reason": "x",
    }
    assert duration_estimate_to_dict(estimate) == {
        "char_count": 4,
        "chars_per_second": 4.0,
        "estimated_seconds": 1.0,
        "required_seconds": 1.0,
    }
