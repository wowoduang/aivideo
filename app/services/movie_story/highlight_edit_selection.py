from __future__ import annotations

"""Selection-pool helpers for the highlight edit pipeline.

This module is the Stage-J landing zone for the remaining large selection
logic that had stayed inside ``highlight_edit_pipeline.py``.  It keeps the
existing heuristics intact while making the future edit bus reuse a dedicated
movie-story selection runtime instead of another monolithic pipeline file.

Pure module: no file I/O, no LLM calls, no global pipeline state.
"""

from typing import Any, Callable, Dict, List, Optional

from app.services.highlight_selector import select_highlight_clips



def _build_subtitle_segment_map(subtitle_segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for segment in subtitle_segments or []:
        seg_id = str(segment.get("seg_id", "") or segment.get("id", "") or "").strip()
        if seg_id:
            mapping[seg_id] = dict(segment)
    return mapping


def _clip_overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    left_start = float(left.get("start", 0.0) or 0.0)
    left_end = float(left.get("end", left_start) or left_start)
    right_start = float(right.get("start", 0.0) or 0.0)
    right_end = float(right.get("end", right_start) or right_start)
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    min_duration = max(
        min(max(left_end - left_start, 0.001), max(right_end - right_start, 0.001)),
        0.001,
    )
    return overlap / min_duration


def _sorted_unique_values(values: List[Any]) -> List[Any]:
    return sorted(
        dict.fromkeys(value for value in (values or []) if value not in (None, "")),
        key=lambda value: str(value),
    )


def _ordered_unique_values(values: List[Any]) -> List[Any]:
    return list(dict.fromkeys(value for value in (values or []) if value not in (None, "")))


def _clip_specificity_key(clip: Dict[str, Any]) -> tuple:
    source = str(clip.get("source", "") or "")
    source_priority = 2 if source == "scene" else 1
    duration = float(clip.get("duration", 0.0) or 0.0)
    score = float(clip.get("total_score", 0.0) or 0.0)
    return (source_priority, -duration, score)


def _clip_similarity(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    overlap = _clip_overlap_ratio(left, right)
    left_pos = float(left.get("story_position", 0.5) if left.get("story_position") not in (None, "") else 0.5)
    right_pos = float(right.get("story_position", 0.5) if right.get("story_position") not in (None, "") else 0.5)
    position_similarity = max(0.0, 1.0 - abs(left_pos - right_pos) / 0.25)
    left_stage = str(left.get("story_stage_hint", "") or "")
    right_stage = str(right.get("story_stage_hint", "") or "")
    stage_similarity = 1.0 if left_stage and left_stage == right_stage else 0.0
    left_tags = set(str(item) for item in (left.get("tags") or []))
    right_tags = set(str(item) for item in (right.get("tags") or []))
    tag_similarity = 0.0
    if left_tags or right_tags:
        tag_similarity = len(left_tags & right_tags) / max(len(left_tags | right_tags), 1)
    return round(overlap * 0.55 + position_similarity * 0.2 + stage_similarity * 0.15 + tag_similarity * 0.1, 3)


def _clip_relevance_score(clip: Dict[str, Any]) -> float:
    score = float(clip.get("total_score", 0.0) or 0.0)
    if clip.get("raw_audio_worthy"):
        score += 0.05
    if str(clip.get("source", "") or "") == "scene":
        score += 0.06
    if "scene_refined" in set(str(item) for item in (clip.get("tags") or [])):
        score += 0.04
    duration = float(clip.get("duration", 0.0) or 0.0)
    if 2.0 <= duration <= 6.0:
        score += 0.04
    return round(score, 3)


def _peak_window_signal_score(clip: Dict[str, Any]) -> float:
    score = _clip_relevance_score(clip)
    score += min(float(clip.get("audio_signal_score", 0.0) or 0.0), 1.0) * 0.12
    score += min(float(clip.get("audio_peak_score", 0.0) or 0.0), 1.0) * 0.14
    score += min(float(clip.get("story_score", 0.0) or 0.0), 1.0) * 0.08
    score += min(float(clip.get("emotion_score", 0.0) or 0.0), 1.0) * 0.06
    if clip.get("raw_audio_worthy"):
        score += 0.08
    tags = set(str(item) for item in (clip.get("tags") or []))
    if {"conflict", "emotion_peak", "reveal", "twist", "audio_peak"} & tags:
        score += 0.08
    stage = str(clip.get("story_stage_hint", "") or "")
    if stage in {"turning_point", "climax", "reveal", "ending"}:
        score += 0.05
    if float(clip.get("peak_window_text_score", 0.0) or 0.0) >= 0.55:
        score += min(float(clip.get("peak_window_text_score", 0.0) or 0.0) * 0.08, 0.06)
    if float(clip.get("peak_window_dialogue_score", 0.0) or 0.0) >= 0.55:
        score += min(float(clip.get("peak_window_dialogue_score", 0.0) or 0.0) * 0.06, 0.05)
    if float(clip.get("peak_window_payoff_score", 0.0) or 0.0) >= 0.52:
        score += min(float(clip.get("peak_window_payoff_score", 0.0) or 0.0) * 0.08, 0.06)
    if float(clip.get("peak_window_character_score", 0.0) or 0.0) >= 0.5:
        score += min(float(clip.get("peak_window_character_score", 0.0) or 0.0) * 0.06, 0.05)
    return round(score, 3)


def _peak_window_bounds(clip: Dict[str, Any]) -> tuple[float, float]:
    start = float(clip.get("peak_window_start", clip.get("start", 0.0)) or 0.0)
    end = float(clip.get("peak_window_end", clip.get("end", start)) or start)
    if end <= start:
        start = float(clip.get("start", 0.0) or 0.0)
        end = float(clip.get("end", start) or start)
    return start, max(end, start)


def _peak_window_overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    left_start, left_end = _peak_window_bounds(left)
    right_start, right_end = _peak_window_bounds(right)
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    min_duration = max(min(max(left_end - left_start, 0.001), max(right_end - right_start, 0.001)), 0.001)
    return overlap / min_duration


def _can_join_peak_window(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    max_gap_seconds: float,
    max_window_seconds: float,
) -> bool:
    left_start = float(left.get("start", 0.0) or 0.0)
    left_end = float(left.get("end", left_start) or left_start)
    right_start = float(right.get("start", 0.0) or 0.0)
    right_end = float(right.get("end", right_start) or right_start)
    gap = right_start - left_end
    if gap > max_gap_seconds:
        return False
    if right_end - left_start > max_window_seconds:
        return False

    left_scene = str(left.get("source_scene_id", "") or "")
    right_scene = str(right.get("source_scene_id", "") or "")
    left_parent = str(left.get("parent_clip_id", "") or "")
    right_parent = str(right.get("parent_clip_id", "") or "")
    left_stage = str(left.get("story_stage_hint", "") or "")
    right_stage = str(right.get("story_stage_hint", "") or "")
    left_pos = float(left.get("story_position", 0.5) if left.get("story_position") not in (None, "") else 0.5)
    right_pos = float(right.get("story_position", 0.5) if right.get("story_position") not in (None, "") else 0.5)
    same_scene = bool(left_scene and right_scene and left_scene == right_scene)
    same_parent = bool(left_parent and right_parent and left_parent == right_parent)
    same_stage = bool(left_stage and right_stage and left_stage == right_stage)
    overlap = _clip_overlap_ratio(left, right) >= 0.18
    strong_pair = max(_peak_window_signal_score(left), _peak_window_signal_score(right)) >= 0.82
    close_story = abs(left_pos - right_pos) <= 0.14

    if same_scene or same_parent:
        return True
    if gap <= 1.2 and (same_stage or close_story):
        return True
    if gap <= 0.4 and strong_pair:
        return True
    if overlap and (same_stage or strong_pair):
        return True
    return False


def _peak_window_strength(window: List[Dict[str, Any]]) -> float:
    if not window:
        return 0.0

    ordered_scores = sorted((_peak_window_signal_score(item) for item in window), reverse=True)
    total_scores = [float(item.get("total_score", 0.0) or 0.0) for item in window]
    window_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
    window_end = max(float(item.get("end", window_start) or window_start) for item in window)
    window_duration = max(window_end - window_start, 0.0)
    top_signal = ordered_scores[0]
    pair_avg = sum(ordered_scores[:2]) / max(len(ordered_scores[:2]), 1)
    mean_total = sum(total_scores) / max(len(total_scores), 1)
    raw_audio_bonus = 0.08 if any(item.get("raw_audio_worthy") for item in window) else 0.0
    stage_bonus = 0.06 if any(str(item.get("story_stage_hint", "") or "") in {"turning_point", "climax", "reveal", "ending"} for item in window) else 0.0
    density_bonus = min(max(len(window) - 1, 0), 3) * 0.04
    duration_bonus = min(window_duration / 12.0, 1.0) * 0.05
    strength = top_signal * 0.5 + pair_avg * 0.22 + mean_total * 0.15 + raw_audio_bonus + stage_bonus + density_bonus + duration_bonus
    return round(strength, 3)


def _window_text_profile_config(highlight_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = dict(highlight_profile or {})
    signal_route = str(profile.get("signal_route", "") or "")
    signal_metrics = dict(profile.get("signal_metrics") or {})
    text_reliability = float(signal_metrics.get("text_reliability", 0.0) or 0.0)
    text_favoring_route = signal_route in {"dialogue_driven", "performance_reaction", "ensemble_conflict"}
    route_weight_map = {
        "dialogue_driven": 1.0,
        "ensemble_conflict": 0.96,
        "performance_reaction": 0.88,
        "balanced_mixed": 0.62,
        "kinetic_visual": 0.32,
        "visual_audio_fallback": 0.18,
    }
    return {
        "signal_route": signal_route,
        "text_reliability": text_reliability,
        "text_favoring_route": text_favoring_route,
        "route_weight": float(route_weight_map.get(signal_route, 0.7 if text_reliability >= 0.45 else 0.4)),
        "search_padding_seconds": 1.8 if text_favoring_route else 0.6,
        "subtitle_expand_limit": 4.5 if text_favoring_route else 2.0,
        "plot_expand_limit": 6.0 if text_favoring_route else 3.0,
    }


def _pick_peak_window_anchor(window: List[Dict[str, Any]]) -> Dict[str, Any]:
    window_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
    window_end = max(float(item.get("end", window_start) or window_start) for item in window)
    midpoint = (window_start + window_end) / 2.0
    return dict(
        max(
            (dict(item) for item in window),
            key=lambda item: (
                _peak_window_signal_score(item),
                -abs(((float(item.get("start", 0.0) or 0.0) + float(item.get("end", item.get("start", 0.0)) or 0.0)) / 2.0) - midpoint),
                float(item.get("duration", 0.0) or 0.0),
            ),
        )
    )


def _related_window_subtitles(
    window: List[Dict[str, Any]],
    subtitle_segment_map: Dict[str, Dict[str, Any]],
    *,
    search_padding_seconds: float,
) -> List[Dict[str, Any]]:
    if not window or not subtitle_segment_map:
        return []

    window_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
    window_end = max(float(item.get("end", window_start) or window_start) for item in window)
    explicit_ids = _ordered_unique_values(
        [
            str(segment_id or "").strip()
            for item in window
            for segment_id in (item.get("source_segment_ids") or [])
            if str(segment_id or "").strip()
        ]
    )
    related: List[Dict[str, Any]] = []
    if explicit_ids:
        for segment_id in explicit_ids:
            segment = subtitle_segment_map.get(segment_id)
            if segment:
                related.append(dict(segment))
        if related:
            return related

    for segment in subtitle_segment_map.values():
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        if end < window_start - search_padding_seconds or start > window_end + search_padding_seconds:
            continue
        related.append(dict(segment))
    return sorted(related, key=lambda item: float(item.get("start", 0.0) or 0.0))


def _pick_window_plot_chunk(
    window: List[Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    subtitle_ids: List[str],
) -> Dict[str, Any]:
    if not window or not plot_chunks:
        return {}

    window_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
    window_end = max(float(item.get("end", window_start) or window_start) for item in window)
    subtitle_id_set = {str(item or "").strip() for item in (subtitle_ids or []) if str(item or "").strip()}
    best_chunk: Dict[str, Any] = {}
    best_key: tuple[Any, ...] | None = None

    for chunk in plot_chunks or []:
        chunk_start = float(chunk.get("start", 0.0) or 0.0)
        chunk_end = float(chunk.get("end", chunk_start) or chunk_start)
        overlap = max(0.0, min(chunk_end, window_end) - max(chunk_start, window_start))
        chunk_subtitle_ids = {
            str(item or "").strip() for item in (chunk.get("subtitle_ids") or []) if str(item or "").strip()
        }
        shared_ids = len(subtitle_id_set & chunk_subtitle_ids) if subtitle_id_set else 0
        proximity = -abs(((chunk_start + chunk_end) / 2.0) - ((window_start + window_end) / 2.0))
        key = (shared_ids, overlap, proximity, float(chunk.get("highlight_score", 0.0) or 0.0))
        if best_key is None or key > best_key:
            best_key = key
            best_chunk = dict(chunk)

    return best_chunk if best_key and (best_key[0] > 0 or best_key[1] > 0.0) else {}


def _snap_peak_window_bounds(
    window: List[Dict[str, Any]],
    *,
    subtitle_segment_map: Dict[str, Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> tuple[float, float, List[str]]:
    base_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
    base_end = max(float(item.get("end", base_start) or base_start) for item in window)
    profile_config = _window_text_profile_config(highlight_profile)
    text_reliability = float(profile_config["text_reliability"])
    text_favoring_route = bool(profile_config["text_favoring_route"])
    search_padding_seconds = float(profile_config["search_padding_seconds"])
    subtitle_expand_limit = float(profile_config["subtitle_expand_limit"])
    plot_expand_limit = float(profile_config["plot_expand_limit"])

    reasons: List[str] = []
    snapped_start = base_start
    snapped_end = base_end

    related_subtitles = _related_window_subtitles(
        window,
        subtitle_segment_map,
        search_padding_seconds=search_padding_seconds,
    )
    subtitle_ids = [
        str(item.get("seg_id", "") or item.get("id", "") or "").strip()
        for item in related_subtitles
        if str(item.get("seg_id", "") or item.get("id", "") or "").strip()
    ]
    if related_subtitles and (text_favoring_route or text_reliability >= 0.42):
        subtitle_start = min(float(item.get("start", 0.0) or 0.0) for item in related_subtitles)
        subtitle_end = max(float(item.get("end", subtitle_start) or subtitle_start) for item in related_subtitles)
        if abs(subtitle_start - base_start) <= subtitle_expand_limit:
            snapped_start = min(snapped_start, subtitle_start)
            reasons.append("subtitle_boundary_snap")
        if abs(subtitle_end - base_end) <= subtitle_expand_limit:
            snapped_end = max(snapped_end, subtitle_end)
            reasons.append("subtitle_boundary_snap")

    related_chunk = _pick_window_plot_chunk(window, plot_chunks, subtitle_ids)
    if related_chunk and (text_favoring_route or text_reliability >= 0.48):
        chunk_start = float(related_chunk.get("start", 0.0) or 0.0)
        chunk_end = float(related_chunk.get("end", chunk_start) or chunk_start)
        if abs(chunk_start - base_start) <= plot_expand_limit:
            snapped_start = min(snapped_start, chunk_start)
            reasons.append("plot_boundary_snap")
        if abs(chunk_end - base_end) <= plot_expand_limit:
            snapped_end = max(snapped_end, chunk_end)
            reasons.append("plot_boundary_snap")

    return round(snapped_start, 3), round(max(snapped_end, snapped_start), 3), _ordered_unique_values(reasons)


def _window_time_overlap_ratio(start: float, end: float, other_start: float, other_end: float) -> float:
    overlap = max(0.0, min(end, other_end) - max(start, other_start))
    duration = max(other_end - other_start, 0.001)
    return overlap / duration


def _compact_speaker_turns(related_subtitles: List[Dict[str, Any]]) -> List[str]:
    compact_turns: List[str] = []
    for speaker in (
        str(item.get("speaker", "") or "").strip()
        for item in (related_subtitles or [])
        if str(item.get("speaker", "") or "").strip()
    ):
        if not compact_turns or speaker != compact_turns[-1]:
            compact_turns.append(speaker)
    return compact_turns


def _compact_window_speaker_turns(window: List[Dict[str, Any]]) -> List[str]:
    compact_turns: List[str] = []
    explicit_sequence = [
        str(item or "").strip()
        for clip in (window or [])
        for item in (clip.get("speaker_sequence") or [])
        if str(item or "").strip()
    ]
    if explicit_sequence:
        for speaker in explicit_sequence:
            if not compact_turns or speaker != compact_turns[-1]:
                compact_turns.append(speaker)
        return compact_turns

    pair_sequence: List[str] = []
    for raw_pair in (
        str(pair or "").strip()
        for clip in (window or [])
        for pair in (clip.get("exchange_pairs") or [])
        if str(pair or "").strip() and "->" in str(pair or "")
    ):
        left, right = (part.strip() for part in raw_pair.split("->", 1))
        if left:
            pair_sequence.append(left)
        if right:
            pair_sequence.append(right)
    for speaker in pair_sequence:
        if not compact_turns or speaker != compact_turns[-1]:
            compact_turns.append(speaker)
    return compact_turns


def _window_character_names(window: List[Dict[str, Any]]) -> List[str]:
    return _ordered_unique_values(
        [
            str(name or "").strip()
            for clip in (window or [])
            for name in (
                list(clip.get("character_names") or [])
                + list(clip.get("speaker_names") or [])
                + list(clip.get("pressure_target_names") or [])
                + list(clip.get("pressure_source_names") or [])
            )
            if str(name or "").strip()
        ]
    )


def _detect_main_character_reference(candidate_clips: List[Dict[str, Any]]) -> List[str]:
    character_scores: Dict[str, float] = {}
    for clip in candidate_clips or []:
        clip_weight = (
            float(clip.get("total_score", 0.0) or 0.0) * 0.55
            + float(clip.get("story_score", 0.0) or 0.0) * 0.2
            + float(clip.get("emotion_score", 0.0) or 0.0) * 0.15
            + (0.08 if clip.get("raw_audio_worthy") else 0.0)
            + (0.06 if str(clip.get("shot_role", "") or "") == "single_focus" else 0.0)
        )
        for name in _ordered_unique_values(
            list(clip.get("character_names") or [])
            + list(clip.get("speaker_names") or [])
            + list(clip.get("pressure_target_names") or [])
        ):
            bonus = 0.0
            if name in set(str(item or "").strip() for item in (clip.get("pressure_target_names") or []) if str(item or "").strip()):
                bonus += 0.12
            if name in set(str(item or "").strip() for item in (clip.get("speaker_names") or []) if str(item or "").strip()):
                bonus += 0.08
            character_scores[name] = character_scores.get(name, 0.0) + clip_weight + bonus

    ordered = sorted(character_scores.items(), key=lambda item: (item[1], item[0]), reverse=True)
    return [name for name, _ in ordered[:3]]


def _peak_window_text_rerank_score(
    *,
    related_subtitles: List[Dict[str, Any]],
    related_chunk: Dict[str, Any],
    snapped_start: float,
    snapped_end: float,
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> float:
    """计算峰值窗口文本重排分数。
    
    文本只作为候选排序信号，不作为本地剧情解读结论。
    """
    profile_config = _window_text_profile_config(highlight_profile)
    text_reliability = float(profile_config["text_reliability"])
    route_weight = float(profile_config["route_weight"])
    text_favoring_route = bool(profile_config["text_favoring_route"])
    if not related_subtitles and not related_chunk:
        return 0.0

    subtitle_texts = [str(item.get("text", "") or "").strip() for item in related_subtitles if str(item.get("text", "") or "").strip()]
    subtitle_chars = sum(len(text) for text in subtitle_texts)
    subtitle_count = len(subtitle_texts)
    subtitle_span_score = min(subtitle_count / (3.0 if text_favoring_route else 2.0), 1.0) if subtitle_count else 0.0
    text_density = min(subtitle_chars / 90.0, 1.0) if subtitle_chars else 0.0
    subtitle_coverage = 0.0
    completeness_bonus = 0.0
    speaker_turn_score = 0.0

    if related_subtitles:
        subtitle_start = min(float(item.get("start", 0.0) or 0.0) for item in related_subtitles)
        subtitle_end = max(float(item.get("end", subtitle_start) or subtitle_start) for item in related_subtitles)
        subtitle_coverage = _window_time_overlap_ratio(snapped_start, snapped_end, subtitle_start, subtitle_end)
        if abs(snapped_start - subtitle_start) <= 0.2 and abs(snapped_end - subtitle_end) <= 0.35:
            completeness_bonus += 0.12

        compact_turns = _compact_speaker_turns(related_subtitles)
        turn_switches = max(len(compact_turns) - 1, 0)
        speaker_turn_score = min(turn_switches / 2.0, 1.0) if turn_switches > 0 else 0.0

    chunk_coverage = 0.0
    chunk_bonus = 0.0
    if related_chunk:
        chunk_start = float(related_chunk.get("start", 0.0) or 0.0)
        chunk_end = float(related_chunk.get("end", chunk_start) or chunk_start)
        chunk_coverage = _window_time_overlap_ratio(snapped_start, snapped_end, chunk_start, chunk_end)
        if chunk_coverage >= 0.92:
            chunk_bonus += 0.1

    raw_score = (
        subtitle_coverage * 0.28
        + chunk_coverage * 0.24
        + text_density * 0.18
        + subtitle_span_score * 0.14
        + speaker_turn_score * 0.1
        + completeness_bonus
        + chunk_bonus
    )
    reliability_factor = 0.35 + min(max(text_reliability, 0.0), 1.0) * 0.65
    route_factor = 0.35 + min(max(route_weight, 0.0), 1.0) * 0.65
    return round(min(raw_score * reliability_factor * route_factor, 1.0), 3)


def _peak_window_dialogue_cycle_score(
    *,
    related_subtitles: List[Dict[str, Any]],
    window: List[Dict[str, Any]],
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> float:
    profile_config = _window_text_profile_config(highlight_profile)
    route_weight = float(profile_config["route_weight"])
    text_reliability = float(profile_config["text_reliability"])
    compact_turns = _compact_speaker_turns(related_subtitles)
    if len(compact_turns) < 2:
        compact_turns = _compact_window_speaker_turns(window)

    unique_speakers = list(dict.fromkeys(compact_turns))
    turn_switches = max(len(compact_turns) - 1, 0)
    cycle_bonus = 0.0
    if len(compact_turns) >= 3 and compact_turns[0] == compact_turns[2]:
        cycle_bonus += 0.24
    if len(compact_turns) >= 4 and compact_turns[0] == compact_turns[-1]:
        cycle_bonus += 0.1
    if len(unique_speakers) >= 3 and len(compact_turns) >= 3:
        cycle_bonus += 0.14
    exchange_density = min(turn_switches / 3.0, 1.0) * 0.34
    speaker_variety = min(len(unique_speakers) / 3.0, 1.0) * 0.18

    pressure_targets = _ordered_unique_values(
        [name for item in window for name in (item.get("pressure_target_names") or []) if str(name or "").strip()]
    )
    pressure_sources = _ordered_unique_values(
        [name for item in window for name in (item.get("pressure_source_names") or []) if str(name or "").strip()]
    )
    pressure_bonus = 0.0
    if len(pressure_targets) == 1 and len(pressure_sources) >= 2:
        pressure_bonus += 0.18
    elif pressure_targets and pressure_sources:
        pressure_bonus += 0.08
    inferred_turn_bonus = 0.0
    if len(compact_turns) < 2:
        related_subtitle_count = len([item for item in (related_subtitles or []) if str(item.get("text", "") or "").strip()])
        inferred_turn_bonus += min(related_subtitle_count / 3.0, 1.0) * 0.12
        inferred_turn_bonus += min(len(_window_character_names(window)) / 3.0, 1.0) * 0.08

    window_relation = max(float(item.get("relation_score", 0.0) or 0.0) for item in window)
    window_dialogue = max(float(item.get("dialogue_exchange_score", 0.0) or 0.0) for item in window)
    score = exchange_density + speaker_variety + cycle_bonus + pressure_bonus + inferred_turn_bonus
    score += min(window_dialogue * 0.1, 0.08)
    score += min(window_relation * 0.08, 0.06)
    route_factor = 0.35 + min(max(route_weight, 0.0), 1.0) * 0.65
    reliability_factor = 0.35 + min(max(text_reliability, 0.0), 1.0) * 0.65
    return round(min(score * route_factor * reliability_factor, 1.0), 3)


def _peak_window_character_focus_score(
    *,
    window: List[Dict[str, Any]],
    main_characters: List[str],
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> float:
    """计算峰值窗口中角色/人物相关线索的局部评分。
    
    该分数只用于候选排序，不在本地推断最终人物关系结论。
    """
    if not window or not main_characters:
        return 0.0

    profile_config = _window_text_profile_config(highlight_profile)
    route_weight = float(profile_config["route_weight"])
    main_set = {str(name or "").strip() for name in (main_characters or []) if str(name or "").strip()}
    if not main_set:
        return 0.0

    ordered_window = sorted((dict(item) for item in window), key=lambda item: float(item.get("start", 0.0) or 0.0))
    clip_hits = 0
    target_hits = 0
    speaker_hits = 0
    continuity_streak = 0
    max_streak = 0
    for clip in ordered_window:
        clip_names = {
            str(name or "").strip()
            for name in (
                list(clip.get("character_names") or [])
                + list(clip.get("speaker_names") or [])
                + list(clip.get("pressure_target_names") or [])
            )
            if str(name or "").strip()
        }
        target_names = {
            str(name or "").strip() for name in (clip.get("pressure_target_names") or []) if str(name or "").strip()
        }
        speaker_names = {
            str(name or "").strip() for name in (clip.get("speaker_names") or []) if str(name or "").strip()
        }
        if clip_names & main_set:
            clip_hits += 1
            continuity_streak += 1
            max_streak = max(max_streak, continuity_streak)
        else:
            continuity_streak = 0
        if target_names & main_set:
            target_hits += 1
        if speaker_names & main_set:
            speaker_hits += 1

    coverage_score = min(clip_hits / max(len(ordered_window), 1), 1.0) * 0.4
    target_score = min(target_hits / max(len(ordered_window), 1), 1.0) * 0.22
    speaker_score = min(speaker_hits / max(len(ordered_window), 1), 1.0) * 0.14
    continuity_score = min(max_streak / max(len(ordered_window), 1), 1.0) * 0.16
    climax_bonus = 0.0
    if ordered_window and any(
        ({str(name or "").strip() for name in (clip.get("pressure_target_names") or []) if str(name or "").strip()} & main_set)
        and str(clip.get("story_stage_hint", "") or "") in {"turning_point", "climax", "reveal", "ending"}
        for clip in ordered_window
    ):
        climax_bonus += 0.12

    route_factor = 0.55 + min(max(route_weight, 0.0), 1.0) * 0.45
    return round(min((coverage_score + target_score + speaker_score + continuity_score + climax_bonus) * route_factor, 1.0), 3)


def _peak_window_payoff_arc_score(
    *,
    window: List[Dict[str, Any]],
    related_chunk: Dict[str, Any],
    highlight_profile: Optional[Dict[str, Any]] = None,
) -> float:
    """计算峰值窗口中的剧情回报/转折弧线评分。
    
    该 helper 服务候选排序；最终叙事解释仍交给双轮链或文案链。
    """
    if not window:
        return 0.0

    profile_config = _window_text_profile_config(highlight_profile)
    route_weight = float(profile_config["route_weight"])
    ordered_window = sorted((dict(item) for item in window), key=lambda item: float(item.get("start", 0.0) or 0.0))
    first = ordered_window[0]
    last = ordered_window[-1]
    tags = {str(tag).strip() for item in ordered_window for tag in (item.get("tags") or []) if str(tag).strip()}
    stages = {
        str(item.get("story_stage_hint", "") or "").strip()
        for item in ordered_window
        if str(item.get("story_stage_hint", "") or "").strip()
    }
    stage_progression = min(max(len(stages) - 1, 0) / 2.0, 1.0) * 0.18
    payoff_tags = {"reveal", "emotion_peak", "ending"}
    setup_tags = {"conflict", "raw_audio", "audio_peak"}
    tag_progression = 0.0
    if tags & payoff_tags and tags & setup_tags:
        tag_progression += 0.24
    elif tags & payoff_tags:
        tag_progression += 0.12

    score_progression = 0.0
    first_score = _peak_window_signal_score(first)
    last_score = _peak_window_signal_score(last)
    if last_score >= first_score + 0.08:
        score_progression += 0.16
    top_index = max(range(len(ordered_window)), key=lambda index: _peak_window_signal_score(ordered_window[index]))
    if len(ordered_window) > 1 and top_index >= len(ordered_window) // 2:
        score_progression += 0.12

    chunk_bonus = 0.0
    if related_chunk:
        plot_function = str(related_chunk.get("plot_function", "") or "")
        if any(token in plot_function.lower() for token in ("reveal", "twist", "ending", "conflict", "emotion")):
            chunk_bonus += 0.12
        if float(related_chunk.get("highlight_score", 0.0) or 0.0) >= 0.72:
            chunk_bonus += 0.08

    raw_audio_bonus = 0.0
    if any(item.get("raw_audio_worthy") for item in ordered_window[len(ordered_window) // 2:]):
        raw_audio_bonus += 0.12
    emotion_late = max(float(item.get("emotion_score", 0.0) or 0.0) for item in ordered_window[len(ordered_window) // 2:]) if ordered_window else 0.0
    if emotion_late >= 0.72:
        raw_audio_bonus += 0.08

    arc_score = stage_progression + tag_progression + score_progression + chunk_bonus + raw_audio_bonus
    route_factor = 0.45 + min(max(route_weight, 0.0), 1.0) * 0.55
    return round(min(arc_score * route_factor, 1.0), 3)


def _build_peak_window_anchors(
    candidate_clips: List[Dict[str, Any]],
    target_duration_seconds: int,
    *,
    subtitle_segment_map: Optional[Dict[str, Dict[str, Any]]] = None,
    plot_chunks: Optional[List[Dict[str, Any]]] = None,
    highlight_profile: Optional[Dict[str, Any]] = None,
    main_characters: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """构造高光峰值窗口锚点。
    
    该函数服务长视频拆短视频候选召回，综合文本、时间轴和局部密度信号；
    后续应拆成候选收集、窗口扩展、去重排序等 helper。
    """
    ordered = sorted(
        (dict(item) for item in (candidate_clips or [])),
        key=lambda item: (
            float(item.get("start", 0.0) or 0.0),
            float(item.get("end", item.get("start", 0.0)) or 0.0),
            -_peak_window_signal_score(item),
        ),
    )
    if not ordered:
        return []

    max_gap_seconds = 4.0 if target_duration_seconds >= 120 else 3.2
    max_window_seconds = min(max(float(target_duration_seconds or 0) / 10.0, 8.0), 18.0)
    grouped_windows: List[List[Dict[str, Any]]] = []
    current_window: List[Dict[str, Any]] = []

    for clip in ordered:
        if not current_window:
            current_window = [clip]
            continue
        if _can_join_peak_window(
            current_window[-1],
            clip,
            max_gap_seconds=max_gap_seconds,
            max_window_seconds=max_window_seconds,
        ):
            current_window.append(clip)
            continue
        grouped_windows.append(current_window)
        current_window = [clip]
    if current_window:
        grouped_windows.append(current_window)

    desired_count = max(min(round(float(target_duration_seconds or 0) / 75.0), 4), 2)
    anchors: List[Dict[str, Any]] = []
    for window in grouped_windows:
        if not window:
            continue
        strength = _peak_window_strength(window)
        window_start = min(float(item.get("start", 0.0) or 0.0) for item in window)
        window_end = max(float(item.get("end", window_start) or window_start) for item in window)
        window_duration = round(max(window_end - window_start, 0.0), 3)
        if window_duration < 3.2:
            continue
        if len(window) < 2 and strength < 0.94 and not any(item.get("raw_audio_worthy") for item in window):
            continue

        anchor = _pick_peak_window_anchor(window)
        profile_config = _window_text_profile_config(highlight_profile)
        related_subtitles = _related_window_subtitles(
            window,
            dict(subtitle_segment_map or {}),
            search_padding_seconds=float(profile_config["search_padding_seconds"]),
        )
        related_subtitle_ids = [
            str(item.get("seg_id", "") or item.get("id", "") or "").strip()
            for item in related_subtitles
            if str(item.get("seg_id", "") or item.get("id", "") or "").strip()
        ]
        related_chunk = _pick_window_plot_chunk(window, list(plot_chunks or []), related_subtitle_ids)
        snapped_start, snapped_end, snap_reasons = _snap_peak_window_bounds(
            window,
            subtitle_segment_map=dict(subtitle_segment_map or {}),
            plot_chunks=list(plot_chunks or []),
            highlight_profile=highlight_profile,
        )
        text_score = _peak_window_text_rerank_score(
            related_subtitles=related_subtitles,
            related_chunk=related_chunk,
            snapped_start=snapped_start,
            snapped_end=snapped_end,
            highlight_profile=highlight_profile,
        )
        dialogue_score = _peak_window_dialogue_cycle_score(
            related_subtitles=related_subtitles,
            window=window,
            highlight_profile=highlight_profile,
        )
        payoff_score = _peak_window_payoff_arc_score(
            window=window,
            related_chunk=related_chunk,
            highlight_profile=highlight_profile,
        )
        character_score = _peak_window_character_focus_score(
            window=window,
            main_characters=list(main_characters or []),
            highlight_profile=highlight_profile,
        )
        snapped_duration = round(max(snapped_end - snapped_start, 0.0), 3)
        anchor_duration = max(float(anchor.get("duration", 0.0) or 0.0), 0.0)
        if snapped_duration <= anchor_duration + 0.5:
            continue

        anchor["peak_window_start"] = snapped_start
        anchor["peak_window_end"] = snapped_end
        anchor["peak_window_duration"] = snapped_duration
        anchor["peak_window_strength"] = strength
        anchor["peak_window_text_score"] = text_score
        anchor["peak_window_dialogue_score"] = dialogue_score
        anchor["peak_window_payoff_score"] = payoff_score
        anchor["peak_window_character_score"] = character_score
        anchor["peak_window_clip_ids"] = _ordered_unique_values([str(item.get("clip_id", "") or "") for item in window])
        anchor["selection_reason"] = list(
            dict.fromkeys(list(anchor.get("selection_reason") or []) + ["peak_window"] + list(snap_reasons))
        )
        if text_score >= 0.55:
            anchor["selection_reason"] = list(
                dict.fromkeys(list(anchor.get("selection_reason") or []) + ["text_complete_window"])
            )
        if dialogue_score >= 0.46:
            anchor["selection_reason"] = list(
                dict.fromkeys(list(anchor.get("selection_reason") or []) + ["dialogue_cycle_window"])
            )
        if payoff_score >= 0.42:
            anchor["selection_reason"] = list(
                dict.fromkeys(list(anchor.get("selection_reason") or []) + ["payoff_window"])
            )
        if character_score >= 0.42:
            anchor["selection_reason"] = list(
                dict.fromkeys(list(anchor.get("selection_reason") or []) + ["main_character_window"])
            )
        anchors.append(anchor)

    selected: List[Dict[str, Any]] = []
    route_weight = float(_window_text_profile_config(highlight_profile)["route_weight"])
    for anchor in sorted(
        anchors,
        key=lambda item: (
            float(item.get("peak_window_strength", 0.0) or 0.0)
            + float(item.get("peak_window_text_score", 0.0) or 0.0) * (0.22 if route_weight >= 0.8 else 0.1),
            float(item.get("peak_window_payoff_score", 0.0) or 0.0),
            float(item.get("peak_window_dialogue_score", 0.0) or 0.0),
            float(item.get("peak_window_character_score", 0.0) or 0.0),
            float(item.get("peak_window_text_score", 0.0) or 0.0),
            _peak_window_signal_score(item),
            float(item.get("peak_window_duration", 0.0) or 0.0),
        ),
        reverse=True,
    ):
        if any(_peak_window_overlap_ratio(anchor, existing) >= 0.55 for existing in selected):
            continue
        selected.append(anchor)
        if len(selected) >= desired_count:
            break

    return sorted(selected, key=lambda item: float(item.get("start", 0.0) or 0.0))


def _select_diverse_clips(candidate_clips: List[Dict[str, Any]], top_k: int, lambda_relevance: float = 0.72) -> List[Dict[str, Any]]:
    pool = [dict(item) for item in (candidate_clips or [])]
    if not pool:
        return []

    target = max(int(top_k or 0), 1)
    ordered = sorted(
        pool,
        key=lambda clip: (_clip_relevance_score(clip), float(clip.get("duration", 0.0) or 0.0)),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    while ordered and len(selected) < target:
        best_index = -1
        best_value = None
        for idx, clip in enumerate(ordered):
            relevance = _clip_relevance_score(clip)
            redundancy = max((_clip_similarity(clip, chosen) for chosen in selected), default=0.0)
            mmr_value = lambda_relevance * relevance - (1.0 - lambda_relevance) * redundancy
            ranking = (mmr_value, relevance, -redundancy, float(clip.get("start", 0.0) or 0.0))
            if best_index < 0 or ranking > best_value:
                best_index = idx
                best_value = ranking
        selected.append(dict(ordered.pop(best_index)))
    return selected


def _append_selection_reasons(clip: Dict[str, Any], *reasons: str) -> Dict[str, Any]:
    updated = dict(clip)
    merged = list(updated.get("selection_reason") or [])
    for reason in reasons:
        normalized = str(reason or "").strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    updated["selection_reason"] = merged
    return updated


def _merge_clip_metadata(preferred: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """合并候选片段的剪辑元数据。
    
    输出给后续 composition/export 消费；这里应只做字段归一和证据合并，
    不要引入旧 movie_story native 主流程判断。
    """
    merged = dict(preferred)
    alternate = dict(incoming)

    for field in (
        "total_score",
        "story_score",
        "emotion_score",
        "energy_score",
        "story_position",
        "peak_window_duration",
        "peak_window_strength",
        "peak_window_text_score",
        "peak_window_dialogue_score",
        "peak_window_payoff_score",
        "peak_window_character_score",
        "visible_action_score",
        "reaction_score",
        "inner_state_support",
        "relation_score",
        "narrative_overview_score",
        "group_reaction_score",
        "speaker_turns",
        "solo_focus_score",
        "dialogue_exchange_score",
        "ensemble_scene_score",
    ):
        if field in alternate and alternate.get(field) not in (None, ""):
            current = merged.get(field)
            if current in (None, ""):
                merged[field] = alternate.get(field)
            else:
                try:
                    merged[field] = round(max(float(current), float(alternate.get(field))), 3)
                except (TypeError, ValueError):
                    merged[field] = current

    for field in (
        "selection_reason",
        "tags",
        "character_names",
        "speaker_names",
        "interaction_target_names",
        "pressure_source_names",
        "pressure_target_names",
        "source_segment_ids",
        "keyframe_candidates",
        "boundary_candidates",
    ):
        merged[field] = _sorted_unique_values(list(merged.get(field) or []) + list(alternate.get(field) or []))
    merged["peak_window_clip_ids"] = _ordered_unique_values(
        list(merged.get("peak_window_clip_ids") or []) + list(alternate.get("peak_window_clip_ids") or [])
    )
    merged["speaker_sequence"] = _ordered_unique_values(
        list(merged.get("speaker_sequence") or []) + list(alternate.get("speaker_sequence") or [])
    )
    merged["exchange_pairs"] = _ordered_unique_values(
        list(merged.get("exchange_pairs") or []) + list(alternate.get("exchange_pairs") or [])
    )

    merged["raw_audio_worthy"] = bool(merged.get("raw_audio_worthy") or alternate.get("raw_audio_worthy"))
    merged["prevent_merge"] = bool(merged.get("prevent_merge") or alternate.get("prevent_merge"))

    for field in ("scene_summary", "subtitle_text"):
        merged_value = str(merged.get(field, "") or "")
        incoming_value = str(alternate.get(field, "") or "")
        if len(incoming_value) > len(merged_value):
            merged[field] = incoming_value

    for field in (
        "source_scene_id",
        "plot_function",
        "plot_role",
        "story_stage_hint",
        "source",
        "clip_id",
        "parent_clip_id",
        "subshot_index",
        "primary_evidence",
    ):
        if not merged.get(field) and alternate.get(field) not in (None, ""):
            merged[field] = alternate.get(field)

    merged_role = str(merged.get("shot_role", "") or "")
    alternate_role = str(alternate.get("shot_role", "") or "")
    if merged_role and alternate_role and merged_role != alternate_role:
        merged["shot_role"] = "mixed"
    elif not merged_role and alternate_role:
        merged["shot_role"] = alternate_role

    peak_starts = [
        float(value)
        for value in (merged.get("peak_window_start"), alternate.get("peak_window_start"))
        if value not in (None, "")
    ]
    peak_ends = [
        float(value)
        for value in (merged.get("peak_window_end"), alternate.get("peak_window_end"))
        if value not in (None, "")
    ]
    if peak_starts:
        merged["peak_window_start"] = round(min(peak_starts), 3)
    if peak_ends:
        merged["peak_window_end"] = round(max(peak_ends), 3)

    return merged


def _pick_anchor_clip(
    candidate_clips: List[Dict[str, Any]],
    *,
    story_position_min: Optional[float] = None,
    story_position_max: Optional[float] = None,
    allowed_stages: Optional[set] = None,
    require_raw_audio: bool = False,
) -> List[Dict[str, Any]]:
    pool: List[Dict[str, Any]] = []
    for clip in candidate_clips or []:
        story_position = float(clip.get("story_position", 0.5) if clip.get("story_position") not in (None, "") else 0.5)
        if story_position_min is not None and story_position < story_position_min:
            continue
        if story_position_max is not None and story_position > story_position_max:
            continue
        if require_raw_audio and not clip.get("raw_audio_worthy"):
            continue
        if allowed_stages:
            stage = str(clip.get("story_stage_hint", "") or "")
            if stage not in allowed_stages:
                continue
        pool.append(dict(clip))

    if not pool:
        return []
    ordered = sorted(
        pool,
        key=lambda clip: (
            _clip_relevance_score(clip),
            float(clip.get("total_score", 0.0) or 0.0),
            -abs(float(clip.get("story_position", 0.5) if clip.get("story_position") not in (None, "") else 0.5) - 0.5),
        ),
        reverse=True,
    )
    return [ordered[0]]


def _build_main_character_anchor_clips(
    candidate_clips: List[Dict[str, Any]],
    main_characters: List[str],
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    if not candidate_clips or not main_characters:
        return []

    main_set = {str(name or "").strip() for name in (main_characters or []) if str(name or "").strip()}
    scored_pool: List[Dict[str, Any]] = []
    for clip in candidate_clips or []:
        clip_names = {
            str(name or "").strip()
            for name in (
                list(clip.get("character_names") or [])
                + list(clip.get("speaker_names") or [])
                + list(clip.get("pressure_target_names") or [])
            )
            if str(name or "").strip()
        }
        overlap = len(clip_names & main_set)
        if overlap <= 0:
            continue
        enriched = dict(clip)
        character_score = min(overlap / max(len(main_set), 1), 1.0)
        reference_score = (
            float(clip.get("total_score", 0.0) or 0.0) * 0.62
            + character_score * 0.22
            + (0.08 if str(clip.get("shot_role", "") or "") == "single_focus" else 0.0)
            + (0.06 if clip.get("raw_audio_worthy") else 0.0)
            + min(float(clip.get("peak_window_character_score", 0.0) or 0.0) * 0.08, 0.06)
        )
        enriched["_character_reference_score"] = round(reference_score, 3)
        scored_pool.append(enriched)

    chosen: List[Dict[str, Any]] = []
    for clip in sorted(
        scored_pool,
        key=lambda item: (
            float(item.get("_character_reference_score", 0.0) or 0.0),
            float(item.get("total_score", 0.0) or 0.0),
            float(item.get("duration", 0.0) or 0.0),
        ),
        reverse=True,
    ):
        if any(_clip_similarity(clip, existing) >= 0.72 for existing in chosen):
            continue
        chosen.append(_append_selection_reasons(clip, "main_character_anchor"))
        if len(chosen) >= max(int(top_k or 0), 1):
            break
    return chosen


def _build_highlight_recut_selection_pool(
    candidate_clips: List[Dict[str, Any]],
    target_duration_seconds: int,
    *,
    subtitle_segments: Optional[List[Dict[str, Any]]] = None,
    plot_chunks: Optional[List[Dict[str, Any]]] = None,
    highlight_profile: Optional[Dict[str, Any]] = None,
    select_highlight_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """构造精彩粗剪/短视频候选选择池。
    
    生产者是 timeline/highlight 候选，消费者是前端复核或剪辑组合流程。
    """
    if not candidate_clips:
        return []

    selection_top_k = max(round(target_duration_seconds / 35), 4)
    selector = select_highlight_fn or select_highlight_clips
    desired_pool = max(selection_top_k * 2, round(target_duration_seconds / 18), 8)
    coverage_count = max(min(selection_top_k, 6), 3)

    strongest = selector(candidate_clips, top_k=max(selection_top_k, 4))
    strongest = [_append_selection_reasons(clip, "score_pick") for clip in strongest]

    hero_clips = _select_diverse_clips(candidate_clips, desired_pool, lambda_relevance=0.76)
    hero_clips = [_append_selection_reasons(clip, "diverse_pick") for clip in hero_clips]

    coverage_clips = _build_coverage_clips(candidate_clips, coverage_count)
    coverage_clips = [_append_selection_reasons(clip, "coverage_anchor") for clip in coverage_clips]

    raw_audio_clips = _select_diverse_clips(
        [dict(item) for item in candidate_clips if item.get("raw_audio_worthy")],
        top_k=max(round(selection_top_k / 2), 2),
        lambda_relevance=0.8,
    )
    raw_audio_clips = [_append_selection_reasons(clip, "raw_audio_keep", "raw_audio_anchor") for clip in raw_audio_clips]

    scene_focus_clips = _select_diverse_clips(
        [dict(item) for item in candidate_clips if str(item.get("source", "") or "") == "scene"],
        top_k=max(round(selection_top_k / 3), 1),
        lambda_relevance=0.74,
    )
    scene_focus_clips = [_append_selection_reasons(clip, "scene_anchor") for clip in scene_focus_clips]

    opening_anchor = [
        _append_selection_reasons(clip, "coverage_anchor", "opening_anchor")
        for clip in _pick_anchor_clip(
            candidate_clips,
            story_position_max=0.18,
            allowed_stages={"opening", "setup"},
        )
    ]
    ending_candidates = _pick_anchor_clip(
        candidate_clips,
        story_position_min=0.82,
        allowed_stages={"ending", "climax"},
    ) or _pick_anchor_clip(
        candidate_clips,
        story_position_min=0.78,
        allowed_stages={"reveal", "climax", "ending", "turning_point"},
    )
    ending_anchor = [_append_selection_reasons(clip, "coverage_anchor", "ending_anchor") for clip in ending_candidates]
    climax_raw_anchor = [
        _append_selection_reasons(clip, "raw_audio_keep", "climax_anchor")
        for clip in _pick_anchor_clip(
            candidate_clips,
            story_position_min=0.45,
            allowed_stages={"conflict", "turning_point", "climax", "ending"},
            require_raw_audio=True,
        )
    ]

    chronology_clips = [
        _append_selection_reasons(dict(clip), "chronology_anchor")
        for clip in sorted(
            (dict(item) for item in candidate_clips),
            key=lambda x: (float(x.get("start", 0.0) or 0.0), -float(x.get("total_score", 0.0) or 0.0)),
        )[: max(selection_top_k, 4)]
    ]

    subtitle_segment_map = _build_subtitle_segment_map(subtitle_segments or [])
    main_character_reference = _detect_main_character_reference(candidate_clips)
    peak_window_clips = _build_peak_window_anchors(
        candidate_clips,
        target_duration_seconds,
        subtitle_segment_map=subtitle_segment_map,
        plot_chunks=list(plot_chunks or []),
        highlight_profile=highlight_profile or {},
        main_characters=main_character_reference,
    )
    main_character_clips = _build_main_character_anchor_clips(
        candidate_clips,
        main_character_reference,
        top_k=max(round(selection_top_k / 2), 1),
    )

    return _merge_unique_clips(
        strongest,
        hero_clips,
        coverage_clips,
        raw_audio_clips,
        scene_focus_clips,
        peak_window_clips,
        main_character_clips,
        opening_anchor,
        ending_anchor,
        climax_raw_anchor,
        chronology_clips,
    )


def _merge_unique_clips(*clip_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for group in clip_groups:
        for clip in group or []:
            item = dict(clip)
            clip_id = str(item.get("clip_id", "") or "")
            if not clip_id:
                clip_id = f"{float(item.get('start', 0.0) or 0.0):.3f}_{float(item.get('end', 0.0) or 0.0):.3f}"
            duplicate_index = next(
                (
                    index
                    for index, existing in enumerate(merged)
                    if str(existing.get("clip_id", "") or "") == clip_id or _clip_overlap_ratio(existing, item) >= 0.82
                ),
                -1,
            )
            if duplicate_index >= 0:
                existing = dict(merged[duplicate_index])
                if _clip_specificity_key(item) > _clip_specificity_key(existing):
                    merged[duplicate_index] = _merge_clip_metadata(item, existing)
                else:
                    merged[duplicate_index] = _merge_clip_metadata(existing, item)
                continue
            merged.append(item)
    return sorted(merged, key=lambda x: float(x.get("start", 0.0) or 0.0))


def _build_coverage_clips(candidate_clips: List[Dict[str, Any]], desired_count: int) -> List[Dict[str, Any]]:
    ordered = sorted((dict(item) for item in (candidate_clips or [])), key=lambda x: float(x.get("start", 0.0) or 0.0))
    if not ordered:
        return []

    selected: List[Dict[str, Any]] = []
    used = set()
    target_count = max(int(desired_count or 0), 1)
    total = len(ordered)
    for idx, clip in enumerate(ordered, start=1):
        if clip.get("story_position") is None:
            clip["story_position"] = round((idx - 1) / max(total - 1, 1), 3) if total > 1 else 0.5

    for slot in range(target_count):
        desired_position = round(slot / max(target_count - 1, 1), 3) if target_count > 1 else 0.5
        best = None
        best_score = -1.0
        for clip in ordered:
            clip_id = str(clip.get("clip_id", "") or "")
            if clip_id in used:
                continue
            position_value = clip.get("story_position", 0.5)
            if position_value in (None, ""):
                position_value = 0.5
            position_gap = abs(float(position_value) - desired_position)
            score = float(clip.get("total_score", 0.0) or 0.0) * 0.65 + (1.0 - min(position_gap, 1.0)) * 0.35
            if score > best_score:
                best = clip
                best_score = score
        if best is None:
            continue
        used.add(str(best.get("clip_id", "") or ""))
        selected.append(dict(best))
    return selected


def build_highlight_recut_selection_pool(
    candidate_clips: List[Dict[str, Any]],
    target_duration_seconds: int,
    *,
    subtitle_segments: Optional[List[Dict[str, Any]]] = None,
    plot_chunks: Optional[List[Dict[str, Any]]] = None,
    highlight_profile: Optional[Dict[str, Any]] = None,
    select_highlight_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Build the combined recut pool used before timeline planning."""
    return _build_highlight_recut_selection_pool(
        candidate_clips,
        target_duration_seconds,
        subtitle_segments=subtitle_segments,
        plot_chunks=plot_chunks,
        highlight_profile=highlight_profile,
        select_highlight_fn=select_highlight_fn,
    )


def merge_unique_clips(*clip_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge candidate groups while preserving the most specific metadata."""
    return _merge_unique_clips(*clip_groups)


def clip_overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    """Return overlap ratio relative to the shorter clip duration."""
    return _clip_overlap_ratio(left, right)


def detect_main_character_reference(candidate_clips: List[Dict[str, Any]]) -> List[str]:
    """Expose the main-character heuristic for stats and audits."""
    return _detect_main_character_reference(candidate_clips)


def sorted_unique_values(values: List[Any]) -> List[Any]:
    return _sorted_unique_values(values)


def ordered_unique_values(values: List[Any]) -> List[Any]:
    return _ordered_unique_values(values)


__all__ = [
    "build_highlight_recut_selection_pool",
    "merge_unique_clips",
    "clip_overlap_ratio",
    "detect_main_character_reference",
    "sorted_unique_values",
    "ordered_unique_values",
]
