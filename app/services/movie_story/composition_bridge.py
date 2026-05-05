from __future__ import annotations

"""Bridge movie-story narration output into a unified CompositionPlan.

Stage-M module.

The old movie-story/subtitle-first chain produces script_items first.  The new
highlight-edit chain produces a CompositionPlan first and derives script_items
from it.  This bridge lets the movie-story chain join the same output contract
without rewriting its mature narration generator.

Design rules:
- Preserve script-item timings as the authoritative video timeline.
- Do not let TTS length re-cut video windows.
- Keep raw/ducked/tts audio intent explicit through audio_mode.
- Carry movie-story evidence ids and validation metadata for audit/UI/debugging.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _non_empty_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _stable_id(value: Any) -> str:
    return str(value or "").strip()


def _listify(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _string_list(value: Any) -> List[str]:
    result: List[str] = []
    for item in _listify(value):
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _index_by_ids(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        keys = [
            row.get("highlight_id"),
            row.get("scene_id"),
            row.get("segment_id"),
            row.get("source_scene_id"),
            row.get("source_clip_id"),
        ]
        for key in keys:
            text = _stable_id(key)
            if text and text not in index:
                index[text] = row
    return index


def _match_evidence_for_script_item(
    item: Dict[str, Any],
    *,
    evidence_index: Dict[str, Dict[str, Any]],
    highlight_index: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return best evidence/highlight pair for a script item.

    We first use explicit ids.  If ids are absent, use simple time overlap so
    legacy script items can still be bridged.
    """
    keys = [
        item.get("highlight_id"),
        item.get("scene_id"),
        item.get("segment_id"),
        item.get("source_scene_id"),
        item.get("source_clip_id"),
    ]
    for key in keys:
        text = _stable_id(key)
        if text and text in evidence_index:
            evidence = evidence_index[text]
            return evidence, highlight_index.get(text, {})
        if text and text in highlight_index:
            highlight = highlight_index[text]
            highlight_key = _stable_id(highlight.get("highlight_id") or highlight.get("scene_id") or highlight.get("segment_id"))
            return evidence_index.get(highlight_key, {}), highlight

    item_start = _as_float(item.get("start"), 0.0)
    item_end = _as_float(item.get("end"), item_start)
    best_evidence: Dict[str, Any] = {}
    best_overlap = 0.0
    for evidence in evidence_index.values():
        start = _as_float(evidence.get("start"), 0.0)
        end = _as_float(evidence.get("end"), start)
        overlap = max(0.0, min(item_end, end) - max(item_start, start))
        if overlap > best_overlap:
            best_evidence = evidence
            best_overlap = overlap

    best_highlight: Dict[str, Any] = {}
    best_overlap = 0.0
    for highlight in highlight_index.values():
        start = _as_float(highlight.get("start"), 0.0)
        end = _as_float(highlight.get("end"), start)
        overlap = max(0.0, min(item_end, end) - max(item_start, start))
        if overlap > best_overlap:
            best_highlight = highlight
            best_overlap = overlap

    return best_evidence, best_highlight


def _audio_mode_from_script_item(item: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    explicit = str(item.get("composition_audio_mode") or "").strip().lower()
    if explicit in {"raw", "ducked_raw", "tts", "mute"}:
        return explicit

    narration = str(item.get("narration") or item.get("narration_text") or "").strip()
    ost = item.get("OST")
    raw_keep = bool(
        item.get("llm_raw_voice_keep")
        or item.get("raw_voice_retain_suggestion")
        or evidence.get("raw_voice")
        or evidence.get("raw_audio_worthy")
    )

    if ost == 1 or (not narration and raw_keep):
        return "raw"
    if ost == 0:
        return "mute" if not narration else "tts"
    if raw_keep and narration:
        return "ducked_raw"
    if narration:
        return "tts"
    return "raw"


def _selection_reasons(item: Dict[str, Any], evidence: Dict[str, Any], highlight: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for source in (
        item.get("highlight_reasons"),
        item.get("selection_reason"),
        evidence.get("selection_reason"),
        evidence.get("highlight_reasons"),
        highlight.get("selection_reason"),
        highlight.get("reasons"),
    ):
        reasons.extend(_string_list(source))
    if evidence.get("plot_function"):
        reasons.append(f"plot:{evidence.get('plot_function')}")
    if highlight.get("highlight_type"):
        reasons.append(f"type:{highlight.get('highlight_type')}")
    return list(dict.fromkeys(str(reason) for reason in reasons if str(reason).strip()))


def _build_picture(item: Dict[str, Any], evidence: Dict[str, Any], highlight: Dict[str, Any], idx: int) -> str:
    visual_summary = evidence.get("visual_summary")
    if isinstance(visual_summary, list) and visual_summary:
        first = visual_summary[0]
        if isinstance(first, dict):
            desc = _non_empty_string(first.get("desc"), first.get("description"), first.get("caption"))
            if desc:
                return desc[:100]
        text = _non_empty_string(first)
        if text:
            return text[:100]

    return _non_empty_string(
        item.get("picture"),
        item.get("scene_summary"),
        evidence.get("visual_summary_text"),
        evidence.get("scene_summary"),
        evidence.get("subtitle_text"),
        highlight.get("summary"),
        item.get("narration"),
        f"影视解说片段 {idx}",
    )[:100]


def build_movie_story_composition_plan(
    *,
    video_path: str,
    movie_title: str = "",
    target_duration_seconds: int = 0,
    script_items: List[Dict[str, Any]],
    narration_evidence: Optional[List[Dict[str, Any]]] = None,
    story_highlights: Optional[List[Dict[str, Any]]] = None,
    narration_audio_path: str = "",
    visual_mode: str = "",
    generation_mode: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a CompositionPlan from finalized movie-story script items."""
    evidence_rows = list(narration_evidence or [])
    highlight_rows = list(story_highlights or [])
    evidence_index = _index_by_ids(evidence_rows)
    highlight_index = _index_by_ids(highlight_rows)

    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for idx, item in enumerate(script_items or [], start=1):
        if not isinstance(item, dict):
            continue
        start = _as_float(item.get("start"), 0.0)
        end = _as_float(item.get("end"), start)
        if end <= start:
            duration = _as_float(item.get("duration"), 0.0)
            end = start + max(duration, 0.5)
        duration = max(end - start, 0.5)
        evidence, highlight = _match_evidence_for_script_item(
            item,
            evidence_index=evidence_index,
            highlight_index=highlight_index,
        )
        audio_mode = _audio_mode_from_script_item(item, evidence)
        narration_text = _non_empty_string(item.get("narration"), item.get("narration_text"))
        if audio_mode in {"raw", "mute"}:
            # Raw-only or silent segments should not accidentally carry TTS text.
            carry_text = narration_text if audio_mode == "mute" and narration_text else ""
        else:
            carry_text = narration_text

        source_id = _non_empty_string(
            item.get("highlight_id"),
            item.get("scene_id"),
            item.get("segment_id"),
            evidence.get("highlight_id"),
            evidence.get("scene_id"),
            evidence.get("segment_id"),
            f"movie_story_clip_{idx:04d}",
        )
        reasons = _selection_reasons(item, evidence, highlight)
        if audio_mode:
            reasons.append(f"audio:{audio_mode}")

        segment = {
            "segment_id": f"movie_story_seg_{idx:04d}",
            "video_start": round(start, 3),
            "video_end": round(end, 3),
            "timeline_start": round(cursor, 3),
            "timeline_end": round(cursor + duration, 3),
            "audio_mode": audio_mode,
            "narration_text": carry_text,
            "narration_audio_path": narration_audio_path if carry_text else "",
            "selection_reason": list(dict.fromkeys(reasons)),
            "picture": _build_picture(item, evidence, highlight, idx),
            "audio_strategy": _non_empty_string(item.get("audio_strategy"), evidence.get("audio_strategy"), audio_mode),
            "source_clip_id": source_id,
            "clip_source": "hybrid",
            "source_scene_id": _non_empty_string(evidence.get("scene_id"), item.get("scene_id"), source_id),
            "raw_audio_worthy": bool(
                item.get("llm_raw_voice_keep")
                or item.get("raw_voice_retain_suggestion")
                or evidence.get("raw_voice")
                or evidence.get("raw_audio_worthy")
            ),
            "trim_strategy": _non_empty_string(item.get("trim_strategy"), "movie_story_semantic_window"),
            "original_duration": round(_as_float(item.get("duration"), duration) or duration, 3),
            "planned_duration": round(duration, 3),
            "match_strategy": "movie_story_script_item",
            "movie_story_validation": dict(item.get("movie_story_validation") or {}),
            "semantic_start": item.get("semantic_start", evidence.get("semantic_start")),
            "semantic_end": item.get("semantic_end", evidence.get("semantic_end")),
            "story_highlight_type": highlight.get("highlight_type") or evidence.get("highlight_type"),
        }
        segments.append(segment)
        cursor += duration

    plan_metadata = {
        "source_pipeline": "movie_story_native_engine",
        "composition_bridge_stage": "stage_m",
        "selected_clip_count": len(segments),
        "script_item_count": len(script_items or []),
        "narration_evidence_count": len(evidence_rows),
        "story_highlight_count": len(highlight_rows),
        "generated_at": datetime.now().isoformat(),
        "visual_mode": visual_mode,
        "generation_mode": generation_mode,
    }
    if metadata:
        plan_metadata.update(dict(metadata))

    return {
        "mode": "movie_story",
        "video_path": video_path,
        "movie_title": movie_title,
        "target_duration_seconds": int(target_duration_seconds or round(cursor) or 0),
        "segments": segments,
        "audio_tracks": {
            "bgm_path": "",
            "narration_path": narration_audio_path or "",
            "keep_raw_audio": any(bool(seg.get("raw_audio_worthy")) or seg.get("audio_mode") in {"raw", "ducked_raw"} for seg in segments),
        },
        "metadata": plan_metadata,
    }


def validate_composition_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return lightweight diagnostics for a CompositionPlan."""
    segments = list((plan or {}).get("segments") or [])
    issues: List[str] = []
    previous_timeline_end = 0.0
    for idx, segment in enumerate(segments, start=1):
        start = _as_float(segment.get("video_start"), 0.0)
        end = _as_float(segment.get("video_end"), start)
        timeline_start = _as_float(segment.get("timeline_start"), previous_timeline_end)
        timeline_end = _as_float(segment.get("timeline_end"), timeline_start)
        if end <= start:
            issues.append(f"segment_{idx}:invalid_video_window")
        if timeline_end <= timeline_start:
            issues.append(f"segment_{idx}:invalid_timeline_window")
        if timeline_start + 0.01 < previous_timeline_end:
            issues.append(f"segment_{idx}:timeline_overlap")
        if segment.get("audio_mode") not in {"raw", "ducked_raw", "tts", "mute"}:
            issues.append(f"segment_{idx}:invalid_audio_mode")
        previous_timeline_end = max(previous_timeline_end, timeline_end)

    return {
        "stage": "08_movie_story_composition_plan",
        "segment_count": len(segments),
        "total_timeline_seconds": round(previous_timeline_end, 3),
        "passed": not issues and bool(segments),
        "issues": issues,
    }
