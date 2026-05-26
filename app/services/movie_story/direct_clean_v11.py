# -*- coding: utf-8 -*-
from __future__ import annotations

"""
direct_clean_v11.py
Single active rule: v11_audio_protected.
01_plot_chunks video_start/video_end is authoritative.
Downstream stages must inherit time. If time changes, raise RuntimeError and write timing_mismatch_report.csv.
"""

import csv
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

from app.services.movie_story import direct_runtime_v11_consolidated as rt

_LAST_PLOT_MAP: Dict[str, Tuple[float, float]] = {}
_LAST_PLOT_ITEMS: List[Dict[str, Any]] = []


def _to_seconds(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", ".")
        if not text:
            return default
        parts = text.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except Exception:
        return default


def _fmt(seconds: float) -> str:
    try:
        return rt.fmt(float(seconds))
    except Exception:
        seconds = max(0.0, float(seconds or 0.0))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds - h * 3600 - m * 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _parse_range(text):
    text = str(text or "").strip()
    if "-" not in text:
        return None, None
    left, right = text.split("-", 1)
    s = _to_seconds(left)
    e = _to_seconds(right)
    if s is None or e is None or e <= s:
        return None, None
    return round(float(s), 3), round(float(e), 3)


def first_list_arg(*args, **kwargs):
    """
    Return the authoritative scene list.

    In the clean single-rule pipeline, 01_plot_chunks is the authoritative
    scene source. Some old pipeline calls may pass later filtered lists into
    evidence/highlight planning functions. If we accept those lists, scenes
    can shrink before scoring.

    Selection order:
    1. Prefer provided list with best overlap with _LAST_PLOT_MAP.
    2. If provided best list is shorter than _LAST_PLOT_ITEMS, use _LAST_PLOT_ITEMS.
    3. Fallback to _LAST_PLOT_ITEMS or first provided list.
    """
    candidates = []
    for x in args:
        if isinstance(x, list):
            candidates.append(x)
    for x in kwargs.values():
        if isinstance(x, list):
            candidates.append(x)

    if not candidates:
        return list(_LAST_PLOT_ITEMS) if _LAST_PLOT_ITEMS else []

    if _LAST_PLOT_MAP:
        best = None
        best_score = -1
        for lst in candidates:
            overlap = 0
            for idx, item in enumerate(lst or [], start=1):
                if not isinstance(item, dict):
                    continue
                keys = [
                    item.get("segment_id"),
                    item.get("scene_id"),
                    item.get("candidate_id"),
                    item.get("id"),
                    f"idx_{idx:04d}",
                ]
                if any(k and str(k) in _LAST_PLOT_MAP for k in keys):
                    overlap += 1
            score = overlap * 100000 + len(lst or [])
            if score > best_score:
                best_score = score
                best = lst

        if _LAST_PLOT_ITEMS and best is not None and len(best or []) < len(_LAST_PLOT_ITEMS):
            return list(_LAST_PLOT_ITEMS)

        if best is not None and best_score > 0:
            return best

    if _LAST_PLOT_ITEMS:
        return list(_LAST_PLOT_ITEMS)

    return candidates[0]


def start_end(item: Dict[str, Any]) -> Tuple[float, float]:
    for sk, ek in (
        ("video_start", "video_end"),
        ("start", "end"),
        ("semantic_start", "semantic_end"),
        ("source_start", "source_end"),
    ):
        try:
            s = item.get(sk)
            e = item.get(ek)
            if s is not None and e is not None and float(e) > float(s):
                return round(float(s), 3), round(float(e), 3)
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)

    for key in ("timestamp", "semantic_timestamp", "source_timestamp"):
        s, e = _parse_range(item.get(key))
        if s is not None and e is not None:
            return s, e

    s = _to_seconds(item.get("start"), 0.0) or 0.0
    e = _to_seconds(item.get("end"), s + 1.0) or (s + 1.0)
    if e <= s:
        e = s + 1.0
    return round(float(s), 3), round(float(e), 3)


def text_of(item: Dict[str, Any]) -> str:
    return str(
        item.get("subtitle_text")
        or item.get("source_text")
        or item.get("main_text_evidence")
        or item.get("text")
        or item.get("narration")
        or ""
    ).strip()


def key_of(item: Dict[str, Any], idx: int) -> str:
    return str(
        item.get("segment_id")
        or item.get("scene_id")
        or item.get("candidate_id")
        or item.get("highlight_id")
        or item.get("id")
        or f"idx_{idx:04d}"
    )


def normalize_item(item: Dict[str, Any], idx: int = 0, candidate_type: str | None = None) -> Dict[str, Any]:
    cur = dict(item or {})
    s, e = start_end(cur)
    ts = f"{_fmt(s)}-{_fmt(e)}"
    text = text_of(cur)
    base = key_of(cur, idx)

    cur["candidate_id"] = cur.get("candidate_id") or base
    cur["segment_id"] = cur.get("segment_id") or base
    cur["scene_id"] = cur.get("scene_id") or base
    cur["id"] = cur.get("id") or base
    if candidate_type:
        cur["candidate_type"] = candidate_type

    cur["start"] = s
    cur["end"] = e
    cur["video_start"] = s
    cur["video_end"] = e
    cur["semantic_start"] = s
    cur["semantic_end"] = e
    cur["source_start"] = s
    cur["source_end"] = e
    cur["duration"] = round(max(0.0, e - s), 3)
    cur["timestamp"] = ts
    cur["semantic_timestamp"] = ts
    cur["source_timestamp"] = ts

    cur["subtitle_text"] = text
    cur["source_text"] = text
    cur["main_text_evidence"] = text
    cur["text"] = text

    score = cur.get("highlight_score")
    if score is None:
        score = cur.get("score")
    if score is None and isinstance(cur.get("scores"), dict):
        score = cur["scores"].get("highlight_score")
    cur["highlight_score"] = score
    cur["score"] = score

    cur["time_policy"] = "v11_scene_video_start_end_authoritative"
    return cur


def normalize_list(items: List[Dict[str, Any]], candidate_type: str | None = None) -> List[Dict[str, Any]]:
    out = []
    for idx, item in enumerate(items or [], start=1):
        cur = normalize_item(item, idx, candidate_type=candidate_type)
        if float(cur["end"]) > float(cur["start"]):
            out.append(cur)
    return out


def _store_plot_map(items: List[Dict[str, Any]]) -> None:
    global _LAST_PLOT_MAP, _LAST_PLOT_ITEMS
    _LAST_PLOT_ITEMS = normalize_list(items, candidate_type="scene")
    _LAST_PLOT_MAP = {}
    for idx, item in enumerate(_LAST_PLOT_ITEMS, start=1):
        base_time = start_end(item)
        for alt in (key_of(item, idx), item.get("scene_id"), item.get("candidate_id"), item.get("segment_id"), item.get("id")):
            if alt:
                _LAST_PLOT_MAP[str(alt)] = base_time


_AUDITED_CLEAN_STAGES = set()


def _audit(stage: str, items: List[Dict[str, Any]], metadata=None, export_clips=None):

    # ===== production movie-story audit policy BEGIN =====
    try:
        from pathlib import Path as _AuditPath
        from app.services.movie_story.audit_policy import should_skip_stage as _ms_should_skip_stage, should_export_clips as _ms_should_export_clips
        _ms_stage_name = str(stage or "")
        if _ms_should_skip_stage(_ms_stage_name):
            return _AuditPath("_skipped")
        if not _ms_should_export_clips(_ms_stage_name):
            export_clips = False
    except Exception as _e:
        logger.warning("操作失败（已捕获）: {}", _e)
    # ===== production movie-story audit policy END =====
    """
    Clean stages are diagnostic tables. Do not export duplicate clips here.

    Reason:
    The legacy visible stages such as 01_plot_chunks / 02_scene_evidence /
    04_story_highlights / 10_before_filter_script_items already export videos.
    Exporting the same clips again under *_v11_clean wastes a lot of time and disk.
    """
    try:
        first_start = 0.0
        last_end = 0.0
        if items:
            first_start = round(float((items[0] or {}).get("start", 0.0) or 0.0), 3)
            last_end = round(float((items[-1] or {}).get("end", 0.0) or 0.0), 3)
        key = (stage, len(items or []), first_start, last_end)

        if stage.endswith("_v11_clean") or "v11_clean" in stage or stage.endswith("_authoritative"):
            if key in _AUDITED_CLEAN_STAGES:
                return None
            _AUDITED_CLEAN_STAGES.add(key)
            if export_clips is None:
                export_clips = False

        return rt.audit_stage(
            stage,
            items or [],
            getattr(rt, "_LAST_VIDEO_PATH", "") or "",
            getattr(rt, "_LAST_OUTPUT_PATH", "") or "",
            metadata or {},
            export_clips=export_clips,
        )
    except Exception as exc:
        logger.warning("v11 clean audit skipped: stage=%s error=%s", stage, exc)
        return None


def _report_path() -> Path:
    try:
        base = rt.audit_base(getattr(rt, "_LAST_VIDEO_PATH", ""), getattr(rt, "_LAST_OUTPUT_PATH", ""))
        return base / f"timing_mismatch_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    except Exception:
        return Path(".") / f"timing_mismatch_{int(time.time())}.csv"


def assert_same_as_plot(stage: str, items: List[Dict[str, Any]]) -> None:
    if not _LAST_PLOT_MAP:
        return

    mismatches = []
    for idx, item in enumerate(items or [], start=1):
        k = key_of(item, idx)
        src = _LAST_PLOT_MAP.get(k)
        if src is None:
            for alt in (item.get("scene_id"), item.get("candidate_id"), item.get("segment_id"), item.get("id")):
                if alt and str(alt) in _LAST_PLOT_MAP:
                    src = _LAST_PLOT_MAP[str(alt)]
                    break
        if src is None:
            continue

        s, e = start_end(item)
        ps, pe = src
        if abs(s - ps) > 0.01 or abs(e - pe) > 0.01:
            mismatches.append({
                "stage": stage,
                "key": k,
                "plot_start": ps,
                "plot_end": pe,
                "current_start": s,
                "current_end": e,
                "delta_start": round(s - ps, 3),
                "delta_end": round(e - pe, 3),
                "text": text_of(item)[:160],
            })

    if mismatches:
        path = _report_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(mismatches[0].keys()))
            writer.writeheader()
            writer.writerows(mismatches)
        raise RuntimeError(f"v11 timing mismatch at {stage}: {len(mismatches)} rows. report={path}")


def build_plot_chunks_v11_clean(segments, *args, **kwargs):
    chunks = rt.build_plot_chunks_v11(segments, *args, **kwargs)
    chunks = normalize_list(chunks, candidate_type="scene")
    _store_plot_map(chunks)
    _audit("01_plot_chunks_v11_clean_authoritative", chunks, {"source": "v11_audio_protected_authoritative"})
    return chunks


def scene_evidence_passthrough(scene_items, *args, **kwargs):
    evidence = normalize_list(scene_items, candidate_type="scene")
    assert_same_as_plot("02_scene_evidence", evidence)
    for item in evidence:
        item["evidence_policy"] = "v11_pass_through_from_scene_candidates_no_retiming"
        item["selected_for_final_story"] = True
    _audit("02_scene_evidence_v11_clean", evidence, {"source": "scene_candidates_passthrough"})
    return evidence


def keep_scene_evidence(scene_evidence, *args, **kwargs):
    evidence = normalize_list(scene_evidence, candidate_type="scene")
    assert_same_as_plot("select_final_story_evidence", evidence)
    for item in evidence:
        item["selected_for_final_story"] = True
        item["final_story_drop_reason"] = ""
        item["stage2_policy"] = "v11_clean_keep_all_no_retiming"
    return evidence


def strength(value="") -> str:
    """
    Highlight strength.

    Explicit config wins:
        movie_story_highlight_strength = all / loose / balanced / strong / strict

    If no explicit config is set, default to loose for debugging the clean
    single-rule pipeline. Do not inherit hidden balanced values from old callers.
    """
    explicit = rt.cfg("movie_story_highlight_strength", None)
    raw = str(explicit if explicit not in (None, "") else "loose").lower().strip()
    aliases = {
        "全部": "all", "全保留": "all",
        "宽松": "loose", "弱": "loose",
        "均衡": "balanced", "中": "balanced",
        "强": "strong",
        "严格": "strict",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in {"all", "loose", "balanced", "strong", "strict"} else "loose"


def threshold_cap(strength_name: str, n: int):
    if strength_name == "all":
        return -1.0, max(n, 1), 1.0
    if strength_name == "strict":
        return float(rt.cfg("movie_story_strict_threshold", 0.68) or 0.68), int(rt.cfg("movie_story_strict_max_keep_count", 35) or 35), 0.0
    if strength_name == "strong":
        return float(rt.cfg("movie_story_strong_threshold", 0.58) or 0.58), int(rt.cfg("movie_story_strong_max_keep_count", 60) or 60), 0.0
    if strength_name == "balanced":
        return float(rt.cfg("movie_story_balanced_threshold", 0.48) or 0.48), int(rt.cfg("movie_story_balanced_max_keep_count", 90) or 90), 0.0
    return float(rt.cfg("movie_story_loose_threshold", 0.34) or 0.34), int(rt.cfg("movie_story_loose_max_keep_count", 500) or 500), float(rt.cfg("movie_story_loose_min_keep_ratio", 0.35) or 0.35)


def _simple_score(item: Dict[str, Any]):
    try:
        return rt.score_item(item)
    except Exception:
        text = text_of(item)
        score = 0.36 if text else 0.1
        return {
            "story_score": score,
            "character_score": 0.3 if text else 0.0,
            "information_score": 0.1,
            "emotion_score": 0.05,
            "visual_score": 0.25,
            "audio_score": 0.05,
            "continuity_score": 0.5,
            "penalty": 0.0,
            "highlight_score": score,
        }, ["fallback_score"]


def build_story_candidates(scene_evidence: List[Dict[str, Any]]):
    """
    Story grouping for audit only. It never rewrites scene boundaries.

    Previous behavior was too coarse: one story could contain several story beats.
    This version splits more locally by:
    - explicit transition words;
    - obvious topic shift between adjacent scenes;
    - accumulated scene count;
    - accumulated text length.

    Important:
    The output story windows are only for story-level audit.
    Final highlight/video windows still use the original scene windows.
    """
    scenes = normalize_list(scene_evidence, candidate_type="scene")
    assert_same_as_plot("03_story_candidates_input", scenes)

    stories = []
    buf = []
    text_len = 0
    last_text = ""

    break_words = [
        "第二天", "几天后", "后来", "与此同时", "另一边", "回到",
        "转眼", "此时", "随后", "晚上", "次日", "另一头",
        "过了一会儿", "没过多久", "这时", "这时候",
    ]
    strong_turn_words = [
        "突然", "没想到", "原来", "真相", "决定", "下令", "发现",
        "质问", "威胁", "救", "杀", "逃", "抓", "跪", "哭",
    ]

    def zh_chars(text):
        return {c for c in str(text or "") if "\u4e00" <= c <= "\u9fff"}

    def jaccard(a, b):
        aa, bb = zh_chars(a), zh_chars(b)
        if not aa or not bb:
            return 1.0
        return len(aa & bb) / max(1, len(aa | bb))

    def has_break_word(text):
        return any(x in text for x in break_words)

    def has_strong_turn(text):
        return any(x in text for x in strong_turn_words)

    def should_start_new_story(cur_text):
        if not buf:
            return False

        scene_count = len(buf)
        similarity = jaccard(last_text, cur_text)

        # Clear transition: split once the previous story has at least some content.
        if has_break_word(cur_text) and text_len >= 40:
            return True

        # Strong plot turn after some accumulated context.
        if has_strong_turn(cur_text) and text_len >= 120 and scene_count >= 2:
            return True

        # Topic drift: the adjacent scene shares too little vocabulary with previous scene.
        # Require enough accumulated text to avoid cutting every short reaction shot.
        if similarity < 0.10 and text_len >= 100 and scene_count >= 2:
            return True

        # Do not allow a story audit group to swallow too many scenes.
        if scene_count >= 4:
            return True

        # Text-based soft cap. This is not a video time rule; it only prevents
        # several story beats from being hidden in one audit story row.
        if text_len >= 220:
            return True

        return False

    def flush():
        nonlocal buf, text_len, last_text
        if not buf:
            return
        idx = len(stories) + 1
        s = float(buf[0]["video_start"])
        e = float(buf[-1]["video_end"])
        ts = f"{_fmt(s)}-{_fmt(e)}"
        text = " ".join(text_of(x) for x in buf if text_of(x)).strip()
        stories.append({
            "candidate_id": f"story_{idx:04d}",
            "candidate_type": "story",
            "story_id": f"story_{idx:04d}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "semantic_start": s,
            "semantic_end": e,
            "source_start": s,
            "source_end": e,
            "duration": round(max(0.0, e - s), 3),
            "timestamp": ts,
            "semantic_timestamp": ts,
            "source_timestamp": ts,
            "scene_ids": [x.get("scene_id") for x in buf],
            "segment_ids": [x.get("segment_id") for x in buf],
            "children_count": len(buf),
            "source_text": text,
            "subtitle_text": text,
            "text": text,
            "merge_policy": "v11_story_merge_audit_only_finer_semantic_groups_no_retiming",
        })
        buf = []
        text_len = 0
        last_text = ""

    for scene in scenes:
        txt = text_of(scene)
        if should_start_new_story(txt):
            flush()
        buf.append(scene)
        text_len += len(txt)
        if txt:
            last_text = txt

    flush()
    _audit("03_story_candidates_v11_clean", stories, {"source": "finer_story_merge_audit_only_no_retiming"})
    return stories


def extract_highlights(scene_evidence, cut_points=None, highlight_selectivity="loose", *args, **kwargs):
    """Production highlight selection + existing full-plot narration chain.

    This function owns only selection orchestration. Final narration is delegated
    to app.services.movie_story.narration_engine, which calls the existing
    AIVideoGPT narration generator instead of using a simplified prompt.
    """
    from app.services.movie_story import highlight_selection
    from app.services.movie_story import narration_engine

    def _cfg_float(key, default):
        try:
            from app.config import config as app_config
            app = getattr(app_config, "app", None)
            if isinstance(app, dict) and key in app:
                return float(app.get(key, default))
            if app is not None and hasattr(app, key):
                return float(getattr(app, key))
            if isinstance(app_config, dict):
                if key in app_config:
                    return float(app_config.get(key, default))
                if isinstance(app_config.get("app"), dict):
                    return float(app_config["app"].get(key, default))
        except Exception as _e:
            logger.debug("数值转换失败，跳过: {}", _e)
        return float(default)

    def _cfg_int(key, default):
        try:
            return int(round(_cfg_float(key, default)))
        except Exception:
            return int(default)

    def _cfg_str(key, default=""):
        try:
            from app.config import config as app_config
            app = getattr(app_config, "app", None)
            if isinstance(app, dict) and key in app:
                return str(app.get(key, default) or default)
            if app is not None and hasattr(app, key):
                return str(getattr(app, key) or default)
            if isinstance(app_config, dict):
                if key in app_config:
                    return str(app_config.get(key, default) or default)
                if isinstance(app_config.get("app"), dict):
                    return str(app_config["app"].get(key, default) or default)
        except Exception as _e:
            logger.debug("配置字段读取失败，返回 default: {}", _e)
        return str(default or "")

    scenes = normalize_list(scene_evidence, candidate_type="scene")
    assert_same_as_plot("extract_typed_highlights_input", scenes)
    stories = build_story_candidates(scenes)
    st = strength(highlight_selectivity)

    scored_scenes = []
    for idx, scene in enumerate(scenes, start=1):
        cur = normalize_item(scene, idx, candidate_type="scene")
        scores, reasons = _simple_score(cur)
        score = float(scores.get("highlight_score") or 0.0)
        cur.update({
            "scores": scores,
            "highlight_score": score,
            "score": score,
            "selection_reasons": reasons,
            "selected": False,
            "drop_reason": "not_typed_yet",
            "highlight_strength": st,
        })
        scored_scenes.append(cur)

    min_conf = _cfg_float("movie_story_typed_min_confidence", 0.52)
    fallback_conf = _cfg_float("movie_story_typed_fallback_confidence", 0.45)
    min_base = _cfg_float("movie_story_typed_min_base_score", 0.18)
    target_items = _cfg_int("movie_story_typed_target_items", 45)
    quotas = highlight_selection.parse_type_quotas(_cfg_str("movie_story_typed_type_quotas", ""))

    typed_candidates = highlight_selection.build_typed_candidates(
        scored_scenes,
        stories,
        min_confidence=min_conf,
        fallback_confidence=fallback_conf,
    )
    audited, meta = highlight_selection.select_by_type_pools(
        typed_candidates,
        quotas=quotas,
        min_confidence=min_conf,
        fallback_confidence=fallback_conf,
        min_base_score=min_base,
        target_items=target_items,
    )
    audited = highlight_selection.sort_chronological(audited)
    selected_clips = highlight_selection.merge_selected_records(audited)
    selected_clips = highlight_selection.sort_chronological(selected_clips)
    meta.update({
        "source_scene_count": len(scenes),
        "source_story_count": len(stories),
        "selected_clip_count": len(selected_clips),
        "selected_type_distribution": highlight_selection.type_distribution(selected_clips),
        "selection_policy": "typed_highlight_pools",
        "time_policy": "no_duration_cap_no_density_gap",
        "output_order": "chronological_movie_time",
        "narration_engine": "existing_full_plot_narration_chain",
    })
    _audit("04_typed_highlight_candidates", audited, meta, export_clips=False)

    highlights = []
    for idx, src in enumerate(selected_clips, start=1):
        s, e = start_end(src)
        s, e = float(s or 0.0), float(e or 0.0)
        ts = f"{_fmt(s)}-{_fmt(e)}"
        scene_id = src.get("scene_id") or src.get("segment_id") or src.get("candidate_id") or f"scene_{idx:04d}"
        story_id = src.get("parent_story_id") or src.get("story_id")
        scores = src.get("scores") or {}
        text = text_of(src)
        score = float(src.get("highlight_score") or scores.get("highlight_score") or src.get("score") or 0.0)
        details = src.get("type_details") or []
        hints = []
        for detail in details:
            hint = detail.get("narration_hint")
            if hint and hint not in hints:
                hints.append(hint)
        highlights.append({
            "highlight_id": f"highlight_{idx:03d}",
            "highlight_rank": src.get("selection_rank") or idx,
            "selection_rank": src.get("selection_rank"),
            "narration_order": idx,
            "movie_order": idx,
            "candidate_type": "highlight",
            "story_id": story_id,
            "parent_story_id": story_id,
            "parent_story_start": src.get("parent_story_start"),
            "parent_story_end": src.get("parent_story_end"),
            "parent_story_text": src.get("parent_story_text") or src.get("parent_story_summary"),
            "scene_ids": [scene_id],
            "segment_ids": [scene_id],
            "evidence_ids": [scene_id],
            "scene_id": scene_id,
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "semantic_start": s,
            "semantic_end": e,
            "source_start": s,
            "source_end": e,
            "duration": round(max(0.0, e - s), 3),
            "timestamp": ts,
            "semantic_timestamp": ts,
            "source_timestamp": ts,
            "source_text": text,
            "subtitle_text": text,
            "text": text,
            "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [],
            "highlight_type": src.get("highlight_type"),
            "highlight_type_key": src.get("highlight_type_key"),
            "highlight_types": src.get("highlight_types") or [src.get("highlight_type")],
            "highlight_type_keys": src.get("highlight_type_keys") or [src.get("highlight_type_key")],
            "type_confidence": src.get("type_confidence"),
            "type_details": details,
            "type_evidence": src.get("type_evidence") or [],
            "evidence_text": src.get("evidence_text") or text[:120],
            "narration_hint": "；".join(hints) if hints else src.get("narration_hint"),
            "highlight_reasons": src.get("selection_reasons") or src.get("highlight_reasons") or [],
            "highlight_score": score,
            "score": score,
            "scores": scores,
            "llm_highlight_selected": False,
            "highlight_filter_selected": True,
            "highlight_selectivity": highlight_selectivity,
            "highlight_strength": st,
            "selected": True,
            "selection_policy": "typed_highlight_pools",
            "time_policy": "no_duration_cap_no_density_gap",
            "narration_policy": "existing_full_plot_narration_chain_after_selection",
        })

    highlights = highlight_selection.sort_chronological(highlights)
    _audit("05_selected_highlights", highlights, {
        "policy": "typed_highlight_pools_no_duration_density_limit",
        "strength": st,
        "selected": len(highlights),
        "source_story_count": len(stories),
        "source_scene_count": len(scenes),
        "typed_candidate_count": len(audited),
        "selected_type_distribution": highlight_selection.type_distribution(highlights),
        "duration_cap": None,
        "min_gap_seconds": None,
        "output_order": "chronological_movie_time",
        "narration_next_step": "06_scene_evidence_for_narration -> 07_narration_script",
    })

    narration = narration_engine.generate_from_selected_highlights(
        highlights,
        scenes=scenes,
        stories=stories,
        options={
            "style": _cfg_str("movie_story_narration_style", ""),
            "frontend_style": _cfg_str("movie_story_frontend_narration_style", ""),
            "api_key": _cfg_str("movie_story_llm_api_key", ""),
            "base_url": _cfg_str("movie_story_llm_base_url", ""),
            "model": _cfg_str("movie_story_llm_model", ""),
        },
    )
    _audit("06_scene_evidence_for_narration", narration.get("scene_evidence") or [], narration.get("metadata") or {}, export_clips=False)
    _audit("07_narration_script", narration.get("script_items") or [], narration.get("metadata") or {}, export_clips=False)
    if narration.get("status") != "ok":
        try:
            import logging
            logging.getLogger(__name__).warning("movie-story narration engine failed: %s", narration.get("error"))
        except Exception as _e:
            logger.warning("操作失败（已捕获）: {}", _e)
    return highlights







def script_items_no_retime(items, candidate_type="script_item"):
    out = normalize_list(items, candidate_type=candidate_type)
    assert_same_as_plot("script_items", out)
    for item in out:
        item["script_item_policy"] = "v11_clean_pass_through_no_retiming"
        item["narration"] = item.get("narration") or text_of(item)
        item["OST"] = item.get("OST", 2)
    return out
