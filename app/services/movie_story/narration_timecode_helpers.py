# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story.narration_timecode_helpers

解说文案时间码与片段窗口的纯确定性 helper。

这个模块先作为“待引用”的功能函数集合存在：
- 不调用 LLM；
- 不改两轮提示词；
- 不读取/写入运行文件；
- 不 import 旧 native/legacy 实现；
- 不参与业务调度；
- 只做字符数估算、最小时长计算、时间窗口校验和扩展。

后续拆 `generate_narration_script.py`, `narrated_highlight_mapper.py`,
`composition_bridge.py` 或二轮文案时间码校验时，应优先复用这里的纯函数。
"""

from dataclasses import asdict, dataclass
from typing import Sequence


__CONTEXT__ = {
    "module": "app.services.movie_story.narration_timecode_helpers",
    "purpose": "Pure deterministic helpers for narration duration and timecode window planning.",
    "producers": [
        "two_round_narration",
        "two_round_visual_narration",
        "narration finalizer",
        "composition bridge",
    ],
    "consumers": [
        "future narration timecode validation",
        "composition planning",
        "highlight/narration mapper refactors",
    ],
    "runtime_side_effects": "none",
    "legacy_boundary": "Does not import or call old movie_story native/legacy engines.",
}


@dataclass(frozen=True)
class NarrationWindow:
    """解说片段时间窗口。

    字段：
    - start_seconds/end_seconds：秒级片段范围；
    - source：窗口来源，例如 round1-fact、story-segment、manual；
    - reason：选择或扩展该窗口的客观原因。
    """

    start_seconds: float
    end_seconds: float
    source: str
    reason: str

    @property
    def duration_seconds(self) -> float:
        """返回窗口时长。"""

        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class NarrationDurationEstimate:
    """文案所需时长估算结果。"""

    char_count: int
    chars_per_second: float
    estimated_seconds: float
    required_seconds: float


def count_cjk_aware_text_chars(text: str) -> int:
    """统计用于解说语速估算的字符数。

    去除所有空白字符，但保留中文、英文、数字和标点。
    这比简单 `len(text)` 更适合估算中文解说文案的最低时长。
    """

    return sum(1 for char in text if not char.isspace())


def estimate_narration_duration(
    *,
    text: str,
    chars_per_second: float = 4.0,
    min_seconds: float = 60.0,
) -> NarrationDurationEstimate:
    """估算文案片段需要的最低视频时长。

    默认沿用项目约定：字符数 / 4 得到基础秒数，再与 60 秒下限取最大值。
    这里仅做确定性数学计算，不修改提示词。
    """

    speed = float(chars_per_second)
    minimum = float(min_seconds)
    if speed <= 0:
        raise ValueError(f"chars_per_second_must_be_positive:{chars_per_second}")
    if minimum <= 0:
        raise ValueError(f"min_seconds_must_be_positive:{min_seconds}")

    char_count = count_cjk_aware_text_chars(text)
    estimated = char_count / speed
    required = max(estimated, minimum)
    return NarrationDurationEstimate(
        char_count=char_count,
        chars_per_second=speed,
        estimated_seconds=estimated,
        required_seconds=required,
    )


def build_narration_window(
    *,
    start_seconds: float,
    end_seconds: float,
    source: str,
    reason: str,
) -> NarrationWindow:
    """构造并校验解说时间窗口。

    非法时间范围、空 source 或空 reason 直接报错，避免后续合成阶段静默使用错误时间码。
    """

    start = float(start_seconds)
    end = float(end_seconds)
    if start < 0:
        raise ValueError(f"narration_window_start_must_be_non_negative:{start_seconds}")
    if end <= start:
        raise ValueError(f"narration_window_end_must_be_greater_than_start:{start_seconds}:{end_seconds}")
    if not source.strip():
        raise ValueError("narration_window_source_required")
    if not reason.strip():
        raise ValueError("narration_window_reason_required")
    return NarrationWindow(
        start_seconds=start,
        end_seconds=end,
        source=source.strip(),
        reason=reason.strip(),
    )


def validate_window_within_media(
    *,
    window: NarrationWindow,
    media_duration_seconds: float,
) -> NarrationWindow:
    """校验解说时间窗口不超过媒体范围。

    不自动截断，避免掩盖上游 round1 事实窗口或 composition plan 的时间轴错误。
    """

    media_duration = float(media_duration_seconds)
    if media_duration <= 0:
        raise ValueError(f"media_duration_must_be_positive:{media_duration_seconds}")
    if window.end_seconds > media_duration:
        raise ValueError(
            "narration_window_exceeds_media_duration:"
            f"{window.end_seconds}:{media_duration}:{window.source}"
        )
    return window


def expand_window_to_required_duration(
    *,
    window: NarrationWindow,
    required_seconds: float,
    media_duration_seconds: float,
) -> NarrationWindow:
    """把解说时间窗口扩展到所需时长，并限制在媒体范围内。

    扩展围绕原窗口中心点进行；如果媒体本身不足以容纳 required_seconds，直接报错。
    """

    required = float(required_seconds)
    media_duration = float(media_duration_seconds)
    if required <= 0:
        raise ValueError(f"required_seconds_must_be_positive:{required_seconds}")
    if media_duration <= 0:
        raise ValueError(f"media_duration_must_be_positive:{media_duration_seconds}")
    if required > media_duration:
        raise ValueError(f"required_seconds_exceeds_media_duration:{required}:{media_duration}")

    validate_window_within_media(window=window, media_duration_seconds=media_duration)

    if window.duration_seconds >= required:
        return window

    center = (window.start_seconds + window.end_seconds) / 2.0
    start = center - required / 2.0
    end = center + required / 2.0

    if start < 0:
        end -= start
        start = 0.0
    if end > media_duration:
        start -= end - media_duration
        end = media_duration
    if start < 0 or end > media_duration or end <= start:
        raise ValueError(f"cannot_expand_narration_window:{window}:{required}:{media_duration}")

    return NarrationWindow(
        start_seconds=start,
        end_seconds=end,
        source=window.source,
        reason=window.reason,
    )


def required_window_for_text(
    *,
    text: str,
    base_window: NarrationWindow,
    media_duration_seconds: float,
    chars_per_second: float = 4.0,
    min_seconds: float = 60.0,
) -> tuple[NarrationWindow, NarrationDurationEstimate]:
    """根据文案文本得到满足语速下限的时间窗口。

    返回扩展后的窗口和时长估算，方便调用方同时写入审计信息。
    """

    estimate = estimate_narration_duration(
        text=text,
        chars_per_second=chars_per_second,
        min_seconds=min_seconds,
    )
    expanded = expand_window_to_required_duration(
        window=base_window,
        required_seconds=estimate.required_seconds,
        media_duration_seconds=media_duration_seconds,
    )
    return expanded, estimate


def sort_windows_chronologically(windows: Sequence[NarrationWindow]) -> tuple[NarrationWindow, ...]:
    """按时间顺序排序解说窗口。

    这里只做确定性排序，不判断文案论证顺序是否合理。
    """

    return tuple(sorted(windows, key=lambda item: (item.start_seconds, item.end_seconds)))


def window_overlap_seconds(left: NarrationWindow, right: NarrationWindow) -> float:
    """计算两个解说窗口的重叠秒数。"""

    return max(0.0, min(left.end_seconds, right.end_seconds) - max(left.start_seconds, right.start_seconds))


def narration_window_to_dict(window: NarrationWindow) -> dict[str, float | str]:
    """把 NarrationWindow 转为可序列化字典。"""

    return asdict(window)


def duration_estimate_to_dict(estimate: NarrationDurationEstimate) -> dict[str, float | int]:
    """把 NarrationDurationEstimate 转为可序列化字典。"""

    return asdict(estimate)
