
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
direct_runtime_v5 compatibility shim

用途：
- v6 依赖 direct_runtime_v5 的底层 shot 切片和评分工具。
- 如果之前 v5 补丁没有成功写入，本文件提供兼容实现。
- 优先复用 direct_runtime_v4；如果 v4 也不存在，则使用保底字幕切片逻辑。
"""

import inspect
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

try:
    from app.services.movie_story import direct_runtime_v4 as _v4
except Exception:
    _v4 = None


def cfg(key: str, default=None):
    if _v4 is not None and hasattr(_v4, "cfg"):
        return _v4.cfg(key, default)
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
    except Exception:
        pass
    return default


def cfg_bool(key: str, default: bool = False) -> bool:
    if _v4 is not None and hasattr(_v4, "cfg_bool"):
        return _v4.cfg_bool(key, default)
    return str(cfg(key, default)).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def cfg_float(key: str, default: float) -> float:
    if _v4 is not None and hasattr(_v4, "cfg_float"):
        return _v4.cfg_float(key, default)
    try:
        return float(cfg(key, default))
    except Exception:
        return float(default)


def cfg_int(key: str, default: int) -> int:
    if _v4 is not None and hasattr(_v4, "cfg_int"):
        return _v4.cfg_int(key, default)
    try:
        return int(cfg(key, default))
    except Exception:
        return int(default)


def selectivity(fallback: str = "balanced") -> str:
    if _v4 is not None and hasattr(_v4, "selectivity"):
        return _v4.selectivity(fallback)
    value = (
        os.environ.get("AIVIDEO_HIGHLIGHT_SELECTIVITY")
        or os.environ.get("MOVIE_STORY_HIGHLIGHT_SELECTIVITY")
        or str(cfg("movie_story_highlight_selectivity", "") or "")
        or fallback
    )
    value = str(value or "balanced").strip().lower()
    aliases = {"宽松": "loose", "较宽松": "loose", "很宽松": "very_loose", "严格": "strict", "均衡": "balanced", "默认": "balanced", "normal": "balanced", "medium": "balanced"}
    value = aliases.get(value, value)
    return value if value in {"strict", "balanced", "loose", "very_loose"} else "balanced"


def parse_time(value: Any) -> Optional[float]:
    if _v4 is not None and hasattr(_v4, "parse_time"):
        return _v4.parse_time(value)
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
    if _v4 is not None and hasattr(_v4, "fmt_time"):
        return _v4.fmt_time(seconds)
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def safe_id(value: Any) -> str:
    if _v4 is not None and hasattr(_v4, "safe_id"):
        return _v4.safe_id(value)
    return str(value or "segment").replace("/", "_").replace("\\", "_")[:50]


def caller_value(name: str, default=None):
    if _v4 is not None and hasattr(_v4, "caller_value"):
        return _v4.caller_value(name, default)
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
    if _v4 is not None and hasattr(_v4, "resolve_video_path"):
        return _v4.resolve_video_path(kwargs or {})
    kwargs = kwargs or {}
    for key in ("video_path", "video_origin_path", "source_video_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("video_path", "video_origin_path", "source_video_path"):
        value = caller_value(key)
        if value:
            return str(value)
    return ""


def resolve_output_script_path(kwargs=None) -> str:
    if _v4 is not None and hasattr(_v4, "resolve_output_script_path"):
        return _v4.resolve_output_script_path(kwargs or {})
    kwargs = kwargs or {}
    for key in ("output_script_path", "script_path", "output_path"):
        if kwargs.get(key):
            return str(kwargs.get(key))
    for key in ("output_script_path", "script_path", "output_path"):
        value = caller_value(key)
        if value:
            return str(value)
    return ""


def _fallback_subtitle_units(segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        units.append({"start": float(start), "end": float(end), "text": str(seg.get("text") or seg.get("content") or seg.get("subtitle") or "").strip()})
    units.sort(key=lambda x: (x["start"], x["end"]))
    return units


def build_plot_chunks_v5(segments, *args, **kwargs):
    """
    v6 需要的底层 shot candidates。
    优先复用 v4；没有 v4 时使用字幕时间轴按 8~60 秒保底切片。
    """
    if _v4 is not None and hasattr(_v4, "build_plot_chunks_v4"):
        return _v4.build_plot_chunks_v4(segments, *args, **kwargs)

    units = _fallback_subtitle_units(segments)
    if not units:
        return []
    min_d = cfg_float("movie_story_scene_min_seconds", 8.0)
    max_d = cfg_float("movie_story_scene_max_seconds", 60.0)
    chunks = []
    cur_start = units[0]["start"]
    cur_end = cur_start
    texts = []
    for u in units:
        gap = u["start"] - cur_end
        would_duration = u["end"] - cur_start
        if texts and (gap >= 2.0 or would_duration >= max_d):
            idx = len(chunks) + 1
            chunks.append({
                "candidate_id": f"shot_{idx:04d}",
                "candidate_type": "shot",
                "segment_id": f"plot_{idx:03d}",
                "scene_id": f"plot_{idx:03d}",
                "video_start": round(cur_start, 3),
                "video_end": round(cur_end, 3),
                "start": round(cur_start, 3),
                "end": round(cur_end, 3),
                "duration": round(cur_end - cur_start, 3),
                "timestamp": f"{fmt_time(cur_start)}-{fmt_time(cur_end)}",
                "subtitle_text": " ".join(texts).strip(),
                "source_text": " ".join(texts).strip(),
                "main_text_evidence": " ".join(texts).strip(),
                "boundary_start_reason": ["fallback_subtitle"],
                "boundary_end_reason": ["fallback_subtitle"],
                "boundary_confidence": "medium",
            })
            cur_start = u["start"]
            texts = []
        cur_end = u["end"]
        if u["text"]:
            texts.append(u["text"])

    if cur_end > cur_start:
        idx = len(chunks) + 1
        chunks.append({
            "candidate_id": f"shot_{idx:04d}",
            "candidate_type": "shot",
            "segment_id": f"plot_{idx:03d}",
            "scene_id": f"plot_{idx:03d}",
            "video_start": round(cur_start, 3),
            "video_end": round(cur_end, 3),
            "start": round(cur_start, 3),
            "end": round(cur_end, 3),
            "duration": round(cur_end - cur_start, 3),
            "timestamp": f"{fmt_time(cur_start)}-{fmt_time(cur_end)}",
            "subtitle_text": " ".join(texts).strip(),
            "source_text": " ".join(texts).strip(),
            "main_text_evidence": " ".join(texts).strip(),
            "boundary_start_reason": ["fallback_subtitle"],
            "boundary_end_reason": ["fallback_subtitle"],
            "boundary_confidence": "medium",
        })

    logger.warning("direct_runtime_v5 compatibility fallback produced chunks=%s", len(chunks))
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
    if _v4 is not None and hasattr(_v4, "guess_plot"):
        return _v4.guess_plot(text)
    for name, keys in PLOT_RULES:
        if any(k in text for k in keys):
            return name
    return "弱过渡" if len(text) < 20 else "发展"


def score_item(item: Dict[str, Any]):
    """
    v6 的评分表会调用这里。
    保持与 v5 经验一致：普通基础分降低，短片段/弱过渡扣分。
    """
    if _v4 is not None and hasattr(_v4, "score_item"):
        return _v4.score_item(item)

    text = str(item.get("subtitle_text") or item.get("source_text") or item.get("main_text_evidence") or "")
    duration = max(0.0, float(item.get("video_end", item.get("end", 0.0)) or 0.0) - float(item.get("video_start", item.get("start", 0.0)) or 0.0))
    plot = item.get("plot_function") or guess_plot(text)
    item["plot_function"] = plot
    reasons = []

    if plot in {"冲突升级", "反转", "高潮", "结局收束"}:
        story = 0.95
        reasons.append(f"强剧情功能:{plot}")
    elif plot in {"信息揭露", "阴谋推进", "关键决定", "人物转折", "关系变化"}:
        story = 0.82
        reasons.append(f"剧情推进:{plot}")
    elif plot in {"发展", "铺垫"}:
        story = 0.48
        reasons.append(f"主线铺垫:{plot}")
    else:
        story = 0.18
        reasons.append("弱过渡或低信息片段")

    info_tags = [k for k in ["真相", "秘密", "身份", "计划", "证据", "误会", "背叛", "陷害"] if k in text]
    emotion_tags = [k for k in ["哭", "流泪", "恨", "对不起", "怕", "崩溃", "紧张"] if k in text]

    char = 0.10
    if re.findall(r"[\u4e00-\u9fa5]{2,4}", text[:160]):
        char += 0.20
        reasons.append("存在人物线索")
    if any(k in text for k in ["决定", "相信", "怀疑", "背叛", "原谅", "离开", "留下"]):
        char += 0.30
        reasons.append("人物关系或目标变化")
    char = min(char, 1.0)

    info = 0.85 if info_tags else 0.05
    emotion = 0.78 if emotion_tags else 0.05
    visual = 0.25 if item.get("boundary_confidence") == "high" else 0.08
    importance = str(item.get("importance_level") or ("high" if plot in {"信息揭露", "冲突升级", "人物转折", "关键决定", "情感爆发", "阴谋推进"} else "medium"))
    continuity = 0.70 if importance == "high" else 0.45
    audio = 0.35 if plot in {"情感爆发", "冲突升级"} else 0.05

    penalty = 0.0
    if plot == "弱过渡":
        penalty += 0.12
        reasons.append("弱过渡扣分")
    if duration < cfg_float("movie_story_short_segment_penalty_seconds", 7.0) and not info_tags and not emotion_tags and story < 0.8:
        penalty += 0.18
        reasons.append("短片段且缺少强信息/强情绪扣分")
    if len(text.strip()) < 12 and story < 0.8:
        penalty += 0.10
        reasons.append("文本信息过少扣分")

    score = max(0.0, min(1.0, 0.25 * story + 0.20 * char + 0.15 * info + 0.15 * emotion + 0.10 * visual + 0.10 * continuity + 0.05 * audio - penalty))
    if info_tags:
        reasons.append("存在信息增量:" + ",".join(info_tags[:4]))
    if emotion_tags:
        reasons.append("存在情绪变化:" + ",".join(emotion_tags[:4]))

    return {
        "story_score": round(story, 3),
        "character_score": round(char, 3),
        "information_score": round(info, 3),
        "emotion_score": round(emotion, 3),
        "visual_score": round(visual, 3),
        "audio_score": round(audio, 3),
        "continuity_score": round(continuity, 3),
        "penalty": round(penalty, 3),
        "highlight_score": round(score, 3),
    }, reasons
