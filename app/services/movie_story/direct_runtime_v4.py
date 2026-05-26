
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from app.utils import workspace
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def cfg(key: str, default=None):
    try:
        from app.config import config as app_config
        app = getattr(app_config, "app", None)
        if isinstance(app, dict) and key in app:
            return app.get(key)
        if app is not None and hasattr(app, key):
            return getattr(app, key)
        if isinstance(app_config, dict):
            if key in app_config:
                return app_config.get(key)
            if isinstance(app_config.get("app"), dict):
                return app_config["app"].get(key, default)
    except Exception as _e:
        logger.debug("配置字段读取失败，返回 default: {}", _e)
    return default


def cfg_bool(key: str, default: bool = False) -> bool:
    return str(cfg(key, default)).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def cfg_float(key: str, default: float) -> float:
    try:
        return float(cfg(key, default))
    except Exception:
        return float(default)


def cfg_int(key: str, default: int) -> int:
    try:
        return int(cfg(key, default))
    except Exception:
        return int(default)


def selectivity(fallback: str = "balanced") -> str:
    value = (
        os.environ.get("AIVIDEO_HIGHLIGHT_SELECTIVITY")
        or os.environ.get("MOVIE_STORY_HIGHLIGHT_SELECTIVITY")
        or str(cfg("movie_story_highlight_selectivity", "") or "")
        or fallback
    )
    value = str(value or "balanced").strip().lower()
    aliases = {
        "宽松": "loose",
        "较宽松": "loose",
        "很宽松": "very_loose",
        "严格": "strict",
        "均衡": "balanced",
        "默认": "balanced",
        "normal": "balanced",
        "medium": "balanced",
    }
    value = aliases.get(value, value)
    return value if value in {"strict", "balanced", "loose", "very_loose"} else "balanced"


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


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def safe_id(value: Any) -> str:
    return str(value or "segment").replace("/", "_").replace("\\", "_")[:50]


def caller_value(name: str, default=None):
    frame = inspect.currentframe()
    if frame is None:
        return default
    try:
        cur = frame.f_back
        for _ in range(10):
            if cur is None:
                break
            if name in cur.f_locals and cur.f_locals.get(name) is not None:
                return cur.f_locals.get(name)
            cur = cur.f_back
    finally:
        del frame
    return default


def resolve_video_path(kwargs=None) -> str:
    kwargs = kwargs or {}
    for key in ("video_path", "video_origin_path", "source_video_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("video_path", "video_origin_path", "source_video_path"):
        value = caller_value(key)
        if value:
            return str(value)
    params = caller_value("params")
    if params is not None:
        for attr in ("video_path", "video_origin_path", "source_video_path"):
            value = getattr(params, attr, None)
            if value:
                return str(value)
    return ""


def resolve_output_script_path(kwargs=None) -> str:
    kwargs = kwargs or {}
    for key in ("output_script_path", "script_path", "output_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("output_script_path", "script_path", "output_path"):
        value = caller_value(key)
        if value:
            return str(value)
    return ""


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
        units.append({
            "unit_id": f"sub_{idx:05d}",
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "text": str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip(),
        })
    units.sort(key=lambda x: (x["start"], x["end"]))
    cleaned = []
    for u in units:
        if cleaned and u["text"] and cleaned[-1]["text"] == u["text"] and u["start"] - cleaned[-1]["end"] <= 0.8:
            cleaned[-1]["end"] = max(cleaned[-1]["end"], u["end"])
        else:
            cleaned.append(u)
    return cleaned


def subtitle_boundaries(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for prev, cur in zip(units, units[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= 2.5:
            strength = "strong"
        elif gap >= 1.2:
            strength = "medium"
        elif re.search(r"[。！？!?]$", prev.get("text") or "") and gap >= 0.45:
            strength = "weak"
        else:
            continue
        out.append({"time": round((prev["end"] + cur["start"]) / 2, 3), "strength": strength, "reason": ["subtitle_gap"], "gap": round(gap, 3)})
    return out


def normalize_boundaries(items: Iterable[Any], reason: str) -> List[Dict[str, Any]]:
    out = []
    for item in items or []:
        if isinstance(item, dict):
            t = parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            strength = str(item.get("strength") or "medium")
            reasons = list(item.get("reason") or item.get("reasons") or [reason])
        else:
            t = parse_time(item)
            strength = "medium"
            reasons = [reason]
        if t is not None:
            out.append({"time": round(t, 3), "strength": strength, "reason": reasons})
    return out


def detect_ffmpeg_scene_boundaries(video_path: str, *, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    if not video_path or not Path(video_path).exists():
        return []
    if not cfg_bool("movie_story_ffmpeg_scene_detect", True):
        return []

    threshold = cfg_float("movie_story_scene_threshold", 0.30)
    min_gap = cfg_float("movie_story_scene_boundary_min_gap", 3.0)
    timeout = cfg_int("movie_story_scene_detect_timeout", 240)

    vf = f"select='gt(scene,{threshold})',showinfo"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-i", video_path, "-vf", vf, "-an", "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=timeout)
        text = (result.stderr or "") + "\n" + (result.stdout or "")
        times = []
        for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", text):
            t = float(m.group(1))
            if story_start < t < story_end:
                if not times or t - times[-1] >= min_gap:
                    times.append(round(t, 3))
        logger.warning("movie_story v4 ffmpeg scene boundaries: threshold=%s count=%s", threshold, len(times))
        return [{"time": t, "strength": "strong", "reason": ["ffmpeg_scene"]} for t in times]
    except Exception as exc:
        logger.warning("movie_story v4 ffmpeg scene detect failed: %s", exc)
        return []


def fuse_boundaries(all_boundaries: List[Dict[str, Any]], *, story_start: float, story_end: float) -> List[Dict[str, Any]]:
    raw = [b for b in all_boundaries if story_start < float(b.get("time", 0)) < story_end]
    raw.sort(key=lambda x: float(x["time"]))
    cluster_window = cfg_float("movie_story_boundary_fuse_window", 1.0)
    fused = []
    cluster = []

    def flush():
        if not cluster:
            return
        times = [float(x["time"]) for x in cluster]
        reasons = []
        score = 0
        for x in cluster:
            reasons.extend(x.get("reason") or [])
            strength = str(x.get("strength") or "medium")
            score += {"weak": 1, "medium": 2, "strong": 3}.get(strength, 2)
        fused.append({
            "time": round(sum(times) / len(times), 3),
            "strength": "strong" if score >= 3 or len(cluster) >= 2 else "medium",
            "reason": sorted(set(reasons)),
        })

    for b in raw:
        if not cluster or abs(float(b["time"]) - float(cluster[-1]["time"])) <= cluster_window:
            cluster.append(b)
        else:
            flush()
            cluster = [b]
    flush()
    return fused


def text_between(units: List[Dict[str, Any]], start: float, end: float):
    chosen = [u for u in units if u["end"] > start and u["start"] < end]
    if not chosen:
        return "", None, None
    return " ".join(u["text"] for u in chosen if u["text"]).strip(), chosen[0]["start"], chosen[-1]["end"]


def reason_at(boundaries: List[Dict[str, Any]], t: float):
    near = [b for b in boundaries if abs(float(b["time"]) - float(t)) <= 1.2]
    reasons = []
    for b in near:
        reasons.extend(b.get("reason") or [])
    return sorted(set(reasons)) or ["duration_limit"]


def build_scene_candidates(units, boundaries, story_start: float, story_end: float):
    min_d = cfg_float("movie_story_scene_min_seconds", 4.0)
    target_max = cfg_float("movie_story_scene_target_max_seconds", 30.0)
    max_d = cfg_float("movie_story_scene_max_seconds", 45.0)

    cuts = [story_start] + [float(b["time"]) for b in boundaries if story_start < float(b["time"]) < story_end] + [story_end]
    cuts = sorted(set(round(x, 3) for x in cuts))
    ranges = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        if e > s:
            ranges.append((s, e, reason_at(boundaries, s), reason_at(boundaries, e)))

    normalized = []
    for s, e, rs, re in ranges:
        scene_boundary = any(r in {"ffmpeg_scene", "video_boundary"} for r in (rs + re))
        if normalized and e - s < min_d and not scene_boundary:
            ps, pe, prs, pre = normalized.pop()
            normalized.append((ps, e, prs, re))
            continue
        if e - s > max_d:
            current = s
            while e - current > max_d:
                candidates = [float(b["time"]) for b in boundaries if current + min_d <= float(b["time"]) <= current + max_d]
                cut = min(candidates, key=lambda x: abs(x - (current + target_max))) if candidates else current + target_max
                normalized.append((current, cut, rs, ["long_segment_split"]))
                current = cut
            if e - current >= min_d:
                normalized.append((current, e, ["long_segment_split"], re))
            elif normalized:
                ps, pe, prs, pre = normalized.pop()
                normalized.append((ps, e, prs, re))
            continue
        normalized.append((s, e, rs, re))

    scenes = []
    for idx, (s, e, rs, re) in enumerate(normalized, start=1):
        text, sub_s, sub_e = text_between(units, s, e)
        scenes.append({
            "candidate_id": f"scene_{idx:04d}",
            "candidate_type": "scene",
            "video_start": round(s, 3),
            "video_end": round(e, 3),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "subtitle_start": sub_s,
            "subtitle_end": sub_e,
            "subtitle_text": text,
            "main_text_evidence": text,
            "source_text": text,
            "boundary_start_reason": rs,
            "boundary_end_reason": re,
            "boundary_confidence": "high" if any(r in {"ffmpeg_scene", "video_boundary", "subtitle_gap"} for r in rs + re) else "medium",
            "stage1_policy": "movie_story_direct_v4_scene_split_no_filter",
        })
    return scenes


def build_draft_stories(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stories = []
    buf = []

    def flush():
        nonlocal buf
        if not buf:
            return
        s, e = buf[0]["video_start"], buf[-1]["video_end"]
        idx = len(stories) + 1
        stories.append({
            "candidate_id": f"story_{idx:04d}",
            "candidate_type": "draft_story",
            "video_start": s,
            "video_end": e,
            "start": s,
            "end": e,
            "duration": round(e - s, 3),
            "children": [x["candidate_id"] for x in buf],
            "subtitle_text": " ".join(x.get("subtitle_text") or "" for x in buf).strip(),
            "merge_reason": ["structural_merge"],
        })
        buf = []

    for sc in scenes:
        if not buf:
            buf.append(sc)
            continue
        cur = sc["video_end"] - buf[0]["video_start"]
        hard_scene_break = "ffmpeg_scene" in (sc.get("boundary_start_reason") or []) or "video_boundary" in (sc.get("boundary_start_reason") or [])
        if cur <= cfg_float("movie_story_story_max_seconds", 120.0) and not hard_scene_break:
            buf.append(sc)
        else:
            flush()
            buf.append(sc)
    flush()
    return stories


def audit_stage(video_path: str, output_script_path: str, stage: str, items: List[Dict[str, Any]], metadata=None):
    try:
        root = Path(output_script_path).parent / "_movie_story_direct_v4_audit" if output_script_path else Path(workspace.runtime_dir("debug/_movie_story_direct_v4_audit", create=True))
        run_id = os.environ.get("AIVIDEO_AUDIT_RUN_ID") or time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = run_id
        run = root / run_id
        stage_dir = run / ("".join(c if c.isalnum() or c in "._-" else "_" for c in stage)[:120])
        clips = stage_dir / "clips"
        clips.mkdir(parents=True, exist_ok=True)

        keep = cfg_int("movie_story_audit_keep_runs", 2)
        if root.exists():
            runs = [p for p in root.glob("run_*") if p.is_dir()]
            runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for old in runs[keep:]:
                shutil.rmtree(old, ignore_errors=True)

        export = cfg_bool("movie_story_audit_export_clips", True)
        max_n = cfg_int("movie_story_audit_max_clips_per_stage", 160)
        rows = []
        exported = 0
        total = 0.0
        for idx, item in enumerate(items or [], start=1):
            s = float(item.get("video_start", item.get("start", 0.0)) or 0.0)
            e = float(item.get("video_end", item.get("end", s)) or s)
            dur = max(0.0, e - s)
            total += dur
            row = {
                "idx": idx,
                "id": item.get("candidate_id") or item.get("highlight_id") or item.get("segment_id") or idx,
                "video_start": s,
                "video_end": e,
                "duration": round(dur, 3),
                "score": item.get("highlight_score") or (item.get("scores") or {}).get("highlight_score"),
                "plot_function": item.get("plot_function"),
                "text": str(item.get("subtitle_text") or item.get("source_text") or "")[:300],
            }
            if export and video_path and Path(video_path).exists() and idx <= max_n and e > s:
                clip_path = clips / f"{idx:03d}_{safe_id(row['id'])}_{s:.3f}_{e:.3f}.mp4"
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{s:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
                    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "25", "-c:a", "aac",
                    "-b:a", "96k", "-movflags", "+faststart", str(clip_path),
                ]
                try:
                    ok = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=max(30, int(dur) + 30)).returncode == 0
                except Exception:
                    ok = False
                row["clip_path"] = str(clip_path)
                row["exported"] = ok
                exported += 1 if ok else 0
            rows.append(row)

        manifest = {"stage": stage, "count": len(items), "exported": exported, "total_duration": round(total, 3), "metadata": metadata or {}, "items": rows}
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if rows:
            with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
        index_path = run / "_stage_index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        except Exception:
            index = []
        index.append({"stage": stage, "dir": str(stage_dir), "count": len(items), "exported": exported, "total_duration": round(total, 3)})
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("movie_story v4 audit: stage=%s count=%s exported=%s dir=%s", stage, len(items), exported, stage_dir)
    except Exception as exc:
        logger.warning("movie_story v4 audit failed: stage=%s error=%s", stage, exc)


def build_plot_chunks_v4(segments, *args, **kwargs):
    video_path = kwargs.get("video_path") or resolve_video_path(kwargs)
    output_script_path = kwargs.get("output_script_path") or resolve_output_script_path(kwargs)
    full_understanding = kwargs.get("full_subtitle_understanding") or caller_value("full_subtitle_understanding") or {}
    video_candidates = (
        kwargs.get("video_candidates")
        or kwargs.get("video_boundary_candidates")
        or caller_value("video_boundary_candidates")
        or caller_value("scene_cut_points")
        or []
    )

    units = subtitle_units(segments)
    if not units:
        return []

    prologue_end = None
    story_end = None
    if isinstance(full_understanding, dict):
        prologue_end = parse_time(full_understanding.get("prologue_end_time"))
        story_end = parse_time(full_understanding.get("story_end_time"))

    story_start = float(prologue_end) if prologue_end is not None else units[0]["start"]
    final_end = float(story_end) if story_end is not None else units[-1]["end"]
    if final_end <= story_start:
        story_start, final_end = units[0]["start"], units[-1]["end"]

    sub_b = subtitle_boundaries(units)
    ext_b = normalize_boundaries(video_candidates or [], "video_boundary")
    ff_b = detect_ffmpeg_scene_boundaries(video_path, story_start=story_start, story_end=final_end)
    boundaries = fuse_boundaries(sub_b + ext_b + ff_b, story_start=story_start, story_end=final_end)

    scenes = build_scene_candidates(units, boundaries, story_start, final_end)
    stories = build_draft_stories(scenes)
    audit_stage(video_path, output_script_path, "01_scene_candidates_v4", scenes, {"policy": "scene_split_no_filter", "subtitle_boundaries": len(sub_b), "external_boundaries": len(ext_b), "ffmpeg_boundaries": len(ff_b), "fused_boundaries": len(boundaries)})
    audit_stage(video_path, output_script_path, "02_draft_story_candidates_v4", stories, {"policy": "audit_only_not_used_for_stage1_output"})

    chunks = []
    for idx, item in enumerate(scenes, start=1):
        s = float(item["video_start"])
        e = float(item["video_end"])
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
            "timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
        })
        chunks.append(cur)

    audit_stage(video_path, output_script_path, "03_plot_chunks_scene_level_v4", chunks, {"policy": "stage1_returns_scene_candidates"})
    logger.warning("movie_story direct v4 stage1: scenes=%s stories=%s returned_chunks=%s", len(scenes), len(stories), len(chunks))
    return chunks


PLOT_RULES = [
    ("信息揭露", ["真相", "秘密", "原来", "知道", "发现", "告诉", "证据", "身份"]),
    ("冲突升级", ["吵", "打", "杀", "滚", "别逼", "你敢", "威胁", "报仇"]),
    ("人物转折", ["决定", "不再", "终于", "改变", "答应", "拒绝", "离开"]),
    ("关系变化", ["相信", "怀疑", "背叛", "原谅", "误会", "合作", "分开"]),
    ("关键决定", ["必须", "不能", "要去", "留下", "救", "走", "选择"]),
    ("情感爆发", ["哭", "流泪", "崩溃", "对不起", "委屈", "恨", "爱"]),
    ("阴谋推进", ["计划", "安排", "利用", "陷害", "坐收渔利", "密令"]),
]


def guess_plot(text: str) -> str:
    for name, keys in PLOT_RULES:
        if any(k in text for k in keys):
            return name
    return "弱过渡" if len(text) < 20 else "发展"


def score_item(item: Dict[str, Any]):
    text = str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")
    plot = item.get("plot_function") or guess_plot(text)
    item["plot_function"] = plot
    reasons = []
    story = 0.25
    if plot in {"冲突升级", "反转", "高潮", "结局收束"}:
        story = 0.95
        reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}:
        story = 0.82
        reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}:
        story = 0.48
        reasons.append(f"主线铺垫:{plot}")

    info_tags = [k for k in ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害"] if k in text]
    emotion_tags = [k for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃", "紧张"] if k in text]
    char = 0.2
    if re.findall(r"[\u4e00-\u9fa5]{2,4}", text[:160]):
        char += 0.25
        reasons.append("存在人物线索")
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]):
        char += 0.25
        reasons.append("人物关系或目标变化")
    char = min(char, 1.0)

    info = 0.85 if info_tags else 0.15
    emotion = 0.78 if emotion_tags else 0.15
    visual = 0.25 if item.get("boundary_confidence") == "high" else 0.1
    importance = str(item.get("importance_level") or ("high" if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} else "medium"))
    continuity = 0.7 if importance == "high" else 0.55
    audio = 0.35 if plot in {"情感爆发", "冲突升级"} else 0.05

    score = max(0.0, min(1.0, 0.25 * story + 0.20 * char + 0.15 * info + 0.15 * emotion + 0.10 * visual + 0.10 * continuity + 0.05 * audio))
    if info_tags:
        reasons.append("存在信息增量:" + ",".join(info_tags[:4]))
    if emotion_tags:
        reasons.append("存在情绪变化:" + ",".join(emotion_tags[:4]))
    if not reasons:
        reasons.append("基础剧情候选")
    return {
        "story_score": round(story, 3),
        "character_score": round(char, 3),
        "information_score": round(info, 3),
        "emotion_score": round(emotion, 3),
        "visual_score": round(visual, 3),
        "audio_score": round(audio, 3),
        "continuity_score": round(continuity, 3),
        "highlight_score": round(score, 3),
    }, reasons


def select_story_highlights_v4(scene_evidence, segments=None, video_path="", output_script_path="", target_minutes=8, highlight_selectivity="balanced"):
    video_path = video_path or resolve_video_path({})
    output_script_path = output_script_path or resolve_output_script_path({})
    mode = selectivity(highlight_selectivity)
    evidence = []
    for idx, item in enumerate(scene_evidence or [], start=1):
        cur = dict(item)
        cur.setdefault("candidate_id", cur.get("segment_id") or cur.get("scene_id") or f"candidate_{idx:04d}")
        cur.setdefault("video_start", cur.get("start", cur.get("semantic_start", 0.0)))
        cur.setdefault("video_end", cur.get("end", cur.get("semantic_end", cur.get("video_start", 0.0))))
        cur.setdefault("subtitle_text", cur.get("subtitle_text") or cur.get("source_text") or cur.get("main_text_evidence") or "")
        evidence.append(cur)

    audit_stage(video_path, output_script_path, "04_scene_evidence_before_v4_selection", evidence, {"policy": "stage2_no_delete"})

    scored = []
    for item in evidence:
        s = float(item.get("video_start", 0.0) or 0.0)
        e = float(item.get("video_end", s) or s)
        if e <= s:
            continue
        scores, reasons = score_item(item)
        scored.append((scores["highlight_score"], e - s, item, scores, reasons))

    if mode == "strict":
        threshold = cfg_float("movie_story_strict_threshold", 0.68)
        candidates = [x for x in scored if x[0] >= threshold]
        candidates.sort(key=lambda x: (-x[0], float(x[2].get("video_start", 0.0))))
        cap_seconds = max(60.0, float(target_minutes or 8) * 60.0 * 1.1)
    elif mode == "balanced":
        threshold = cfg_float("movie_story_balanced_threshold", 0.45)
        candidates = [x for x in scored if x[0] >= threshold]
        candidates.sort(key=lambda x: (-x[0], float(x[2].get("video_start", 0.0))))
        cap_seconds = max(60.0, float(target_minutes or 8) * 60.0 * 2.0)
    elif mode == "loose":
        threshold = cfg_float("movie_story_loose_threshold", 0.18)
        ratio = cfg_float("movie_story_loose_min_keep_ratio", 0.65)
        candidates = [x for x in scored if x[0] >= threshold]
        min_keep = max(1, int(len(scored) * ratio))
        if len(candidates) < min_keep:
            ranked = sorted(scored, key=lambda x: (-x[0], float(x[2].get("video_start", 0.0))))
            seen = {id(x[2]) for x in candidates}
            for row in ranked:
                if len(candidates) >= min_keep:
                    break
                if id(row[2]) not in seen:
                    candidates.append(row)
                    seen.add(id(row[2]))
        candidates.sort(key=lambda x: float(x[2].get("video_start", 0.0)))
        cap_seconds = None
    else:
        candidates = list(scored)
        candidates.sort(key=lambda x: float(x[2].get("video_start", 0.0)))
        cap_seconds = None

    selected = []
    total = 0.0
    for row in candidates:
        if cap_seconds is not None and total >= cap_seconds:
            break
        selected.append(row)
        total += row[1]

    selected.sort(key=lambda x: float(x[2].get("video_start", 0.0)))

    highlights = []
    for idx, (_, _, src, scores, reasons) in enumerate(selected, start=1):
        s = float(src.get("video_start", 0.0) or 0.0)
        e = float(src.get("video_end", s) or s)
        seg_id = src.get("segment_id") or src.get("candidate_id") or f"plot_{idx:03d}"
        highlights.append({
            "highlight_id": f"highlight_{idx:03d}",
            "highlight_rank": idx,
            "scene_ids": [src.get("scene_id") or seg_id],
            "segment_ids": [seg_id],
            "evidence_ids": [seg_id],
            "plot_functions": [src.get("plot_function")] if src.get("plot_function") else [],
            "highlight_reasons": reasons,
            "highlight_score": scores["highlight_score"],
            "importance_level": src.get("importance_level", "medium"),
            "boundary_confidence": src.get("boundary_confidence", "medium"),
            "raw_voice_retain": src.get("plot_function") in {"情感爆发", "冲突升级"},
            "semantic_start": s,
            "semantic_end": e,
            "semantic_duration": round(e - s, 3),
            "semantic_timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
            "start": s,
            "end": e,
            "video_start": s,
            "video_end": e,
            "duration": round(e - s, 3),
            "timestamp": f"{fmt_time(s)}-{fmt_time(e)}",
            "source_text": src.get("subtitle_text") or src.get("source_text") or "",
            "llm_highlight_selected": True,
            "highlight_filter_selected": True,
            "highlight_selectivity": mode,
            "scores": scores,
            "stage3_policy": "movie_story_direct_v4_loose_not_hard_capped",
        })

    audit_stage(video_path, output_script_path, "05_selected_highlights_v4", highlights, {"mode": mode, "input": len(evidence), "selected": len(highlights)})
    logger.warning("movie_story direct v4 stage3: mode=%s input=%s selected=%s duration=%.2fs", mode, len(evidence), len(highlights), sum(x["duration"] for x in highlights))
    return highlights
