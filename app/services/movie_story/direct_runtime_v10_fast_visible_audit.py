
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
direct_runtime_v10_fast_visible_audit

修复 v9 的问题：
- v9 先写 active marker，然后才调用 v5.build_plot_chunks_v5。
- v5 可能会先跑整片 ffmpeg scene detect / 旧内部审计，导致用户长时间只能看到 active 一个文件。
- v10 不再调用 v5.build_plot_chunks_v5 生成 shot，而是在本文件内完成：
  1) 先写 00_active_direct_runtime_v10；
  2) 立刻写 00b_start_shot_detection_v10；
  3) 自己检测 ffmpeg shot 边界 + 字幕停顿边界；
  4) 立刻写 00c_boundary_summary_v10；
  5) 输出 01_shot_candidates_v10；
  6) 合并 02_scene_candidates_v10；
  7) 输出 04a_scored_candidates_v10，score 同步 highlight_score。

重要设计：
- manifest/csv 先写，再导出 clips；这样即使 clips 很多、导出很慢，也能先看到表。
- marker 阶段不导出 0.001s 视频，避免出现一个无意义小片段。
"""

import csv
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

from app.services.movie_story import direct_runtime_v5 as v5


# ---------------- config/time helpers ----------------

def cfg(key: str, default=None):
    return v5.cfg(key, default)

def cfg_bool(key: str, default: bool = False) -> bool:
    return v5.cfg_bool(key, default)

def cfg_float(key: str, default: float) -> float:
    return v5.cfg_float(key, default)

def cfg_int(key: str, default: int) -> int:
    return v5.cfg_int(key, default)

def fmt(seconds: float) -> str:
    return v5.fmt_time(seconds)

def safe(value: Any) -> str:
    return str(value or "segment").replace("/", "_").replace("\\", "_")[:60]

def parse_time(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        parts = text.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except Exception:
        return None

def resolve_video_path(kwargs=None) -> str:
    return v5.resolve_video_path(kwargs or {})

def resolve_output_path(kwargs=None) -> str:
    return v5.resolve_output_script_path(kwargs or {})


# ---------------- audit, visible in old folder ----------------

def _audit_base(video_path: str = "", output_path: str = "") -> Path:
    if video_path and Path(video_path).exists():
        return Path(video_path).parent / "_movie_story_pipeline_audit_clips"
    if output_path:
        return Path(output_path).parent / "_movie_story_pipeline_audit_clips"
    cwd = Path.cwd()
    guess = cwd.parent / (cwd.name + "-workspace") / "frontend_uploads" / "video"
    if guess.exists():
        return guess / "_movie_story_pipeline_audit_clips"
    return Path(".-workspace") / "debug" / "_movie_story_pipeline_audit_clips"

def _run_dir(video_path: str = "", output_path: str = "") -> Path:
    rid = os.environ.get("AIVIDEO_PIPELINE_AUDIT_RUN_ID") or os.environ.get("AIVIDEO_AUDIT_RUN_ID")
    if not rid:
        rid = time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_PIPELINE_AUDIT_RUN_ID"] = rid
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = rid
    d = _audit_base(video_path, output_path) / rid
    d.mkdir(parents=True, exist_ok=True)
    return d

def _start_end(item: Dict[str, Any]):
    s = item.get("video_start", item.get("start", item.get("semantic_start", 0.0)))
    e = item.get("video_end", item.get("end", item.get("semantic_end", s)))
    try:
        s = float(s or 0.0)
        e = float(e or s)
    except Exception:
        s, e = 0.0, 0.0
    return s, e

def _row(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    s, e = _start_end(item)
    scores = item.get("scores") or {}
    hscore = item.get("highlight_score")
    if hscore is None:
        hscore = scores.get("highlight_score")
    if hscore is None:
        hscore = item.get("score")
    return {
        "idx": idx,
        "id": item.get("candidate_id") or item.get("highlight_id") or item.get("segment_id") or idx,
        "start": s,
        "end": e,
        "duration": round(max(0.0, e - s), 3),
        "timestamp": item.get("timestamp") or f"{fmt(s)}-{fmt(e)}",
        "candidate_type": item.get("candidate_type"),
        "selected": item.get("selected"),
        "drop_reason": item.get("drop_reason"),
        "plot_function": item.get("plot_function"),
        "score": hscore,
        "highlight_score": hscore,
        "story_score": scores.get("story_score", item.get("story_score")),
        "character_score": scores.get("character_score", item.get("character_score")),
        "information_score": scores.get("information_score", item.get("information_score")),
        "emotion_score": scores.get("emotion_score", item.get("emotion_score")),
        "visual_score": scores.get("visual_score", item.get("visual_score")),
        "audio_score": scores.get("audio_score", item.get("audio_score")),
        "continuity_score": scores.get("continuity_score", item.get("continuity_score")),
        "penalty": scores.get("penalty", item.get("penalty")),
        "children_count": len(item.get("children") or item.get("source_shot_ids") or item.get("source_scene_ids") or []),
        "reasons": json.dumps(item.get("selection_reasons") or item.get("highlight_reasons") or item.get("reasons") or [], ensure_ascii=False),
        "text": str(item.get("subtitle_text") or item.get("source_text") or item.get("text") or "")[:500],
    }

def audit_stage(stage: str, items: List[Dict[str, Any]], video_path: str = "", output_path: str = "", metadata=None, export_clips: Optional[bool] = None):
    run = _run_dir(video_path, output_path)
    stage_dir = run / stage
    clips_dir = stage_dir / "clips"
    stage_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    rows = [_row(item, idx) for idx, item in enumerate(items or [], start=1)]
    total = round(sum(float(r.get("duration") or 0.0) for r in rows), 3)

    manifest = {
        "stage": stage,
        "count": len(items or []),
        "exported": 0,
        "total_duration": total,
        "metadata": metadata or {},
        "items": rows,
    }

    # 关键：先写 manifest/csv，再慢慢导出 clips。
    (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    idx_path = run / "_stage_index.json"
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
    except Exception:
        index = []
    index.append({"stage": stage, "dir": str(stage_dir), "count": len(items or []), "exported": 0, "total_duration": total})
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    if export_clips is None:
        export_clips = cfg_bool("movie_story_audit_export_clips", True)

    # marker / summary 阶段默认不导出无意义 clips。
    if stage.startswith("00"):
        export_clips = False

    if not export_clips or not video_path or not Path(video_path).exists():
        logger.warning("movie_story v10 audit manifest only: %s count=%s dir=%s", stage, len(items or []), stage_dir)
        return stage_dir

    max_clips = cfg_int("movie_story_audit_max_clips_per_stage", 560)
    exported = 0
    for idx, (item, r) in enumerate(zip(items or [], rows), start=1):
        if idx > max_clips:
            break
        s, e = _start_end(item)
        dur = max(0.0, e - s)
        if dur < 0.5:
            continue
        clip = clips_dir / f"{idx:03d}_{safe(r['id'])}_{s:.3f}_{e:.3f}.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{s:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "25", "-c:a", "aac",
            "-b:a", "96k", "-movflags", "+faststart", str(clip),
        ]
        try:
            ok = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=max(30, int(dur) + 30)).returncode == 0
        except Exception:
            ok = False
        if ok:
            exported += 1

    # 更新 index/manifest 的 exported 数。
    manifest["exported"] = exported
    (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
        if index:
            index[-1]["exported"] = exported
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 清理操作，忽略异常

    logger.warning("movie_story v10 audit: %s count=%s exported=%s dir=%s", stage, len(items or []), exported, stage_dir)
    return stage_dir


# ---------------- shot detection ----------------

def subtitle_units(segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    units = []
    for idx, seg in enumerate(segments or [], start=1):
        start = parse_time(seg.get("start") or seg.get("begin") or seg.get("from"))
        end = parse_time(seg.get("end") or seg.get("to") or seg.get("finish"))
        if (start is None or end is None) and seg.get("timestamp") and "-" in str(seg.get("timestamp")):
            left, right = str(seg.get("timestamp")).split("-", 1)
            start, end = parse_time(left), parse_time(right)
        if start is None or end is None:
            continue
        if end <= start:
            end = start + 0.3
        units.append({"start": round(float(start), 3), "end": round(float(end), 3), "text": str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip()})
    units.sort(key=lambda x: (x["start"], x["end"]))
    return units

def detect_ffmpeg_scene_times(video_path: str, story_start: float, story_end: float) -> List[float]:
    if not video_path or not Path(video_path).exists():
        return []
    if not cfg_bool("movie_story_ffmpeg_scene_detect", True):
        return []

    threshold = cfg_float("movie_story_scene_threshold", 0.32)
    min_gap = cfg_float("movie_story_scene_boundary_min_gap", 4.0)
    timeout = cfg_int("movie_story_scene_detect_timeout", 240)
    vf = f"select='gt(scene,{threshold})',showinfo"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-i", video_path, "-vf", vf, "-an", "-f", "null", "-"]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=timeout)
    text = (result.stderr or "") + "\n" + (result.stdout or "")
    times = []
    for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", text):
        t = float(m.group(1))
        if story_start < t < story_end and (not times or t - times[-1] >= min_gap):
            times.append(round(t, 3))
    return times

def subtitle_gap_times(units: List[Dict[str, Any]]) -> List[float]:
    times = []
    strong_gap = cfg_float("movie_story_subtitle_strong_gap", 2.5)
    medium_gap = cfg_float("movie_story_subtitle_medium_gap", 1.8)
    for prev, cur in zip(units, units[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= medium_gap:
            times.append(round((prev["end"] + cur["start"]) / 2, 3))
    return times

def text_between(units: List[Dict[str, Any]], s: float, e: float) -> str:
    return " ".join(u["text"] for u in units if u["end"] > s and u["start"] < e and u["text"]).strip()

def build_shots(segments, video_path: str, output_path: str):
    units = subtitle_units(segments)
    if not units:
        return [], {"subtitle_units": 0}

    story_start, story_end = units[0]["start"], units[-1]["end"]
    audit_stage("00b_start_shot_detection_v10", [{
        "candidate_id": "start_shot_detection",
        "candidate_type": "runtime_marker",
        "video_start": story_start,
        "video_end": min(story_start + 0.001, story_end),
        "subtitle_text": "start building shot candidates: ffmpeg_scene + subtitle_gap",
        "score": 1.0,
    }], video_path, output_path, export_clips=False)

    ff_times = []
    try:
        ff_times = detect_ffmpeg_scene_times(video_path, story_start, story_end)
    except Exception as exc:
        logger.exception("v10 ffmpeg scene detect failed: %s", exc)

    sub_times = subtitle_gap_times(units)
    raw = sorted(set([round(t, 3) for t in ff_times + sub_times if story_start < t < story_end]))

    # fuse close boundaries
    fuse_window = cfg_float("movie_story_boundary_fuse_window", 1.2)
    fused = []
    for t in raw:
        if not fused or t - fused[-1] > fuse_window:
            fused.append(t)
        else:
            fused[-1] = round((fused[-1] + t) / 2, 3)

    audit_stage("00c_boundary_summary_v10", [{
        "candidate_id": "boundary_summary",
        "candidate_type": "summary",
        "video_start": story_start,
        "video_end": min(story_start + 0.001, story_end),
        "subtitle_text": f"ffmpeg_boundaries={len(ff_times)}, subtitle_gap_boundaries={len(sub_times)}, fused_boundaries={len(fused)}",
        "score": 1.0,
    }], video_path, output_path, {
        "ffmpeg_boundaries": len(ff_times),
        "subtitle_gap_boundaries": len(sub_times),
        "fused_boundaries": len(fused),
        "scene_threshold": cfg_float("movie_story_scene_threshold", 0.32),
    }, export_clips=False)

    cuts = [story_start] + fused + [story_end]
    shots = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e <= s:
            continue
        txt = text_between(units, s, e)
        sid = f"shot_{len(shots)+1:04d}"
        shots.append({
            "candidate_id": sid,
            "candidate_type": "shot",
            "segment_id": f"plot_{len(shots)+1:03d}",
            "scene_id": f"plot_{len(shots)+1:03d}",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "subtitle_text": txt,
            "source_text": txt,
            "main_text_evidence": txt,
            "boundary_start_reason": ["ffmpeg_or_subtitle_boundary"] if i > 0 else ["story_start"],
            "boundary_end_reason": ["ffmpeg_or_subtitle_boundary"] if i < len(cuts)-2 else ["story_end"],
            "boundary_confidence": "high",
        })
    return shots, {"subtitle_units": len(units), "ffmpeg_boundaries": len(ff_times), "subtitle_gap_boundaries": len(sub_times), "fused_boundaries": len(fused)}


# ---------------- scene merge, boundary first ----------------

def _text(item: Dict[str, Any]) -> str:
    return str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")

def _transition_word(text: str) -> bool:
    markers = ["第二天", "与此同时", "另一边", "回到", "几天后", "随后", "转眼", "晚上", "第二日", "次日", "另一头", "没过多久", "过了一会儿", "此时"]
    return any(m in text for m in markers)

def should_merge(current: List[Dict[str, Any]], shot: Dict[str, Any]) -> bool:
    if not current:
        return True
    s0 = float(current[0]["video_start"])
    e0 = float(current[-1]["video_end"])
    ss = float(shot["video_start"])
    se = float(shot["video_end"])
    cur_dur = e0 - s0
    after_dur = se - s0
    gap = max(0.0, ss - e0)

    min_for_split = cfg_float("movie_story_scene_boundary_min_seconds", 6.0)
    hard_max = cfg_float("movie_story_scene_hard_max_seconds", 90.0)
    max_gap = cfg_float("movie_story_scene_merge_max_gap", 2.0)

    if after_dur > hard_max:
        return False
    if _transition_word(_text(shot)) and cur_dur >= min_for_split:
        return False
    if gap > max_gap and cur_dur >= min_for_split:
        return False

    # 边界优先：v10 的 shot 本身已经是 ffmpeg/subtitle 边界，因此不再用 target 时长强切；
    # 但如果当前片段已达到最小可用长度，遇到下一个边界时可以切开。
    if cur_dur >= min_for_split:
        return False

    return True

def merge_shots_to_scenes(shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scenes, buf = [], []
    def flush():
        nonlocal buf
        if not buf:
            return
        idx = len(scenes) + 1
        s, e = float(buf[0]["video_start"]), float(buf[-1]["video_end"])
        txt = " ".join(_text(x) for x in buf if _text(x)).strip()
        scenes.append({
            "candidate_id": f"scene_{idx:04d}",
            "candidate_type": "scene",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e-s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "subtitle_text": txt,
            "source_text": txt,
            "main_text_evidence": txt,
            "source_shot_ids": [x.get("candidate_id") for x in buf],
            "children": [x.get("candidate_id") for x in buf],
            "merge_policy": "v10_boundary_first_min_only",
        })
        buf = []
    for shot in shots:
        if not buf:
            buf.append(shot)
        elif should_merge(buf, shot):
            buf.append(shot)
        else:
            flush()
            buf.append(shot)
    flush()
    return scenes


# ---------------- exposed pipeline ----------------

def build_plot_chunks_v10(segments, *args, **kwargs):
    video_path = kwargs.get("video_path") or resolve_video_path(kwargs)
    output_path = kwargs.get("output_script_path") or resolve_output_path(kwargs)

    audit_stage("00_active_direct_runtime_v10", [{
        "candidate_id": "active_runtime_v10",
        "candidate_type": "runtime_marker",
        "video_start": 0.0,
        "video_end": 0.001,
        "subtitle_text": "ACTIVE_RUNTIME=direct_runtime_v10_fast_visible_audit; manifest-first audit; local shot builder.",
        "highlight_score": 1.0,
        "score": 1.0,
        "selected": True,
    }], video_path, output_path, export_clips=False)

    shots, meta = build_shots(segments, video_path, output_path)
    audit_stage("01_shot_candidates_v10", shots, video_path, output_path, meta)

    scenes = merge_shots_to_scenes(shots)
    audit_stage("02_scene_candidates_v10", scenes, video_path, output_path, {"source": "v10 local shot merge"})

    chunks = []
    for idx, item in enumerate(scenes, start=1):
        s, e = float(item["video_start"]), float(item["video_end"])
        seg_id = f"plot_{idx:03d}"
        cur = dict(item)
        cur.update({
            "segment_id": seg_id,
            "scene_id": seg_id,
            "candidate_id": item.get("candidate_id") or seg_id,
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
        })
        chunks.append(cur)
    logger.warning("movie_story direct v10 stage1: shots=%s scenes=%s returned=%s", len(shots), len(scenes), len(chunks))
    return chunks

def select_story_highlights_v10(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    video_path = video_path or resolve_video_path({})
    output_script_path = output_script_path or resolve_output_path({})
    mode = v5.selectivity(highlight_selectivity)

    scored = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        s, e = float(cur.get("video_start") or 0.0), float(cur.get("video_end") or 0.0)
        if e <= s:
            continue
        scores, reasons = v5.score_item(cur)
        cur["scores"] = scores
        cur["highlight_score"] = scores.get("highlight_score")
        cur["score"] = scores.get("highlight_score")
        cur["selection_reasons"] = reasons
        cur["selected"] = False
        cur["drop_reason"] = ""
        scored.append(cur)

    if mode == "loose":
        threshold = cfg_float("movie_story_loose_threshold", 0.34)
        cap = cfg_int("movie_story_loose_max_keep_count", 500)
    elif mode == "strict":
        threshold = cfg_float("movie_story_strict_threshold", 0.68)
        cap = cfg_int("movie_story_strict_max_keep_count", 35)
    elif mode == "balanced":
        threshold = cfg_float("movie_story_balanced_threshold", 0.48)
        cap = cfg_int("movie_story_balanced_max_keep_count", 60)
    else:
        threshold = cfg_float("movie_story_very_loose_threshold", 0.18)
        cap = cfg_int("movie_story_very_loose_max_keep_count", 560)

    candidates = [x for x in scored if float(x.get("highlight_score") or 0.0) >= threshold]
    ranked = sorted(scored, key=lambda x: (-float(x.get("highlight_score") or 0.0), float(x.get("video_start") or 0.0)))
    if mode == "loose":
        min_keep = min(cap, max(1, int(len(scored) * cfg_float("movie_story_loose_min_keep_ratio", 0.35))))
        selected = {id(x): x for x in candidates}
        for row in ranked:
            if len(selected) >= min_keep:
                break
            selected[id(row)] = row
        candidates = list(selected.values())

    if len(candidates) > cap:
        candidates = sorted(candidates, key=lambda x: (-float(x.get("highlight_score") or 0.0), float(x.get("video_start") or 0.0)))[:cap]

    ids = {id(x) for x in candidates}
    for row in scored:
        if id(row) in ids:
            row["selected"] = True
        else:
            row["drop_reason"] = f"score_below_{threshold}_or_over_cap_{cap}"

    audit_stage("04a_scored_candidates_v10", scored, video_path, output_script_path, {"mode": mode, "threshold": threshold, "cap": cap})

    candidates.sort(key=lambda x: float(x.get("video_start") or 0.0))
    highlights = []
    for idx, src in enumerate(candidates, start=1):
        s, e = float(src.get("video_start") or 0.0), float(src.get("video_end") or 0.0)
        seg_id = src.get("segment_id") or src.get("candidate_id") or f"plot_{idx:03d}"
        scores = src.get("scores") or {}
        highlights.append({
            "highlight_id": f"highlight_{idx:03d}",
            "highlight_rank": idx,
            "scene_ids": [src.get("scene_id") or seg_id],
            "segment_ids": [seg_id],
            "evidence_ids": [seg_id],
            "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [],
            "highlight_reasons": src.get("selection_reasons") or [],
            "highlight_score": scores.get("highlight_score", 0.0),
            "score": scores.get("highlight_score", 0.0),
            "semantic_start": s,
            "semantic_end": e,
            "semantic_duration": round(e-s, 3),
            "semantic_timestamp": f"{fmt(s)}-{fmt(e)}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e-s, 3),
            "timestamp": f"{fmt(s)}-{fmt(e)}",
            "source_text": src.get("subtitle_text") or src.get("source_text") or "",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "highlight_selectivity": mode,
            "scores": scores,
            "selected": True,
            "stage3_policy": "direct_v10_fast_visible_score_sync",
        })
    audit_stage("05_selected_highlights_v10", highlights, video_path, output_script_path, {"mode": mode, "selected": len(highlights)})
    return highlights
