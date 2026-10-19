# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story.composition_plan_helpers

长视频拆短视频/剪辑合成计划的确定性 helper。

这个模块先作为“待引用”的功能函数集合存在：
- 不调用 LLM；
- 不读取/写入运行文件；
- 不 import 旧 native/legacy 实现；
- 不参与业务调度；
- 只做时间段校验、时长分配、区间合并、ID 构造等纯确定性工作。

后续拆 `highlight_edit_composition.py` 或 `composition_bridge.py` 时，应优先把
无副作用的时间轴/时长/合成计划辅助逻辑迁移到这里，再由主流程引用。
"""

from dataclasses import asdict, dataclass
from typing import Sequence


__CONTEXT__ = {
    "module": "app.services.movie_story.composition_plan_helpers",
    "purpose": "Pure deterministic helpers for long-video-to-shorts composition planning.",
    "producers": [
        "highlight_edit_selection",
        "timeline_runtime",
        "composition_bridge",
    ],
    "consumers": [
        "highlight_edit_composition",
        "video export pipeline",
        "future composition refactors",
    ],
    "runtime_side_effects": "none",
    "legacy_boundary": "Does not import or call old movie_story native/legacy engines.",
}


@dataclass(frozen=True)
class TimeRange:
    """稳定的秒级时间段结构。

    字段：
    - start_seconds/end_seconds：闭开区间的秒级边界。
    - source：时间段来源，方便后续追踪是 timeline、highlight 还是手动选择。
    """

    start_seconds: float
    end_seconds: float
    source: str

    @property
    def duration_seconds(self) -> float:
        """返回时间段时长。"""

        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class DurationAllocation:
    """一次剪辑时长分配结果。

    `durations_seconds` 的顺序必须与调用方传入的候选片段顺序一致。
    """

    total_duration_seconds: float
    durations_seconds: tuple[float, ...]


def require_positive_seconds(value: float, *, field_name: str) -> float:
    """校验正秒数并返回 float。

    这是剪辑计划 helper 的基础入口。非法值直接报错，不做静默修正，
    让调用方尽早暴露错误输入。
    """

    seconds = float(value)
    if seconds <= 0:
        raise ValueError(f"{field_name}_must_be_positive_seconds:{value}")
    return seconds


def build_time_range(*, start_seconds: float, end_seconds: float, source: str) -> TimeRange:
    """构造并校验 TimeRange。

    只接受 `end_seconds > start_seconds` 的有效区间；source 必须非空，
    用于后续审计该时间段由哪个模块生产。
    """

    start = float(start_seconds)
    end = float(end_seconds)
    if not source.strip():
        raise ValueError("time_range_source_required")
    if start < 0:
        raise ValueError(f"time_range_start_must_be_non_negative:{start_seconds}")
    if end <= start:
        raise ValueError(f"time_range_end_must_be_greater_than_start:{start_seconds}:{end_seconds}")
    return TimeRange(start_seconds=start, end_seconds=end, source=source.strip())


def validate_time_range_within_media(
    *,
    time_range: TimeRange,
    media_duration_seconds: float,
) -> TimeRange:
    """校验时间段位于媒体时长内部。

    该函数不自动截断越界时间，因为自动截断会掩盖上游时间轴错误；
    如果上游给出越界时间，应由调用方修正生产者。
    """

    duration = require_positive_seconds(media_duration_seconds, field_name="media_duration")
    if time_range.end_seconds > duration:
        raise ValueError(
            "time_range_exceeds_media_duration:"
            f"{time_range.end_seconds}:{duration}:{time_range.source}"
        )
    return time_range


def expand_range_to_min_duration(
    *,
    time_range: TimeRange,
    min_duration_seconds: float,
    media_duration_seconds: float,
) -> TimeRange:
    """把时间段扩展到最小时长。

    扩展是确定性操作：优先围绕原始中心点两侧扩展，并严格限制在媒体时长内。
    如果媒体本身不足以容纳最小时长，直接报错。
    """

    minimum = require_positive_seconds(min_duration_seconds, field_name="min_duration")
    media_duration = require_positive_seconds(media_duration_seconds, field_name="media_duration")
    validate_time_range_within_media(time_range=time_range, media_duration_seconds=media_duration)

    if minimum > media_duration:
        raise ValueError(f"min_duration_exceeds_media_duration:{minimum}:{media_duration}")
    if time_range.duration_seconds >= minimum:
        return time_range

    center = (time_range.start_seconds + time_range.end_seconds) / 2.0
    start = center - minimum / 2.0
    end = center + minimum / 2.0

    if start < 0:
        end -= start
        start = 0.0
    if end > media_duration:
        start -= end - media_duration
        end = media_duration
    if start < 0 or end > media_duration or end <= start:
        raise ValueError(f"cannot_expand_time_range:{time_range}:{minimum}:{media_duration}")

    return TimeRange(start_seconds=start, end_seconds=end, source=time_range.source)


def split_duration_evenly(
    *,
    total_duration_seconds: float,
    item_count: int,
    min_duration_seconds: float,
) -> DurationAllocation:
    """把总时长均分给固定数量的片段。

    如果总时长不足以满足每个片段的最小时长，直接报错。
    该函数用于后续把 `_plan_group_shot_durations` 里的确定性分配逻辑拆出来。
    """

    total = require_positive_seconds(total_duration_seconds, field_name="total_duration")
    minimum = require_positive_seconds(min_duration_seconds, field_name="min_duration")
    if item_count <= 0:
        raise ValueError(f"item_count_must_be_positive:{item_count}")
    if total < item_count * minimum:
        raise ValueError(f"total_duration_too_short:{total}:{item_count}:{minimum}")

    per_item = total / item_count
    return DurationAllocation(
        total_duration_seconds=total,
        durations_seconds=tuple(per_item for _ in range(item_count)),
    )


def allocate_durations_by_weights(
    *,
    total_duration_seconds: float,
    weights: Sequence[float],
    min_duration_seconds: float,
) -> DurationAllocation:
    """按权重分配总时长，同时保证每个片段有最小时长。

    权重必须非负，且至少一个权重大于 0。该函数只做确定性时长分配，
    不决定候选片段是否应该入选。
    """

    total = require_positive_seconds(total_duration_seconds, field_name="total_duration")
    minimum = require_positive_seconds(min_duration_seconds, field_name="min_duration")
    normalized_weights = tuple(float(weight) for weight in weights)
    if not normalized_weights:
        raise ValueError("weights_required")
    if any(weight < 0 for weight in normalized_weights):
        raise ValueError(f"weights_must_be_non_negative:{normalized_weights}")

    base_total = len(normalized_weights) * minimum
    if total < base_total:
        raise ValueError(f"total_duration_too_short:{total}:{len(normalized_weights)}:{minimum}")

    weight_total = sum(normalized_weights)
    if weight_total <= 0:
        raise ValueError("at_least_one_weight_must_be_positive")

    remaining = total - base_total
    durations = tuple(
        minimum + remaining * (weight / weight_total)
        for weight in normalized_weights
    )
    return DurationAllocation(total_duration_seconds=total, durations_seconds=durations)


def merge_time_ranges(
    *,
    ranges: Sequence[TimeRange],
    max_gap_seconds: float,
    merged_source: str,
) -> tuple[TimeRange, ...]:
    """合并重叠或间隔足够近的时间段。

    该 helper 服务高光片段去重和剪辑窗口连续性处理。它只处理时间区间，
    不改变候选的叙事含义。
    """

    if not merged_source.strip():
        raise ValueError("merged_source_required")
    gap = float(max_gap_seconds)
    if gap < 0:
        raise ValueError(f"max_gap_must_be_non_negative:{max_gap_seconds}")
    if not ranges:
        return tuple()

    ordered = sorted(ranges, key=lambda item: (item.start_seconds, item.end_seconds))
    merged: list[TimeRange] = []
    current = ordered[0]

    for item in ordered[1:]:
        if item.start_seconds <= current.end_seconds + gap:
            current = TimeRange(
                start_seconds=current.start_seconds,
                end_seconds=max(current.end_seconds, item.end_seconds),
                source=merged_source.strip(),
            )
            continue
        merged.append(current)
        current = item

    merged.append(current)
    return tuple(merged)


def time_range_to_dict(time_range: TimeRange) -> dict[str, float | str]:
    """把 TimeRange 转为可序列化字典。

    输出字段使用明确秒数命名，避免后续 composition plan 中 start/end 单位不清。
    """

    return asdict(time_range)


def build_composition_group_id(*, prefix: str, index: int) -> str:
    """构造稳定的 composition group ID。

    group ID 是剪辑计划内部引用，不应依赖数据库自增或临时文件路径。
    """

    normalized_prefix = prefix.strip()
    if not normalized_prefix:
        raise ValueError("composition_group_prefix_required")
    if index < 0:
        raise ValueError(f"composition_group_index_must_be_non_negative:{index}")
    return f"{normalized_prefix}_{index:03d}"
