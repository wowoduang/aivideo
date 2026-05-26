# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _range(item: Dict[str, Any]) -> Tuple[float | None, float | None]:
    for sk, ek in [("video_start", "video_end"), ("start", "end")]:
        try:
            if item.get(sk) is not None and item.get(ek) is not None:
                s, e = float(item[sk]), float(item[ek])
                return s, e
        except Exception:
            continue
    return None, None


def check_video_plan_quality(segments: Iterable[Dict[str, Any]], *, source_highlights: Iterable[Dict[str, Any]] | None = None,
                             allow_overlap_seconds: float = 0.2, min_segment_seconds: float = 1.0) -> Dict[str, Any]:
    """成片质量门禁：检查时间轴、空片段、重叠和 TTS 反向改视频时间回归。

    source_highlights 传入时，会检查最终片段 video_start/video_end 是否被脚本或 TTS 阶段偷偷改动。
    """
    items = [x for x in segments or [] if isinstance(x, dict)]
    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    normalized: List[Tuple[int, Dict[str, Any], float, float]] = []

    for idx, item in enumerate(items, start=1):
        s, e = _range(item)
        sid = item.get("segment_id") or item.get("highlight_id") or item.get("id") or idx
        if s is None or e is None:
            issues.append({"segment_id": sid, "code": "missing_time_range", "message": "片段缺少 video_start/video_end 或 start/end"})
            continue
        if e <= s:
            issues.append({"segment_id": sid, "code": "invalid_time_range", "message": "片段结束时间必须大于开始时间"})
            continue
        if e - s < min_segment_seconds:
            warnings.append({"segment_id": sid, "code": "too_short", "message": "片段过短，可能造成闪切"})
        if not str(item.get("text") or item.get("narration") or item.get("subtitle_text") or "").strip():
            warnings.append({"segment_id": sid, "code": "no_text_or_subtitle", "message": "片段缺少旁白或字幕文本，需确认是否保留原声/留白"})
        normalized.append((idx, item, s, e))

    normalized.sort(key=lambda x: (x[2], x[3]))
    for (_, a, _as, ae), (_, b, bs, _be) in zip(normalized, normalized[1:]):
        if ae > bs + allow_overlap_seconds:
            issues.append({
                "segment_id": b.get("segment_id") or b.get("highlight_id") or b.get("id"),
                "code": "overlap",
                "message": "片段时间轴存在明显重叠",
                "previous_segment_id": a.get("segment_id") or a.get("highlight_id") or a.get("id"),
            })

    source_by_id: Dict[str, Dict[str, Any]] = {}
    for h in source_highlights or []:
        if not isinstance(h, dict):
            continue
        key = str(h.get("segment_id") or h.get("highlight_id") or h.get("source_candidate_id") or h.get("candidate_id") or "")
        if key:
            source_by_id[key] = h
    if source_by_id:
        for item in items:
            key_candidates = [
                str(item.get("segment_id") or ""),
                str(item.get("highlight_id") or ""),
                str(item.get("source_candidate_id") or ""),
                str(item.get("candidate_id") or ""),
            ]
            source = next((source_by_id[k] for k in key_candidates if k and k in source_by_id), None)
            if not source:
                continue
            s1, e1 = _range(item)
            s0, e0 = _range(source)
            if s1 is None or e1 is None or s0 is None or e0 is None:
                continue
            if abs(s1 - s0) > 0.02 or abs(e1 - e0) > 0.02:
                issues.append({
                    "segment_id": item.get("segment_id") or item.get("highlight_id") or item.get("id"),
                    "code": "video_time_changed_after_selection",
                    "message": "最终片段时间与高光选择阶段不一致，疑似脚本/TTS 反向改动视频时间",
                    "expected": {"video_start": round(s0, 3), "video_end": round(e0, 3)},
                    "actual": {"video_start": round(s1, 3), "video_end": round(e1, 3)},
                })

    return {
        "passed": not issues,
        "issue_count": len(issues),
        "warning_count": len(warnings),
        "issues": issues,
        "warnings": warnings,
        "principles": {
            "retiming_guard": "tts_or_script_duration_must_not_modify_video_start_video_end",
            "quality_gate": "block_render_when_hard_issues_exist",
        },
    }
