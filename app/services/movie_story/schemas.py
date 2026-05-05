# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SubtitleUnit:
    unit_id: str
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class SceneCandidate:
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
    nonstory_tag: Optional[str] = None
    need_semantic_review: bool = True

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class DraftStoryCandidate:
    candidate_id: str
    candidate_type: str
    video_start: float
    video_end: float
    children: List[str]
    subtitle_text: str
    merge_reason: List[str] = field(default_factory=list)
    boundary_confidence: str = "medium"
    need_semantic_review: bool = True

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class EvidenceSegment:
    candidate_id: str
    candidate_type: str
    video_start: float
    video_end: float
    evidence_start: Optional[float] = None
    evidence_end: Optional[float] = None
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
    source_candidate: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(max(0.0, self.video_end - self.video_start), 3)


@dataclass
class SelectedHighlight:
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
        return asdict(obj)
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def item_time_range(obj: Any):
    data = to_dict(obj)
    if not isinstance(data, dict):
        return None, None
    for sk, ek in [("video_start", "video_end"), ("start", "end"), ("evidence_start", "evidence_end")]:
        if data.get(sk) is not None and data.get(ek) is not None:
            try:
                s, e = float(data[sk]), float(data[ek])
                if e > s:
                    return s, e
            except Exception:
                pass
    return None, None


def item_duration(obj: Any) -> float:
    s, e = item_time_range(obj)
    return round(e - s, 3) if s is not None and e is not None else 0.0
