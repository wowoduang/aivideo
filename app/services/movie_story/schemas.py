# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SubtitleUnit:
    unit_id: str
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end - self.start), 3)


@dataclass
class SceneCandidate:
    """第一阶段细粒度候选片段。

    这里刻意只保存结构切片信息，不出现 highlight_score / selected 等
    第三阶段才应该产生的字段。
    """

    candidate_id: str
    candidate_type: str
    video_start: float
    video_end: float
    subtitle_start: Optional[float] = None
    subtitle_end: Optional[float] = None
    subtitle_text: str = ""
    boundary_start_reason: List[str] = field(default_factory=list)
    boundary_end_reason: List[str] = field(default_factory=list)
    boundary_confidence: str = "medium"
    source_scene_ids: List[str] = field(default_factory=list)
    nonstory_tag: Optional[str] = None
    need_semantic_review: bool = True

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class DraftStoryCandidate:
    """第一阶段粗粒度故事候选块。

    它只是初步合并结果，不代表最终高光，不允许在这里做目标时长压缩。
    """

    candidate_id: str
    candidate_type: str
    video_start: float
    video_end: float
    children: List[str]
    subtitle_text: str
    merge_reason: List[str] = field(default_factory=list)
    boundary_confidence: str = "medium"
    need_semantic_review: bool = True
    nonstory_tag: Optional[str] = None

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class EvidenceSegment:
    """第二阶段证据增强后的候选。

    第二阶段只补证据和标签；弱片段只能打 drop_suggestion，不从列表中删除。
    """

    candidate_id: str
    candidate_type: str
    video_start: float
    video_end: float
    evidence_start: Optional[float] = None
    evidence_end: Optional[float] = None
    semantic_start: Optional[float] = None
    semantic_end: Optional[float] = None
    subtitle_text: str = ""
    visual_evidence: Dict[str, Any] = field(default_factory=dict)
    character_trace: Dict[str, Any] = field(default_factory=dict)
    plot_function: str = ""
    importance_level: str = "medium"
    emotion_tags: List[str] = field(default_factory=list)
    information_tags: List[str] = field(default_factory=list)
    raw_voice_suggestion: bool = False
    drop_suggestion: bool = False
    drop_reason: str = ""
    split_merge_suggestion: Dict[str, Any] = field(default_factory=dict)
    evidence_warnings: List[str] = field(default_factory=list)
    source_candidate: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class SelectedHighlight:
    """第三阶段最终选中高光。

    注意：video_start/video_end 必须原样继承候选，不能被 TTS 或脚本长度反向修改。
    """

    highlight_id: str
    source_candidate_id: str
    video_start: float
    video_end: float
    evidence_start: Optional[float]
    evidence_end: Optional[float]
    selected: bool
    selection_mode: str
    scores: Dict[str, float]
    selection_reasons: List[str]
    character_trace: Dict[str, Any]
    keep_original_audio: bool = False
    highlight_rank: int = 0
    source_segment: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


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
