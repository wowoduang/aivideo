from __future__ import annotations

"""Legacy per-segment understanding enrichment for Movie Story.

The old AIVideoGPT highlight selector had a useful segment-level semantic
model: speaker exchange, pressure direction, primary evidence type and shot
role.  This module ports that value into Movie Story understanding without
changing segment boundaries or replacing LLM local understanding.
"""

from typing import Any, Dict, List, Mapping, Sequence

from app.services.highlight_selector import enrich_candidate_evidence


_PLOT_TAGS = {
    "反转": "reveal",
    "信息揭露": "reveal",
    "冲突升级": "conflict",
    "情感爆发": "emotion_peak",
    "结局收束": "ending",
}

_LEGACY_SEGMENT_KEYS = (
    "character_names",
    "speaker_sequence",
    "speaker_names",
    "speaker_turns",
    "exchange_pairs",
    "interaction_target_names",
    "pressure_source_names",
    "pressure_target_names",
    "visible_action_score",
    "reaction_score",
    "inner_state_support",
    "relation_score",
    "narrative_overview_score",
    "group_reaction_score",
    "solo_focus_score",
    "dialogue_exchange_score",
    "ensemble_scene_score",
    "primary_evidence",
    "shot_role",
)


def _time(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _unique(values: Sequence[Any] | None, limit: int = 12) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _text(*values: Any, limit: int = 1200) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text[:limit]
    return ""


def _tags(item: Mapping[str, Any]) -> List[str]:
    tags = list(item.get("tags") or item.get("information_tags") or [])
    plot_function = str(item.get("plot_function") or "").strip()
    tag = _PLOT_TAGS.get(plot_function)
    if tag:
        tags.append(tag)
    if item.get("raw_voice_retain_suggestion") or item.get("llm_raw_voice_keep"):
        tags.append("raw_audio")
    return _unique(tags)


def _candidate_from_segment(item: Mapping[str, Any], index: int, total: int) -> Dict[str, Any]:
    start = _time(item.get("start", item.get("video_start", 0.0)))
    end = _time(item.get("end", item.get("video_end", start)), start)
    if end <= start:
        end = start + 0.5
    local = dict(item.get("local_understanding") or {})
    text = _text(
        item.get("subtitle_text"),
        item.get("main_text_evidence"),
        item.get("aligned_subtitle_text"),
        item.get("source_text"),
        item.get("text"),
    )
    scene_summary = _text(
        item.get("real_narrative_state"),
        local.get("real_narrative_state"),
        item.get("surface_dialogue_meaning"),
        local.get("surface_dialogue_meaning"),
        local.get("core_event"),
        text,
    )
    position = round((index - 1) / max(total - 1, 1), 3) if total > 1 else 0.5
    return {
        "clip_id": str(item.get("segment_id") or item.get("scene_id") or item.get("candidate_id") or f"seg_{index:04d}"),
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(max(end - start, 0.5), 3),
        "source": "scene",
        "story_index": index,
        "story_position": position,
        "plot_function": item.get("plot_function") or local.get("plot_function") or "",
        "plot_role": item.get("plot_role") or "",
        "importance_level": item.get("importance_level") or local.get("importance_level") or "",
        "attraction_level": item.get("attraction_level") or "",
        "narration_level": item.get("narration_level") or "",
        "subtitle_text": text,
        "scene_summary": scene_summary,
        "story_score": item.get("story_score") or item.get("highlight_score") or 0.0,
        "emotion_score": item.get("emotion_score") or 0.0,
        "energy_score": item.get("energy_score") or 0.0,
        "raw_audio_worthy": bool(item.get("raw_voice_retain_suggestion") or item.get("llm_raw_voice_keep")),
        "tags": _tags(item),
        "speaker_sequence": list(item.get("speaker_sequence") or local.get("speaker_sequence") or []),
        "speaker_names": list(item.get("speaker_names") or local.get("speaker_names") or []),
        "speaker_turns": int(item.get("speaker_turns") or local.get("speaker_turns") or 0),
        "exchange_pairs": list(item.get("exchange_pairs") or local.get("exchange_pairs") or []),
        "interaction_target_names": list(item.get("interaction_target_names") or local.get("interaction_target_names") or []),
        "pressure_source_names": list(item.get("pressure_source_names") or local.get("pressure_source_names") or []),
        "pressure_target_names": list(item.get("pressure_target_names") or local.get("pressure_target_names") or []),
        "character_names": list(
            item.get("character_names")
            or local.get("character_names")
            or local.get("characters")
            or []
        ),
    }


def enrich_legacy_segment_understanding(
    scene_evidence: Sequence[Mapping[str, Any]] | None,
) -> List[Dict[str, Any]]:
    """Write old per-segment semantic signals back to scene evidence.

    This is a pure enrichment pass: it preserves existing timing, IDs and LLM
    local-understanding fields, then adds deterministic legacy semantic
    descriptors that downstream highlight and narration code can consume.
    """

    rows = [dict(item) for item in list(scene_evidence or []) if isinstance(item, Mapping)]
    total = len(rows)
    out: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        enriched = enrich_candidate_evidence(_candidate_from_segment(row, index, total))
        local = dict(row.get("local_understanding") or {})
        legacy_segment = {key: enriched.get(key) for key in _LEGACY_SEGMENT_KEYS if key in enriched}
        legacy_segment["story_position"] = enriched.get("story_position")
        legacy_segment["story_stage_hint"] = enriched.get("story_stage_hint")
        legacy_segment["source"] = "legacy_highlight_selector_segment_model"

        for key, value in legacy_segment.items():
            if value not in (None, "", [], {}):
                row.setdefault(key, value)
        if enriched.get("character_names"):
            local["characters"] = _unique(list(local.get("characters") or []) + list(enriched.get("character_names") or []), limit=8)
        local["legacy_segment_understanding"] = legacy_segment
        local.setdefault("primary_evidence", legacy_segment.get("primary_evidence"))
        local.setdefault("shot_role", legacy_segment.get("shot_role"))
        row["local_understanding"] = local
        row["legacy_segment_understanding"] = legacy_segment
        out.append(row)
    return out


__all__ = ["enrich_legacy_segment_understanding"]
