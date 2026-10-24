# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class FactSegment:
    """事实层输出：只描述事实，不直接写成最终解说。"""

    segment_id: str
    title: str
    summary: str
    time_range: str
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class NarrativeBeat:
    """节拍层输出：负责设计“怎么讲”，不属于最终定稿。"""

    beat_id: str
    phase: str
    hook: str
    content: str
    time_range: str
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class NarrationItem:
    """定稿层输出：最终脚本 item。"""

    item_id: str
    script_text: str
    time_range: str
    fact_ids: List[str] = field(default_factory=list)
    beat_ids: List[str] = field(default_factory=list)


@dataclass
class StageResult:
    """一个阶段结果对象，保留输入/输出和证据引用。"""

    stage: str
    status: str
    message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


__all__ = [
    "FactSegment",
    "NarrativeBeat",
    "NarrationItem",
    "StageResult",
    "to_dict",
    "item_time_range",
    "item_duration",
]


def to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        data = asdict(obj)
        if hasattr(obj, "duration"):
            data["duration"] = getattr(obj, "duration")
        return data
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, tuple):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        out = {k: to_dict(v) for k, v in obj.items()}
        if "duration" not in out:
            s, e = item_time_range(out)
            if s is not None and e is not None:
                out["duration"] = round(e - s, 3)
        return out
    return obj


def item_time_range(obj: Any) -> Tuple[Optional[float], Optional[float]]:
    data = asdict(obj) if is_dataclass(obj) else obj
    if not isinstance(data, dict):
        return None, None
    for sk, ek in [("video_start", "video_end"), ("start", "end"), ("evidence_start", "evidence_end")]:
        if data.get(sk) is not None and data.get(ek) is not None:
            try:
                s, e = float(data[sk]), float(data[ek])
                if e > s:
                    return s, e
            except Exception as _e:
                logger.debug("时间字段转 float 失败，跳过: {}", _e)
    return None, None


def item_duration(obj: Any) -> float:
    s, e = item_time_range(obj)
    return round(e - s, 3) if s is not None and e is not None else 0.0
