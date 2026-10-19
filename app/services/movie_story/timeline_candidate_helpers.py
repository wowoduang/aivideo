# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story.timeline_candidate_helpers

长视频拆短视频/视觉增强共用的时间轴候选纯 helper。

这个模块先作为“待引用”的功能函数集合存在：
- 不调用 LLM；
- 不读取/写入运行文件；
- 不 import 旧 native/legacy 实现；
- 不参与业务调度；
- 只做时间段校验、覆盖桶、候选去重、场景边界规范化和按分数选择。

后续拆 `timeline_runtime.py`, `direct_runtime_v11_consolidated.py`,
`highlight_edit_candidates.py` 时，应优先把无副作用时间轴候选逻辑迁移到这里。
"""

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


__CONTEXT__ = {
    "module": "app.services.movie_story.timeline_candidate_helpers",
    "purpose": "Pure deterministic helpers for timeline/scene candidate selection.",
    "producers": [
        "shot boundary detection",
        "scene boundary detection",
        "subtitle timing windows",
    ],
    "consumers": [
        "timeline_runtime",
        "visual_focus_segments",
        "highlight_edit_candidates",
        "highlight_edit_selection",
    ],
    "runtime_side_effects": "none",
    "legacy_boundary": "Does not import or call old movie_story native/legacy engines.",
}


@dataclass(frozen=True)
class TimelineCandidate:
    """时间轴候选片段。

    字段：
    - start_seconds/end_seconds：候选时间范围。
    - score：确定性候选分数，必须位于 0..1。
    - source：候选来源，例如 scene-boundary、shot-boundary、subtitle-window。
    - reason：候选被召回的客观原因，供审计和后续输入打包使用。
    """

    start_seconds: float
    end_seconds: float
    score: float
    source: str
    reason: str

    @property
    def duration_seconds(self) -> float:
        """返回候选片段时长。"""

        return self.end_seconds - self.start_seconds


def clamp_unit_score(value: float) -> float:
    """把候选分数限制在 0..1。"""

    number = float(value)
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def build_timeline_candidate(
    *,
    start_seconds: float,
    end_seconds: float,
    score: float,
    source: str,
    reason: str,
) -> TimelineCandidate:
    """构造并校验 TimelineCandidate。

    非法时间范围、空 source 或空 reason 都直接报错；score 会被限制到 0..1。
    该函数只做确定性结构校验，不解释剧情语义。
    """

    start = float(start_seconds)
    end = float(end_seconds)
    if start < 0:
        raise ValueError(f"timeline_candidate_start_must_be_non_negative:{start_seconds}")
    if end <= start:
        raise ValueError(f"timeline_candidate_end_must_be_greater_than_start:{start_seconds}:{end_seconds}")
    if not source.strip():
        raise ValueError("timeline_candidate_source_required")
    if not reason.strip():
        raise ValueError("timeline_candidate_reason_required")
    return TimelineCandidate(
        start_seconds=start,
        end_seconds=end,
        score=clamp_unit_score(score),
        source=source.strip(),
        reason=reason.strip(),
    )


def candidate_overlap_seconds(left: TimelineCandidate, right: TimelineCandidate) -> float:
    """计算两个时间轴候选的重叠秒数。"""

    return max(0.0, min(left.end_seconds, right.end_seconds) - max(left.start_seconds, right.start_seconds))


def candidate_overlap_ratio(left: TimelineCandidate, right: TimelineCandidate) -> float:
    """计算两个候选相对较短候选的重叠比例。"""

    denominator = max(min(left.duration_seconds, right.duration_seconds), 1e-9)
    return candidate_overlap_seconds(left, right) / denominator


def dedupe_timeline_candidates(
    *,
    candidates: Sequence[TimelineCandidate],
    max_overlap_ratio: float,
) -> tuple[TimelineCandidate, ...]:
    """按分数去除重叠过高的时间轴候选。

    该 helper 只做候选去重，不负责决定最终剪辑片段。
    """

    threshold = float(max_overlap_ratio)
    if threshold < 0 or threshold > 1:
        raise ValueError(f"max_overlap_ratio_must_be_between_0_and_1:{max_overlap_ratio}")

    selected: list[TimelineCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-item.score, item.start_seconds, item.end_seconds),
    ):
        if any(candidate_overlap_ratio(candidate, chosen) > threshold for chosen in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: (item.start_seconds, item.end_seconds)))


def coverage_bin_index(
    *,
    start_seconds: float,
    media_duration_seconds: float,
    bin_count: int,
) -> int:
    """把候选起点映射到粗粒度覆盖桶。

    覆盖桶用于保证候选分布在全片范围内，避免只集中在某个局部高潮。
    """

    duration = float(media_duration_seconds)
    if duration <= 0:
        raise ValueError(f"media_duration_must_be_positive:{media_duration_seconds}")
    if bin_count <= 0:
        raise ValueError(f"bin_count_must_be_positive:{bin_count}")
    start = max(0.0, min(float(start_seconds), duration))
    index = int((start / duration) * bin_count)
    return min(index, bin_count - 1)


def coverage_bins_for_candidates(
    *,
    candidates: Sequence[TimelineCandidate],
    media_duration_seconds: float,
    bin_count: int,
) -> tuple[int, ...]:
    """返回候选集合覆盖到的时间桶。"""

    return tuple(
        sorted(
            {
                coverage_bin_index(
                    start_seconds=candidate.start_seconds,
                    media_duration_seconds=media_duration_seconds,
                    bin_count=bin_count,
                )
                for candidate in candidates
            }
        )
    )


def coverage_ratio(
    *,
    candidates: Sequence[TimelineCandidate],
    media_duration_seconds: float,
    bin_count: int,
) -> float:
    """计算候选集合覆盖的时间桶比例。"""

    bins = coverage_bins_for_candidates(
        candidates=candidates,
        media_duration_seconds=media_duration_seconds,
        bin_count=bin_count,
    )
    return len(bins) / bin_count


def select_top_candidates_per_bin(
    *,
    candidates: Sequence[TimelineCandidate],
    media_duration_seconds: float,
    bin_count: int,
    per_bin: int,
) -> tuple[TimelineCandidate, ...]:
    """按时间桶选择每个桶内分数最高的候选。

    该 helper 服务 timeline/highlight 候选召回，保证全片覆盖；不做剧情解释。
    """

    if per_bin <= 0:
        raise ValueError(f"per_bin_must_be_positive:{per_bin}")

    buckets: dict[int, list[TimelineCandidate]] = {}
    for candidate in candidates:
        index = coverage_bin_index(
            start_seconds=candidate.start_seconds,
            media_duration_seconds=media_duration_seconds,
            bin_count=bin_count,
        )
        buckets.setdefault(index, []).append(candidate)

    selected: list[TimelineCandidate] = []
    for index in sorted(buckets):
        ranked = sorted(
            buckets[index],
            key=lambda item: (-item.score, item.start_seconds, item.end_seconds),
        )
        selected.extend(ranked[:per_bin])
    return tuple(sorted(selected, key=lambda item: (item.start_seconds, item.end_seconds)))


def normalize_scene_boundaries(
    *,
    boundaries: Iterable[tuple[float, float]],
    source: str,
    default_score: float,
) -> tuple[TimelineCandidate, ...]:
    """把场景边界元组转换成 TimelineCandidate。

    该转换只保留时间范围和来源，不加入剧情语义。
    """

    return tuple(
        build_timeline_candidate(
            start_seconds=start,
            end_seconds=end,
            score=default_score,
            source=source,
            reason="normalized_scene_boundary",
        )
        for start, end in boundaries
    )


def expand_candidate_window(
    *,
    candidate: TimelineCandidate,
    target_duration_seconds: float,
    media_duration_seconds: float,
) -> TimelineCandidate:
    """围绕候选中心扩展到目标时长，并限制在媒体范围内。"""

    target = float(target_duration_seconds)
    media_duration = float(media_duration_seconds)
    if target <= 0:
        raise ValueError(f"target_duration_must_be_positive:{target_duration_seconds}")
    if media_duration <= 0:
        raise ValueError(f"media_duration_must_be_positive:{media_duration_seconds}")
    if target > media_duration:
        raise ValueError(f"target_duration_exceeds_media_duration:{target}:{media_duration}")
    if candidate.end_seconds > media_duration:
        raise ValueError(f"candidate_exceeds_media_duration:{candidate.end_seconds}:{media_duration}")

    if candidate.duration_seconds >= target:
        return candidate

    center = (candidate.start_seconds + candidate.end_seconds) / 2.0
    start = center - target / 2.0
    end = center + target / 2.0

    if start < 0:
        end -= start
        start = 0.0
    if end > media_duration:
        start -= end - media_duration
        end = media_duration
    if start < 0 or end > media_duration or end <= start:
        raise ValueError(f"cannot_expand_timeline_candidate:{candidate}:{target}:{media_duration}")

    return TimelineCandidate(
        start_seconds=start,
        end_seconds=end,
        score=candidate.score,
        source=candidate.source,
        reason=candidate.reason,
    )


def timeline_candidate_to_dict(candidate: TimelineCandidate) -> dict[str, float | str]:
    """把 TimelineCandidate 转成可序列化字典。"""

    return asdict(candidate)
