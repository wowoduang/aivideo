from __future__ import annotations

"""Composition-plan builders for the highlight-edit pipeline.

Stage-K extraction target.  This module turns planned clips and narration matches
into a CompositionPlan-like dictionary.  It owns grouped narrated shots,
intra-scene subshots, narration splitting, audio-mode decisions, and timeline
cursor assignment.
"""

from datetime import datetime
from typing import Any, Dict, List

def _split_text_clauses(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    buffer = raw
    for splitter in ["。", "！", "？", ".", "!", "?", "；", ";", "，", ",", "：", ":"]:
        buffer = buffer.replace(splitter, splitter + "\n")
    return [item.strip() for item in buffer.splitlines() if item.strip()]

def _split_narration_text_for_group(text: str, group_size: int) -> List[str]:
    raw = str(text or "").strip()
    if group_size <= 1 or not raw:
        return [raw]

    clauses = _split_text_clauses(raw)
    if not clauses:
        return [raw]

    while len(clauses) < group_size:
        longest_index = max(range(len(clauses)), key=lambda idx: len(clauses[idx]))
        longest = clauses[longest_index]
        if len(longest) <= 10:
            break
        midpoint = max(len(longest) // 2, 1)
        left = longest[:midpoint].strip("，,；;：: ")
        right = longest[midpoint:].strip("，,；;：: ")
        if not left or not right:
            break
        clauses = clauses[:longest_index] + [left, right] + clauses[longest_index + 1 :]

    if len(clauses) <= group_size:
        return clauses + [""] * (group_size - len(clauses))

    parts: List[str] = []
    cursor = 0
    for idx in range(group_size):
        remaining_clauses = len(clauses) - cursor
        remaining_slots = group_size - idx
        take = max((remaining_clauses + remaining_slots - 1) // remaining_slots, 1)
        piece = "".join(clauses[cursor : cursor + take]).strip()
        parts.append(piece)
        cursor += take
    return parts

def _pick_keyframe_centers(clip: Dict[str, Any], desired_count: int) -> List[float]:
    start = float(clip.get("start", 0.0) or 0.0)
    end = float(clip.get("end", start) or start)
    duration = max(end - start, 0.5)
    count = max(min(int(desired_count or 1), max(int(duration / 1.1), 1), 4), 1)

    candidates = []
    for value in clip.get("keyframe_candidates") or []:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            continue
        if start <= timestamp <= end:
            candidates.append(round(timestamp, 3))
    candidates = sorted(dict.fromkeys(candidates))

    if not candidates:
        return [round(start + duration * ((idx + 0.5) / count), 3) for idx in range(count)]
    if len(candidates) <= count:
        return candidates

    selected: List[float] = []
    for slot in range(count):
        target_index = round(slot * (len(candidates) - 1) / max(count - 1, 1))
        selected.append(candidates[target_index])
    return sorted(dict.fromkeys(selected))

def _pick_boundary_points(clip: Dict[str, Any], desired_count: int) -> List[float]:
    start = float(clip.get("start", 0.0) or 0.0)
    end = float(clip.get("end", start) or start)
    raw_points = []
    for value in clip.get("boundary_candidates") or []:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            continue
        if start + 0.35 <= timestamp <= end - 0.35:
            raw_points.append(round(timestamp, 3))
    points = sorted(dict.fromkeys(raw_points))
    target = max(min(int(desired_count or 1) - 1, 3), 0)
    if target <= 0 or not points:
        return []
    if len(points) <= target:
        return points

    selected: List[float] = []
    for slot in range(target):
        desired_position = (slot + 1) / (target + 1)
        best_point = min(points, key=lambda point: abs(((point - start) / max(end - start, 0.001)) - desired_position))
        selected.append(best_point)
    return sorted(dict.fromkeys(selected))

def _build_intra_scene_subshots(clip: Dict[str, Any], desired_count: int) -> List[Dict[str, Any]]:
    start = float(clip.get("start", 0.0) or 0.0)
    end = float(clip.get("end", start) or start)
    duration = max(end - start, 0.5)
    if duration < 3.4:
        return [dict(clip)]

    boundary_points = _pick_boundary_points(clip, desired_count)
    if boundary_points:
        boundaries = [start] + boundary_points + [end]
    else:
        centers = _pick_keyframe_centers(clip, desired_count)
        if len(centers) <= 1:
            return [dict(clip)]
        boundaries = [start]
        for left, right in zip(centers[:-1], centers[1:]):
            boundaries.append(round((left + right) / 2.0, 3))
        boundaries.append(end)

    if len(boundaries) <= 2:
        return [dict(clip)]

    subshots: List[Dict[str, Any]] = []
    for idx, (sub_start, sub_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        if sub_end - sub_start < 0.45:
            continue
        subshot = dict(clip)
        subshot["clip_id"] = f"{str(clip.get('clip_id', 'clip'))}__shot_{idx:02d}"
        subshot["start"] = round(sub_start, 3)
        subshot["end"] = round(sub_end, 3)
        subshot["duration"] = round(max(sub_end - sub_start, 0.5), 3)
        subshot["selection_reason"] = list(
            dict.fromkeys(list(subshot.get("selection_reason") or []) + ["intra_scene_cut"])
        )
        subshot["tags"] = list(dict.fromkeys(list(subshot.get("tags") or []) + ["intra_scene_cut"]))
        subshot["prevent_merge"] = True
        subshot["parent_clip_id"] = clip.get("clip_id", "")
        subshot["subshot_index"] = idx
        subshots.append(subshot)

    return subshots or [dict(clip)]

def _expand_group_with_intra_scene_subshots(match: Dict[str, Any], clip_group: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not clip_group:
        return []
    if len(clip_group) > 1:
        return [dict(item) for item in clip_group]

    rhythm = dict(match.get("rhythm_config") or {})
    preferred_group_size = max(int(rhythm.get("preferred_group_size", 2) or 2), 1)
    anchor = dict(clip_group[0])
    if str(anchor.get("source", "") or "") != "scene":
        return [anchor]
    if preferred_group_size <= 1:
        return [anchor]

    expanded = _build_intra_scene_subshots(anchor, min(preferred_group_size, 3))
    return expanded if len(expanded) > 1 else [anchor]

def _build_composition_plan(
    *,
    mode: str,
    video_path: str,
    movie_title: str,
    target_duration_seconds: int,
    visual_mode: str,
    highlight_profile: Dict[str, Any],
    highlight_capabilities: Dict[str, Any],
    candidate_stats: Dict[str, Any],
    selected_clips: List[Dict[str, Any]],
    narration_text: str,
    narration_audio_path: str,
    prefer_raw_audio: bool,
    narration_matches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """构造短视频剪辑合成计划。
    
    该函数连接候选片段、镜头时长、字幕/音频材料和导出计划；
    后续应拆成素材收集、镜头分配、时长规划和输出 schema 组装。
    """
    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    if mode == "narrated_highlight_edit" and narration_matches:
        for match_idx, match in enumerate(narration_matches, start=1):
            clip_group = list(match.get("clip_group") or [])
            if not clip_group and match.get("clip"):
                clip_group = [dict(match.get("clip") or {})]
            if bool(match.get("preserve_sentence_boundary")):
                clip_group = [dict(clip_group[0])] if clip_group else []
            else:
                clip_group = _expand_group_with_intra_scene_subshots(match, clip_group)
            narration = str(match.get("text", "") or "")
            group_narrations = _split_narration_text_for_group(narration, len(clip_group))
            shot_durations = _plan_group_shot_durations(match, clip_group)
            for group_idx, (clip, shot_duration) in enumerate(zip(clip_group, shot_durations), start=1):
                shot_narration = group_narrations[group_idx - 1] if group_idx - 1 < len(group_narrations) else ""
                start = round(float(clip.get("start", 0.0) or 0.0), 3)
                original_end = round(float(clip.get("end", start) or start), 3)
                duration = round(max(float(shot_duration or 0.0), 0.5), 3)
                end = round(min(original_end, start + duration), 3)
                duration = round(max(end - start, 0.5), 3)
                audio_plan = _decide_group_audio_plan(
                    match=match,
                    clip=clip,
                    group_idx=group_idx,
                    group_size=len(clip_group),
                    prefer_raw_audio=prefer_raw_audio,
                    has_narration=bool(shot_narration),
                )
                reasons = list(clip.get("selection_reason") or [])
                if match.get("story_stage"):
                    reasons.append(f"match:{match['story_stage']}")
                if match.get("match_strategy"):
                    reasons.append(f"map:{match['match_strategy']}")
                if match.get("rhythm_profile"):
                    reasons.append(f"rhythm:{match['rhythm_profile']}")
                reasons.append(f"audio:{audio_plan['strategy']}")
                if group_idx > 1:
                    reasons.append("group_follow_shot")
                else:
                    reasons.append("group_anchor_shot")

                segments.append(
                    {
                        "segment_id": f"seg_{match_idx:04d}_{group_idx:02d}",
                        "video_start": start,
                        "video_end": end,
                        "timeline_start": round(cursor, 3),
                        "timeline_end": round(cursor + duration, 3),
                        "audio_mode": audio_plan["audio_mode"],
                        "narration_text": shot_narration if audio_plan["carry_narration"] else "",
                        "narration_audio_path": narration_audio_path if shot_narration and audio_plan["carry_narration"] else "",
                        "selection_reason": reasons,
                        "picture": str(clip.get("scene_summary", "") or clip.get("subtitle_text", "") or ""),
                        "audio_strategy": audio_plan["strategy"],
                        "source_clip_id": clip.get("clip_id", f"clip_{match_idx:04d}_{group_idx:02d}"),
                        "clip_source": str(clip.get("source", "") or ""),
                        "source_scene_id": str(clip.get("source_scene_id", "") or ""),
                        "raw_audio_worthy": bool(clip.get("raw_audio_worthy")),
                        "parent_clip_id": clip.get("parent_clip_id", ""),
                        "subshot_index": clip.get("subshot_index"),
                        "trim_strategy": str(clip.get("trim_strategy", "") or ""),
                        "original_duration": clip.get("original_duration", clip.get("duration", duration)),
                        "planned_duration": duration,
                        "match_score": match.get("match_score"),
                        "match_strategy": match.get("match_strategy", ""),
                    }
                )
                cursor += duration
        return {
            "mode": mode,
            "video_path": video_path,
            "movie_title": movie_title,
            "target_duration_seconds": target_duration_seconds,
            "segments": segments,
            "audio_tracks": {
                "bgm_path": "",
                "narration_path": narration_audio_path or "",
                "keep_raw_audio": bool(prefer_raw_audio),
            },
            "metadata": {
                "selected_clip_count": len(selected_clips),
                "generated_at": datetime.now().isoformat(),
                "narrated_match_count": len(narration_matches or []),
                "has_external_narration": bool(str(narration_text or "").strip()),
                "visual_mode": visual_mode,
                "highlight_profile": dict(highlight_profile or {}),
                "highlight_capabilities": dict(highlight_capabilities or {}),
                "candidate_stats": dict(candidate_stats or {}),
                "grouped_match_mode": True,
                "rhythm_shot_mode": True,
            },
        }

    matched_by_clip_id = {
        str(item.get("clip_id") or ""): item for item in (narration_matches or []) if item.get("clip_id")
    }

    for idx, clip in enumerate(selected_clips, start=1):
        start = round(float(clip.get("start", 0.0) or 0.0), 3)
        end = round(float(clip.get("end", start) or start), 3)
        duration = round(max(end - start, 0.5), 3)
        matched = matched_by_clip_id.get(str(clip.get("clip_id", "") or ""))
        narration = str((matched or {}).get("text", "") or "")
        audio_plan = _decide_group_audio_plan(
            match=matched or {},
            clip=clip,
            group_idx=1,
            group_size=1,
            prefer_raw_audio=prefer_raw_audio,
            has_narration=bool(narration),
        )

        if mode == "narrated_highlight_edit":
            audio_mode = audio_plan["audio_mode"]
        else:
            audio_mode = "raw"

        reasons = list(clip.get("selection_reason") or [])
        if matched and matched.get("story_stage"):
            reasons.append(f"match:{matched['story_stage']}")
        if matched and matched.get("match_strategy"):
            reasons.append(f"map:{matched['match_strategy']}")
        if mode == "narrated_highlight_edit":
            reasons.append(f"audio:{audio_plan['strategy']}")

        segments.append(
            {
                "segment_id": f"seg_{idx:04d}",
                "video_start": start,
                "video_end": end,
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "audio_mode": audio_mode,
                "narration_text": narration if audio_plan["carry_narration"] else "",
                "narration_audio_path": narration_audio_path if narration and audio_plan["carry_narration"] else "",
                "selection_reason": reasons,
                "picture": str(clip.get("scene_summary", "") or clip.get("subtitle_text", "") or ""),
                "audio_strategy": audio_plan["strategy"],
                "source_clip_id": clip.get("clip_id", f"clip_{idx:04d}"),
                "clip_source": str(clip.get("source", "") or ""),
                "source_scene_id": str(clip.get("source_scene_id", "") or ""),
                "raw_audio_worthy": bool(clip.get("raw_audio_worthy")),
                "parent_clip_id": clip.get("parent_clip_id", ""),
                "subshot_index": clip.get("subshot_index"),
                "trim_strategy": str(clip.get("trim_strategy", "") or ""),
                "original_duration": clip.get("original_duration", clip.get("duration", duration)),
                "planned_duration": clip.get("planned_duration", duration),
                "match_score": (matched or {}).get("match_score"),
                "match_strategy": (matched or {}).get("match_strategy", ""),
            }
        )
        cursor += duration

    return {
        "mode": mode,
        "video_path": video_path,
        "movie_title": movie_title,
        "target_duration_seconds": target_duration_seconds,
        "segments": segments,
        "audio_tracks": {
            "bgm_path": "",
            "narration_path": narration_audio_path or "",
            "keep_raw_audio": bool(prefer_raw_audio),
        },
        "metadata": {
            "selected_clip_count": len(selected_clips),
            "generated_at": datetime.now().isoformat(),
            "narrated_match_count": len(narration_matches or []),
            "has_external_narration": bool(str(narration_text or "").strip()),
            "visual_mode": visual_mode,
            "highlight_profile": dict(highlight_profile or {}),
            "highlight_capabilities": dict(highlight_capabilities or {}),
            "candidate_stats": dict(candidate_stats or {}),
        },
    }

def _plan_group_shot_durations(match: Dict[str, Any], clip_group: List[Dict[str, Any]]) -> List[float]:
    """规划一组候选片段内部镜头时长。
    
    该 helper 只做剪辑节奏和时长分配，不改变上游候选语义。
    """
    if not clip_group:
        return []

    rhythm = dict(match.get("rhythm_config") or {})
    profile = str(match.get("rhythm_profile") or rhythm.get("profile") or "balanced")
    target_seconds = float(match.get("target_seconds", 0.0) or 0.0)
    min_shot = float(rhythm.get("min_shot_seconds", 1.2) or 1.2)
    max_shot = float(rhythm.get("max_shot_seconds", 3.0) or 3.0)
    has_scene_refined = any("scene_refined" in set(str(tag) for tag in (clip.get("tags") or [])) for clip in clip_group)
    scene_count = sum(1 for clip in clip_group if str(clip.get("source", "") or "") == "scene")
    if has_scene_refined and len(clip_group) > 1:
        min_shot = min(min_shot, 1.0 if profile in {"fast", "pivot"} else 1.15)
        max_shot = min(max_shot, 2.4 if profile in {"fast", "pivot"} else 2.8)
    available_total = sum(max(float(item.get("duration", 0.0) or 0.0), 0.5) for item in clip_group)
    if target_seconds <= 0.0:
        target_seconds = available_total
    budget = min(available_total, max(target_seconds * (1.0 if has_scene_refined else 1.05), min_shot * len(clip_group)))

    if profile == "fast":
        weights = [0.5, 0.3, 0.2]
    elif profile == "pivot":
        weights = [0.58, 0.27, 0.15]
    elif profile == "steady":
        weights = [0.72, 0.28, 0.0]
    elif profile == "resolve":
        weights = [0.68, 0.32, 0.0]
    else:
        weights = [0.62, 0.24, 0.14]

    weights = weights[: len(clip_group)]
    if not weights:
        weights = [1.0]
    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0 for _ in clip_group]
        total_weight = float(len(weights))
    normalized = [w / total_weight for w in weights]

    if scene_count >= max(1, len(clip_group) - 1) and len(clip_group) > 1:
        clip_weights = []
        for idx, clip in enumerate(clip_group):
            base = normalized[min(idx, len(normalized) - 1)]
            source_bonus = 0.08 if str(clip.get("source", "") or "") == "scene" else -0.04
            score_bonus = min(float(clip.get("total_score", 0.0) or 0.0), 1.0) * 0.08
            clip_weights.append(max(base + source_bonus + score_bonus, 0.05))
        weight_total = sum(clip_weights) or float(len(clip_weights))
        normalized = [weight / weight_total for weight in clip_weights]

    planned: List[float] = []
    for idx, clip in enumerate(clip_group):
        available = max(float(clip.get("duration", 0.0) or 0.0), 0.5)
        weighted = budget * normalized[min(idx, len(normalized) - 1)]
        if available < min_shot:
            planned.append(round(available, 3))
            continue
        duration = min(available, max_shot, max(min_shot, weighted))
        planned.append(round(duration, 3))

    return planned

def _decide_group_audio_plan(
    *,
    match: Dict[str, Any],
    clip: Dict[str, Any],
    group_idx: int,
    group_size: int,
    prefer_raw_audio: bool,
    has_narration: bool,
) -> Dict[str, Any]:
    stage = str(match.get("story_stage", "") or "")
    rhythm = str(match.get("rhythm_profile", "") or "")
    raw_worthy = bool(clip.get("raw_audio_worthy"))
    short_anchor = float(match.get("target_seconds", 0.0) or 0.0) <= 3.0

    if not has_narration:
        return {
            "audio_mode": "raw",
            "carry_narration": False,
            "strategy": "raw_follow",
        }

    if prefer_raw_audio and raw_worthy and (stage in {"conflict", "climax", "reveal", "ending"} or rhythm in {"fast", "pivot"}):
        return {
            "audio_mode": "ducked_raw",
            "carry_narration": True,
            "strategy": "ducked_narration",
        }

    if prefer_raw_audio and raw_worthy and short_anchor and group_size > 1:
        return {
            "audio_mode": "ducked_raw",
            "carry_narration": True,
            "strategy": "keyline_ducked",
        }

    return {
        "audio_mode": "tts",
        "carry_narration": True,
        "strategy": "clean_tts",
    }


# Public names for new callers; underscored names above remain for old tests and
# to preserve compatibility with legacy imports during the transition.
build_composition_plan = _build_composition_plan
plan_group_shot_durations = _plan_group_shot_durations
decide_group_audio_plan = _decide_group_audio_plan
split_narration_text_for_group = _split_narration_text_for_group
build_intra_scene_subshots = _build_intra_scene_subshots
expand_group_with_intra_scene_subshots = _expand_group_with_intra_scene_subshots
