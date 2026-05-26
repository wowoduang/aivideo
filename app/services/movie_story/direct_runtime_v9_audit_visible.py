
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
direct_runtime_v9_audit_visible

目的：
- 解决 direct_v8 没有 _movie_story_direct_v8_audit 的问题。
- 所有 direct 审计统一写入用户正在看的：
  _movie_story_pipeline_audit_clips/run_xxx
- 增加 00_active_direct_runtime_v9，证明当前确实走了 v9。
- score 字段同步 highlight_score，避免旧审计里 score=null。
"""

import csv
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from app.services.movie_story import direct_runtime_v5 as v5
from app.services.movie_story import direct_runtime_v6 as v6
from app.services.movie_story import direct_runtime_v8 as v8


def _fmt(seconds: float) -> str:
    return v5.fmt_time(seconds)


def _safe(value: Any) -> str:
    return str(value or "segment").replace("/", "_").replace("\\", "_")[:50]


def _cfg_bool(key: str, default: bool = False) -> bool:
    return v5.cfg_bool(key, default)


def _cfg_int(key: str, default: int) -> int:
    return v5.cfg_int(key, default)


def _cfg_float(key: str, default: float) -> float:
    return v5.cfg_float(key, default)


def _video_path(kwargs=None) -> str:
    return v5.resolve_video_path(kwargs or {})


def _output_path(kwargs=None) -> str:
    return v5.resolve_output_script_path(kwargs or {})


def _audit_base(video_path: str = "", output_path: str = "") -> Path:
    # 优先写到视频上传目录，和旧 _movie_story_pipeline_audit_clips 放一起。
    if video_path and Path(video_path).exists():
        return Path(video_path).parent / "_movie_story_pipeline_audit_clips"
    if output_path:
        return Path(output_path).parent / "_movie_story_pipeline_audit_clips"

    # 兜底：项目根目录 E:/aivideo-v5 -> E:/aivideo-v5-workspace/frontend_uploads/video
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
        "timestamp": item.get("timestamp") or f"{_fmt(s)}-{_fmt(e)}",
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


def audit_stage(stage: str, items: List[Dict[str, Any]], video_path: str = "", output_path: str = "", metadata=None):
    run = _run_dir(video_path, output_path)
    stage_dir = run / stage
    clips_dir = stage_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    export = _cfg_bool("movie_story_audit_export_clips", True)
    max_clips = _cfg_int("movie_story_audit_max_clips_per_stage", 560)
    rows, total, exported = [], 0.0, 0

    for idx, item in enumerate(items or [], start=1):
        r = _row(item, idx)
        s, e, dur = r["start"], r["end"], r["duration"]
        total += dur
        if export and video_path and Path(video_path).exists() and idx <= max_clips and e > s:
            clip = clips_dir / f"{idx:03d}_{_safe(r['id'])}_{s:.3f}_{e:.3f}.mp4"
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
            r["clip_path"] = str(clip)
            r["exported"] = ok
            exported += 1 if ok else 0
        rows.append(r)

    manifest = {
        "stage": stage,
        "count": len(items or []),
        "exported": exported,
        "total_duration": round(total, 3),
        "metadata": metadata or {},
        "items": rows,
    }
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
    index.append({"stage": stage, "dir": str(stage_dir), "count": len(items or []), "exported": exported, "total_duration": round(total, 3)})
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning("movie_story v9 visible audit: %s count=%s dir=%s", stage, len(items or []), stage_dir)


def build_plot_chunks_v9(segments, *args, **kwargs):
    video_path = kwargs.get("video_path") or _video_path(kwargs)
    output_path = kwargs.get("output_script_path") or _output_path(kwargs)

    audit_stage("00_active_direct_runtime_v9", [{
        "candidate_id": "active_runtime_v9",
        "candidate_type": "runtime_marker",
        "video_start": 0.0,
        "video_end": 0.001,
        "duration": 0.001,
        "subtitle_text": "ACTIVE_RUNTIME=direct_runtime_v9_audit_visible; audit writes to _movie_story_pipeline_audit_clips; score synced from highlight_score.",
        "highlight_score": 1.0,
        "score": 1.0,
        "selected": True,
    }], video_path, output_path)

    shots = v5.build_plot_chunks_v5(segments, *args, **kwargs)
    for idx, s in enumerate(shots, start=1):
        s["candidate_id"] = s.get("candidate_id") or f"shot_{idx:04d}"
        s["candidate_type"] = "shot"
    audit_stage("01_shot_candidates_v9", shots, video_path, output_path, {"source": "v5 shot pool"})

    scenes = v8.merge_shots_to_scene_candidates_v8(shots)
    audit_stage("02_scene_candidates_v9", scenes, video_path, output_path, {"source": "v8 boundary-first merge"})

    chunks = []
    for idx, item in enumerate(scenes, start=1):
        s, e = _start_end(item)
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
            "timestamp": f"{_fmt(s)}-{_fmt(e)}",
        })
        chunks.append(cur)

    logger.warning("movie_story direct v9 stage1: shots=%s scenes=%s returned=%s", len(shots), len(scenes), len(chunks))
    return chunks


def select_story_highlights_v9(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    video_path = video_path or _video_path({})
    output_script_path = output_script_path or _output_path({})

    mode = v5.selectivity(highlight_selectivity)
    evidence = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        evidence.append(cur)

    scored = []
    for item in evidence:
        s, e = _start_end(item)
        if e <= s:
            continue
        scores, reasons = v5.score_item(item)
        row = dict(item)
        row["scores"] = scores
        row["highlight_score"] = scores.get("highlight_score")
        row["score"] = scores.get("highlight_score")
        row["selection_reasons"] = reasons
        row["selected"] = False
        row["drop_reason"] = ""
        scored.append(row)

    if mode == "strict":
        threshold, cap = _cfg_float("movie_story_strict_threshold", 0.68), _cfg_int("movie_story_strict_max_keep_count", 35)
    elif mode == "balanced":
        threshold, cap = _cfg_float("movie_story_balanced_threshold", 0.48), _cfg_int("movie_story_balanced_max_keep_count", 60)
    elif mode == "loose":
        threshold, cap = _cfg_float("movie_story_loose_threshold", 0.34), _cfg_int("movie_story_loose_max_keep_count", 500)
    else:
        threshold, cap = _cfg_float("movie_story_very_loose_threshold", 0.18), _cfg_int("movie_story_very_loose_max_keep_count", 560)

    candidates = [x for x in scored if float(x.get("highlight_score") or 0.0) >= threshold]
    ranked = sorted(scored, key=lambda x: (-float(x.get("highlight_score") or 0.0), float(x.get("video_start") or 0.0)))

    if mode == "loose":
        min_keep = min(cap, max(1, int(len(scored) * _cfg_float("movie_story_loose_min_keep_ratio", 0.35))))
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

    audit_stage("04a_scored_candidates_v9", scored, video_path, output_script_path, {"mode": mode, "threshold": threshold, "cap": cap})

    candidates.sort(key=lambda x: float(x.get("video_start") or 0.0))
    highlights = []
    for idx, src in enumerate(candidates, start=1):
        s, e = _start_end(src)
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
            "semantic_duration": round(e - s, 3),
            "semantic_timestamp": f"{_fmt(s)}-{_fmt(e)}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{_fmt(s)}-{_fmt(e)}",
            "source_text": src.get("subtitle_text") or src.get("source_text") or "",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "highlight_selectivity": mode,
            "scores": scores,
            "selected": True,
            "stage3_policy": "direct_v9_visible_score_sync",
        })
    audit_stage("05_selected_highlights_v9", highlights, video_path, output_script_path, {"mode": mode, "selected": len(highlights)})
    logger.warning("movie_story direct v9 stage3: mode=%s input=%s selected=%s", mode, len(evidence), len(highlights))
    return highlights
