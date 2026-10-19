# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story.highlight_window_helpers

长视频拆短视频候选窗口的纯确定性 helper。

这个模块先作为“待引用”的功能函数集合存在：
- 不调用 LLM；
- 不读取/写入运行文件；
- 不 import 旧 native/legacy 实现；
- 不参与业务调度；
- 只做候选窗口校验、扩展、去重、分数合成和元数据合并。

后续拆 `highlight_edit_selection.py` 中的 `_build_peak_window_anchors`,
`_merge_clip_metadata`, `_peak_window_*_score` 时，应优先把无副作用逻辑迁移到这里。
"""

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


__CONTEXT__ = {
    "module": "app.services.movie_story.highlight_window_helpers",
    "purpose": "Pure deterministic helpers for highlight/short-video candidate windows.",
    "producers": [
        "timeline_runtime",
        "highlight_edit_candidates",
        "highlight_edit_selection",
    ],
    "consumers": [
        "highlight_edit_selection",
        "highlight_runtime",
        "highlight_edit_composition",
    ],
    "runtime_side_effects": "none",
    "legacy_boundary": "Does not import or call old movie_story native/legacy engines.",
}


@dataclass(frozen=True)
class HighlightWindow:
    """短视频候选窗口。

    字段：
    - start_seconds/end_seconds：候选窗口时间范围。
    - score：确定性候选分数，必须在 0..1。
    - source：候选来源，例如 timeline、peak-window、manual。
    """

    start_seconds: float
    end_seconds: float
    score: float
    source: str

    @property
    def duration_seconds(self) -> float:
        """返回候选窗口时长。"""

        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class WeightedScore:
    """加权分数结果。

    `parts` 保留归一化后的子分数，方便后续解释候选为什么被选中。
    """

    value: float
    parts: dict[str, float]


def clamp_score(value: float) -> float:
    """把确定性候选分数限制在 0..1。

    这个 helper 只做数值边界处理，不改变候选语义。
    """

    number = float(value)
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def build_highlight_window(
    *,
    start_seconds: float,
    end_seconds: float,
    score: float,
    source: str,
) -> HighlightWindow:
    """构造并校验短视频候选窗口。

    非法时间范围或空 source 直接报错；score 会被限制到 0..1。
    """

    start = float(start_seconds)
    end = float(end_seconds)
    if not source.strip():
        raise ValueError("highlight_window_source_required")
    if start < 0:
        raise ValueError(f"highlight_window_start_must_be_non_negative:{start_seconds}")
    if end <= start:
        raise ValueError(f"highlight_window_end_must_be_greater_than_start:{start_seconds}:{end_seconds}")
    return HighlightWindow(
        start_seconds=start,
        end_seconds=end,
        score=clamp_score(score),
        source=source.strip(),
    )


def expand_window_within_media(
    *,
    window: HighlightWindow,
    target_duration_seconds: float,
    media_duration_seconds: float,
) -> HighlightWindow:
    """围绕窗口中心扩展到目标时长，并限制在媒体范围内。

    该函数用于候选召回阶段的窗口扩展，不决定最终剪辑是否采用该窗口。
    """

    target_duration = float(target_duration_seconds)
    media_duration = float(media_duration_seconds)
    if target_duration <= 0:
        raise ValueError(f"target_duration_must_be_positive:{target_duration_seconds}")
    if media_duration <= 0:
        raise ValueError(f"media_duration_must_be_positive:{media_duration_seconds}")
    if target_duration > media_duration:
        raise ValueError(f"target_duration_exceeds_media_duration:{target_duration}:{media_duration}")
    if window.end_seconds > media_duration:
        raise ValueError(f"window_exceeds_media_duration:{window.end_seconds}:{media_duration}")

    if window.duration_seconds >= target_duration:
        return window

    center = (window.start_seconds + window.end_seconds) / 2.0
    start = center - target_duration / 2.0
    end = center + target_duration / 2.0

    if start < 0:
        end -= start
        start = 0.0
    if end > media_duration:
        start -= end - media_duration
        end = media_duration
    if start < 0 or end > media_duration or end <= start:
        raise ValueError(f"cannot_expand_highlight_window:{window}:{target_duration}:{media_duration}")

    return HighlightWindow(
        start_seconds=start,
        end_seconds=end,
        score=window.score,
        source=window.source,
    )


def window_overlap_seconds(left: HighlightWindow, right: HighlightWindow) -> float:
    """计算两个候选窗口重叠秒数。"""

    return max(0.0, min(left.end_seconds, right.end_seconds) - max(left.start_seconds, right.start_seconds))


def window_overlap_ratio(left: HighlightWindow, right: HighlightWindow) -> float:
    """计算两个候选窗口相对较短窗口的重叠比例。"""

    denominator = max(min(left.duration_seconds, right.duration_seconds), 1e-9)
    return window_overlap_seconds(left, right) / denominator


def dedupe_windows_by_overlap(
    *,
    windows: Sequence[HighlightWindow],
    max_overlap_ratio: float,
) -> tuple[HighlightWindow, ...]:
    """按分数从高到低去除重叠过高的候选窗口。

    该 helper 服务 `_build_peak_window_anchors` 后续拆分。它只做时间去重，
    不在本地解释剧情高潮或人物关系。
    """

    threshold = float(max_overlap_ratio)
    if threshold < 0 or threshold > 1:
        raise ValueError(f"max_overlap_ratio_must_be_between_0_and_1:{max_overlap_ratio}")

    selected: list[HighlightWindow] = []
    for window in sorted(windows, key=lambda item: (-item.score, item.start_seconds, item.end_seconds)):
        if any(window_overlap_ratio(window, chosen) > threshold for chosen in selected):
            continue
        selected.append(window)
    return tuple(sorted(selected, key=lambda item: (item.start_seconds, item.end_seconds)))


def normalize_score_parts(parts: Mapping[str, float]) -> dict[str, float]:
    """归一化候选子分数字典。

    key 必须非空，value 会被限制到 0..1。空 parts 直接报错，避免候选分数无来源。
    """

    if not parts:
        raise ValueError("score_parts_required")

    normalized: dict[str, float] = {}
    for key, value in parts.items():
        clean_key = str(key).strip()
        if not clean_key:
            raise ValueError("score_part_key_required")
        normalized[clean_key] = clamp_score(float(value))
    return normalized


def weighted_score(
    *,
    parts: Mapping[str, float],
    weights: Mapping[str, float],
) -> WeightedScore:
    """按权重合成候选分数。

    只使用同时存在于 parts 和 weights 的 key。权重必须非负且总和大于 0。
    """

    normalized_parts = normalize_score_parts(parts)
    weighted_total = 0.0
    weight_total = 0.0

    for key, part_value in normalized_parts.items():
        weight = float(weights.get(key, 0.0))
        if weight < 0:
            raise ValueError(f"score_weight_must_be_non_negative:{key}:{weight}")
        weighted_total += part_value * weight
        weight_total += weight

    if weight_total <= 0:
        raise ValueError("at_least_one_positive_score_weight_required")

    return WeightedScore(
        value=clamp_score(weighted_total / weight_total),
        parts=normalized_parts,
    )


def merge_clip_metadata(
    *,
    base: Mapping[str, object],
    overlay: Mapping[str, object],
    list_keys: Sequence[str] = (),
) -> dict[str, object]:
    """合并候选片段元数据。

    普通字段由 overlay 覆盖 base；list_keys 指定的字段会合并并去重。
    该 helper 用于后续拆 `_merge_clip_metadata`，不承担业务评分。
    """

    result: dict[str, object] = dict(base)
    for key, value in overlay.items():
        if key in list_keys:
            existing = result.get(key, [])
            if not isinstance(existing, list):
                existing = [existing]
            incoming = value if isinstance(value, list) else [value]
            merged: list[object] = []
            for item in [*existing, *incoming]:
                if item not in merged:
                    merged.append(item)
            result[key] = merged
            continue
        result[key] = value
    return result


def stable_window_id(*, prefix: str, window: HighlightWindow, index: int) -> str:
    """构造稳定候选窗口 ID。

    ID 只依赖前缀、时间范围和序号，避免绑定临时文件路径或运行目录。
    """

    clean_prefix = prefix.strip()
    if not clean_prefix:
        raise ValueError("window_id_prefix_required")
    if index < 0:
        raise ValueError(f"window_id_index_must_be_non_negative:{index}")
    return (
        f"{clean_prefix}_{index:03d}_"
        f"{window.start_seconds:.3f}_{window.end_seconds:.3f}"
    )


def highlight_window_to_dict(window: HighlightWindow) -> dict[str, float | str]:
    """把 HighlightWindow 转为可序列化字典。"""

    return asdict(window)
