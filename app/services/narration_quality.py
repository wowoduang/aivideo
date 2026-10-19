from __future__ import annotations

"""Evidence-first narration workbench utilities.

Deterministic helpers for a complete narration review loop: normalize generated
script rows, build an evidence pack, score factual support/oral style/TTS fit,
produce conservative humanized rewrites, and persist review artifacts.  This
module intentionally has no provider dependency, so it works in local-first
installs even when no LLM/TTS account is configured.
"""

import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from app.repositories import artifact_repository
from app.utils import workspace

JsonDict = Dict[str, Any]

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
FORMAL_CONNECTORS = ("首先", "其次", "然后", "最后", "综上", "总而言之", "与此同时", "因此", "然而", "此外", "值得注意的是")
UNSUPPORTED_RISK_WORDS = ("凶手", "真凶", "原来", "真相是", "幕后", "一定是", "肯定是", "毫无疑问", "哥哥", "弟弟", "父亲", "母亲", "妻子", "丈夫")
STOPWORDS = {"the", "and", "that", "this", "一个", "这个", "那个", "他们", "我们", "时候", "因为", "所以", "但是", "然后", "已经", "没有", "自己"}

ROLE_LABELS = {
    "hook": "开头钩子",
    "setup": "背景交代",
    "turning_point": "剧情转折",
    "reveal": "信息揭示",
    "emotion": "情绪推进",
    "cliffhanger": "悬念收束",
    "summary": "总结收束",
}

PERSONA_PRESETS: Dict[str, JsonDict] = {
    "suspense": {"label": "悬疑紧张", "prefix": "这一刻，"},
    "emotional": {"label": "情绪共鸣", "prefix": "这一幕里，"},
    "fast": {"label": "爽感快节奏", "prefix": "下一秒，"},
    "documentary": {"label": "冷静纪实", "prefix": "从画面能看出，"},
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        out = ""
    elif isinstance(value, str):
        out = value.strip()
    elif isinstance(value, Mapping):
        out = "；".join(f"{k}:{_text(v)}" for k, v in value.items() if _text(v))
    elif isinstance(value, (list, tuple, set)):
        out = "；".join(_text(v) for v in value if _text(v))
    else:
        out = str(value).strip()
    return out[:max_chars].rstrip() if max_chars and len(out) > max_chars else out


def _as_dict(value: Any) -> JsonDict:
    return dict(value) if isinstance(value, Mapping) else {}


def parse_time_to_seconds(value: Any, default: float | None = 0.0) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return max(0.0, float(value))
    raw = _text(value)
    if not raw:
        return default
    if "-->" in raw:
        raw = raw.split("-->", 1)[0].strip()
    if "-" in raw and not raw.startswith("-"):
        raw = raw.split("-", 1)[0].strip()
    sec = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*s?$", raw, re.I)
    if sec:
        return max(0.0, float(sec.group(1)))
    clock = re.match(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:[,.](\d{1,3}))?$", raw)
    if clock:
        h = int(clock.group(1) or 0)
        m = int(clock.group(2) or 0)
        s = int(clock.group(3) or 0)
        ms = int((clock.group(4) or "0").ljust(3, "0")[:3])
        return h * 3600 + m * 60 + s + ms / 1000
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = parse_time_to_seconds(value, None)
    if parsed is not None:
        return parsed
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _end_from_item(item: Mapping[str, Any], start: float) -> float:
    ts = _text(item.get("timestamp"))
    if "-->" in ts:
        parsed = parse_time_to_seconds(ts.split("-->", 1)[1].strip(), None)
        if parsed is not None:
            return max(start + 0.1, parsed)
    if "-" in ts and not ts.startswith("-"):
        parsed = parse_time_to_seconds(ts.split("-", 1)[1].strip(), None)
        if parsed is not None:
            return max(start + 0.1, parsed)
    parsed = parse_time_to_seconds(item.get("endTime") or item.get("end") or item.get("video_end"), None)
    if parsed is not None:
        return max(start + 0.1, parsed)
    duration = _safe_float(item.get("duration"), 5.0)
    return start + max(0.1, duration)


def _stable_id(prefix: str, *parts: Any) -> str:
    seed = "|".join(_text(x) for x in parts if _text(x))
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:10]}" if seed else f"{prefix}_{uuid.uuid4().hex[:10]}"


def estimate_tts_duration(text: str, *, speed: float = 1.0) -> float:
    raw = _text(text)
    if not raw:
        return 0.0
    cjk = len(CJK_RE.findall(raw))
    words = len(WORD_RE.findall(raw))
    pauses = len(re.findall(r"[，,。.!！?？；;：:……]", raw)) * 0.16
    speed = max(0.35, min(2.0, speed or 1.0))
    return round(max(0.2, (cjk / 4.25 + words / 2.55 + pauses) / speed), 2)


def infer_script_role(index: int, total: int, item: Mapping[str, Any]) -> str:
    explicit = _text(item.get("role") or item.get("segment_role") or item.get("story_role")).lower()
    for key in ROLE_LABELS:
        if key in explicit:
            return key
    if total <= 1:
        return "summary"
    if index == 0:
        return "hook"
    if index >= total - 1:
        return "cliffhanger"
    ratio = index / max(1, total - 1)
    return "setup" if ratio < 0.25 else "turning_point" if ratio < 0.65 else "reveal"


def infer_emotion(item: Mapping[str, Any], narration: str) -> str:
    explicit = _text(item.get("emotion") or item.get("emotion_hint") or item.get("tone")).lower()
    if explicit:
        return explicit[:40]
    raw = f"{narration} {_text(item.get('originalSubtitle') or item.get('subtitle_text'))}"
    if any(k in raw for k in ("危险", "害怕", "紧张", "可怕", "杀", "逃")):
        return "tense"
    if any(k in raw for k in ("哭", "遗憾", "心疼", "告别", "失去")):
        return "emotional"
    if any(k in raw for k in ("发现", "真相", "秘密", "原来")):
        return "suspense"
    return "neutral"


def normalize_script_segments(script_items: Sequence[Mapping[str, Any]] | None) -> List[JsonDict]:
    rows = [dict(x) for x in (script_items or []) if isinstance(x, Mapping)]
    total = len(rows)
    out: List[JsonDict] = []
    for idx, raw in enumerate(rows):
        timestamp = _text(raw.get("timestamp"))
        start = parse_time_to_seconds(raw.get("startTime") or raw.get("start") or raw.get("video_start") or timestamp, 0.0) or 0.0
        end = _end_from_item(raw, start)
        narration = _text(raw.get("narration") or raw.get("new_content") or raw.get("content") or raw.get("text"), 4000)
        original = _text(raw.get("originalSubtitle") or raw.get("original_subtitle") or raw.get("subtitle_text") or raw.get("main_text_evidence") or raw.get("original"), 4000)
        seg_id = _text(raw.get("id") or raw.get("_id") or raw.get("segment_id") or raw.get("highlight_id")) or _stable_id("seg", idx, start, end, narration[:80])
        refs = raw.get("evidence_refs") or raw.get("evidenceRefs") or raw.get("source_evidence_ids") or []
        if not isinstance(refs, list):
            refs = [_text(refs)] if _text(refs) else []
        role = infer_script_role(idx, total, raw)
        emotion = infer_emotion(raw, narration)
        out.append({
            "id": str(seg_id), "index": idx + 1, "start": round(start, 3), "end": round(end, 3),
            "duration": round(max(0.1, end - start), 3), "startTime": _text(raw.get("startTime")) or f"{start:.2f}s",
            "endTime": _text(raw.get("endTime")) or f"{end:.2f}s", "timestamp": timestamp or f"{start:.3f}-{end:.3f}",
            "originalSubtitle": original, "narration": narration, "role": role, "role_label": ROLE_LABELS.get(role, "剧情段"),
            "emotion": emotion, "evidence_refs": [str(x) for x in refs if _text(x)],
            "estimated_tts_duration_sec": estimate_tts_duration(narration),
            "source": _text(raw.get("source") or raw.get("generation_mode")),
            "metadata": {k: v for k, v in raw.items() if k not in {"narration", "content", "text", "originalSubtitle", "original_subtitle"}},
        })
    return out



_CONFIDENCE_LABEL_SCORES: dict[str, float] = {
    "asr_high": 0.90,
    "asr_medium": 0.72,
    "asr_low": 0.55,
    "ocr_high": 0.90,
    "ocr_medium": 0.72,
    "ocr_low": 0.55,
    "visual_high": 0.90,
    "visual_medium": 0.72,
    "visual_low": 0.55,
    "subtitle_high": 0.90,
    "subtitle_medium": 0.72,
    "subtitle_low": 0.55,
}


def _normalize_evidence_confidence(raw: dict[str, object], source: str, index: int) -> float:
    """将 evidence 置信度规范化为 0~1 数值，未知标签直接报错。"""
    value = raw.get("confidence")
    if value is None or value == "":
        value = raw.get("score")
    if value is None or value == "":
        value = raw.get("importance_score")
    if value is None or value == "":
        value = 0.72

    if isinstance(value, str):
        stripped = value.strip()
        if stripped in _CONFIDENCE_LABEL_SCORES:
            return _CONFIDENCE_LABEL_SCORES[stripped]
        try:
            confidence = float(stripped)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported evidence confidence label: source={source}, "
                f"index={index}, value={value!r}"
            ) from exc
    else:
        confidence = float(value)

    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"Evidence confidence out of range: source={source}, "
            f"index={index}, value={value!r}, confidence={confidence}"
        )

    return confidence

def _evidence_from_item(raw: Mapping[str, Any], source: str, index: int) -> JsonDict:
    start = parse_time_to_seconds(raw.get("start") or raw.get("video_start") or raw.get("startTime") or raw.get("timestamp"), 0.0) or 0.0
    end = _end_from_item(raw, start)
    content = _text(raw.get("subtitle_text") or raw.get("main_text_evidence") or raw.get("originalSubtitle") or raw.get("original_subtitle") or raw.get("text") or raw.get("summary") or raw.get("narration_intent"), 1600)
    ev_id = _text(raw.get("evidence_id") or raw.get("id") or raw.get("segment_id") or raw.get("highlight_id")) or _stable_id("ev", source, index, start, end, content[:80])
    return {
        "id": str(ev_id), "start": round(start, 3), "end": round(max(start + 0.1, end), 3), "duration": round(max(0.1, end - start), 3),
        "type": source, "content": content, "characters": raw.get("characters") or raw.get("speaker_names") or [],
        "scene": _text(raw.get("scene") or raw.get("scene_id") or raw.get("story_function"), 200),
        "confidence": _normalize_evidence_confidence(raw, source, index),
        "raw_ref": _text(raw.get("path") or raw.get("artifact_type") or source),
    }


def build_evidence_pack(*, script_items: Sequence[Mapping[str, Any]] | None = None, highlights: Sequence[Mapping[str, Any]] | None = None, audit: Mapping[str, Any] | None = None) -> List[JsonDict]:
    evidence: List[JsonDict] = []
    seen: set[str] = set()

    def add(raw: Mapping[str, Any], source: str, idx: int) -> None:
        ev = _evidence_from_item(raw, source, idx)
        key = f"{ev['id']}|{ev['start']}|{ev['end']}|{ev['content'][:60]}"
        if key not in seen:
            seen.add(key)
            evidence.append(ev)

    for i, item in enumerate(script_items or [], 1):
        if isinstance(item, Mapping):
            add(item, "script_subtitle", i)
    for i, item in enumerate(highlights or [], 1):
        if isinstance(item, Mapping):
            add(item, "selected_highlight", i)
    audit_dict = _as_dict(audit)
    for key in ("selected_scene_evidence", "story_highlights", "highlight_narration_segments", "script_items"):
        for i, item in enumerate(audit_dict.get(key) or [], 1):
            if isinstance(item, Mapping):
                add(item, f"audit.{key}", i)
    return sorted(evidence, key=lambda x: (float(x.get("start") or 0), float(x.get("end") or 0)))


def _terms(text: str) -> set[str]:
    raw = _text(text).lower()
    return {x for x in re.findall(r"[\u4e00-\u9fff]{2,6}", raw) if x not in STOPWORDS} | {x for x in WORD_RE.findall(raw) if len(x) > 2 and x not in STOPWORDS}


def _text_overlap(left: str, right: str) -> float:
    a, b = _terms(left), _terms(right)
    return 0.0 if not a or not b else min(1.0, len(a & b) / max(1, min(len(a), len(b))))


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    base = max(0.1, min(max(0.1, a1 - a0), max(0.1, b1 - b0)))
    return min(1.0, inter / base)


def _supporting_evidence(segment: Mapping[str, Any], evidence_pack: Sequence[Mapping[str, Any]]) -> Tuple[List[JsonDict], float]:
    refs = {str(x) for x in (segment.get("evidence_refs") or []) if _text(x)}
    start, end = _safe_float(segment.get("start")), _safe_float(segment.get("end"))
    narration, original = _text(segment.get("narration")), _text(segment.get("originalSubtitle"))
    scored: List[Tuple[float, JsonDict]] = []
    for raw in evidence_pack:
        ev = dict(raw)
        ref_score = 1.0 if str(ev.get("id") or "") in refs else 0.0
        time_score = _overlap(start, end, _safe_float(ev.get("start")), _safe_float(ev.get("end"))) * 0.72
        txt_score = max(_text_overlap(narration, _text(ev.get("content"))), _text_overlap(original, _text(ev.get("content")))) * 0.82
        score = max(ref_score, time_score, txt_score)
        if score >= 0.12:
            ev["match_score"] = round(score, 3)
            scored.append((score, ev))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [ev for _, ev in scored[:5]]
    support = max([score for score, _ in scored[:3]] or ([0.35] if original else [0.0]))
    return top, round(min(1.0, max(0.0, support)), 3)


def _humanlike_score(text: str) -> Tuple[float, List[str]]:
    raw = _text(text)
    if not raw:
        return 0.0, ["解说为空"]
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(raw) if s.strip()] or [raw]
    avg_len = sum(map(len, sentences)) / len(sentences)
    max_len = max(map(len, sentences))
    score = 0.72
    issues: List[str] = []
    if 8 <= avg_len <= 34:
        score += 0.12
    else:
        score -= 0.12; issues.append("句长不够口播化，建议拆成更短的停顿句")
    if max_len > 58:
        score -= 0.14; issues.append("存在过长句，TTS 容易读成机器总结")
    hits = [x for x in FORMAL_CONNECTORS if x in raw]
    if hits:
        score -= min(0.18, 0.04 * len(hits)); issues.append(f"书面连接词偏多：{'、'.join(hits[:4])}")
    if any(k in raw for k in ("本文", "该片", "上述", "进行", "产生了", "异常现象")):
        score -= 0.1; issues.append("表达偏书面，建议改成口播动作句")
    if any(p in raw for p in ("？", "?", "……")):
        score += 0.05
    return round(max(0.0, min(1.0, score)), 3), issues


def _alignment_score(segment_duration: float, tts_duration: float) -> Tuple[float, str]:
    if segment_duration <= 0.1 or tts_duration <= 0.05:
        return 0.0, "缺少可对齐的画面时长或解说文本"
    ratio = tts_duration / segment_duration
    if 0.65 <= ratio <= 1.08:
        return round(1.0 - abs(0.88 - ratio) * 0.25, 3), "TTS 时长与画面基本匹配"
    if ratio > 1.08:
        return max(0.0, round(1.0 - min(1.0, ratio - 1.08), 3)), "解说预计偏长，建议压缩文案或延长画面"
    return max(0.0, round(1.0 - min(1.0, 0.65 - ratio), 3)), "解说预计偏短，画面可能出现空白"


def _average(values: Iterable[float], default: float = 0.0) -> float:
    nums = [float(x) for x in values if isinstance(x, (int, float)) and math.isfinite(float(x))]
    return round(sum(nums) / len(nums), 3) if nums else default


def _claims(segment: Mapping[str, Any], support_score: float, evidence: Sequence[Mapping[str, Any]]) -> List[JsonDict]:
    text = _text(segment.get("narration"))
    ev_text = "\n".join(_text(ev.get("content")) for ev in evidence)
    out: List[JsonDict] = []
    for word in UNSUPPORTED_RISK_WORDS:
        if word in text and word not in ev_text and support_score < 0.76:
            out.append({"segment_id": segment.get("id"), "text": word, "reason": "强剧情判断缺少证据支撑", "suggestion": "改成弱判断，或补充对应字幕/画面证据"})
    return out[:4]


def build_quality_report(*, script_items: Sequence[Mapping[str, Any]] | None = None, evidence_pack: Sequence[Mapping[str, Any]] | None = None, highlights: Sequence[Mapping[str, Any]] | None = None, audit: Mapping[str, Any] | None = None, speed: float = 1.0) -> JsonDict:
    segments = normalize_script_segments(script_items or [])
    evidence = list(evidence_pack or build_evidence_pack(script_items=script_items, highlights=highlights, audit=audit))
    rows: List[JsonDict] = []
    unsupported: List[JsonDict] = []
    timeline_penalty = 0
    prev_start = -1.0
    for seg in segments:
        supporting, factuality = _supporting_evidence(seg, evidence)
        human, human_issues = _humanlike_score(_text(seg.get("narration")))
        tts_duration = estimate_tts_duration(_text(seg.get("narration")), speed=speed)
        align, align_hint = _alignment_score(_safe_float(seg.get("duration")), tts_duration)
        if _safe_float(seg.get("start")) < prev_start:
            timeline_penalty += 1
        prev_start = _safe_float(seg.get("start"))
        c = _claims(seg, factuality, supporting)
        unsupported.extend(c)
        issues: List[str] = []
        if factuality < 0.35: issues.append("证据支撑不足：建议绑定原字幕/高光证据后再确认")
        issues.extend(human_issues[:3])
        if align < 0.68: issues.append(align_hint)
        rows.append({
            "segment_id": seg.get("id"), "index": seg.get("index"), "start": seg.get("start"), "end": seg.get("end"),
            "role": seg.get("role"), "role_label": seg.get("role_label"), "emotion": seg.get("emotion"),
            "factuality_score": factuality, "humanlike_score": human, "tts_alignment_score": align,
            "estimated_tts_duration_sec": tts_duration, "target_duration_sec": seg.get("duration"),
            "supporting_evidence": supporting, "issues": issues,
            "suggestions": _suggestions(seg, factuality, human, align),
        })
    factuality = _average([x["factuality_score"] for x in rows])
    human = _average([x["humanlike_score"] for x in rows])
    tts = _average([x["tts_alignment_score"] for x in rows])
    timeline = 1.0 if not segments else max(0.0, 1.0 - timeline_penalty / max(1, len(segments)))
    completeness = _average([1.0 if _text(s.get("narration")) else 0.0 for s in segments])
    overall = round(factuality * 0.34 + human * 0.26 + tts * 0.18 + timeline * 0.14 + completeness * 0.08, 3)
    blocking: List[str] = []
    if factuality < 0.45: blocking.append("整体证据支撑偏弱")
    if completeness < 0.99: blocking.append("存在空解说段")
    if timeline < 0.99: blocking.append("脚本时间线顺序存在倒序")
    actions: List[str] = []
    if unsupported: actions.append("优先处理 unsupported_claims：这些句子最容易造成剧情误导")
    if factuality < 0.68: actions.append("打开证据面板，逐段确认字幕/高光证据是否匹配")
    if human < 0.72: actions.append("执行真人口播优化，再人工检查是否改变事实")
    if tts < 0.72: actions.append("进入配音前先处理 TTS 时长偏差，避免声音和画面错位")
    if overall >= 0.82 and not actions: actions.append("质量稳定，可进入配音或保留当前版本")
    return {"version": "narration-quality-v1", "created_at": _now_iso(), "summary": {"overall_score": overall, "factuality_score": factuality, "timeline_score": round(timeline, 3), "humanlike_score": human, "tts_alignment_score": tts, "completeness_score": completeness, "segment_count": len(segments), "evidence_count": len(evidence), "blocking_issues": blocking}, "unsupported_claims": unsupported[:20], "segments": rows, "next_actions": actions[:5]}


def _suggestions(seg: Mapping[str, Any], factuality: float, human: float, align: float) -> List[str]:
    out: List[str] = []
    if factuality < 0.35: out.append("先补证据：给这段绑定原字幕、高光候选或关键帧描述")
    elif factuality < 0.65: out.append("把强判断改成弱判断，避免把推测说成事实")
    if human < 0.68: out.append("拆短句，减少书面连接词，加入自然停顿")
    if align < 0.68: out.append("检查 TTS 预计时长，必要时压缩文案或延长画面")
    return out[:4]


def _compact(text: str) -> str:
    out = _text(text)
    replacements = {"首先，": "", "其次，": "", "然后，": "接着，", "与此同时，": "同时，", "因此，": "所以，", "然而，": "但，", "异常现象": "不对劲", "使他感到非常紧张": "让他一下紧张起来", "发现了": "发现", "进入": "走进", "进行": ""}
    for old, new in replacements.items():
        out = out.replace(old, new)
    return re.sub(r"\s+", " ", out).strip()


def _avoid_overclaim(text: str) -> str:
    out = text
    for old, new in {"真相是": "线索指向", "原来": "看起来", "一定是": "很可能是", "肯定是": "像是", "毫无疑问": "从这里看"}.items():
        out = out.replace(old, new)
    return out


def _oralize(text: str, persona: str, index: int) -> str:
    out = _avoid_overclaim(_compact(text))
    if not out:
        return out
    prefix = PERSONA_PRESETS.get(persona, PERSONA_PRESETS["suspense"])["prefix"]
    if index == 0 and len(out) < 52 and not out.startswith(prefix):
        out = prefix + out
    if len(out) > 42 and "。" not in out[:42]:
        out = out.replace("，", "。", 1)
    if persona == "suspense" and len(out) <= 46 and any(k in out for k in ("发现", "危险", "不对劲", "真相", "身后")):
        out = out.rstrip("。.!！") + "……"
    elif not re.search(r"[。！？!?……]$", out):
        out += "。"
    return out


def build_prosody_plan(text: str, *, emotion: str = "neutral") -> JsonDict:
    if emotion in {"tense", "suspense"}: speed, pitch, pause = 0.92, -1, 0.55
    elif emotion == "emotional": speed, pitch, pause = 0.9, -1, 0.5
    elif emotion in {"fast", "excited"}: speed, pitch, pause = 1.06, 0, 0.25
    else: speed, pitch, pause = 1.0, 0, 0.35
    emphasis = [x for x in ("真相", "危险", "身后", "不对劲", "下一秒", "真正", "秘密") if x in _text(text)]
    return {"text": _text(text), "emotion": emotion or "neutral", "speed": speed, "pitch": pitch, "pause_before": 0.12, "pause_after": pause, "emphasis": emphasis[:3]}


def humanize_script_segments(script_items: Sequence[Mapping[str, Any]] | None, *, persona: str = "suspense", intensity: float = 0.65) -> JsonDict:
    persona = persona if persona in PERSONA_PRESETS else "suspense"
    intensity = max(0.0, min(1.0, float(intensity or 0.65)))
    segments = normalize_script_segments(script_items or [])
    rewritten: List[JsonDict] = []
    changes: List[JsonDict] = []
    for idx, seg in enumerate(segments):
        before = _text(seg.get("narration"))
        after = _oralize(before, persona, idx) if before and intensity >= 0.2 else before
        updated = dict(seg)
        updated["narration"] = after
        updated["estimated_tts_duration_sec"] = estimate_tts_duration(after)
        updated["prosody"] = build_prosody_plan(after, emotion=_text(seg.get("emotion")) or "neutral")
        rewritten.append(updated)
        if after != before:
            changes.append({"segment_id": seg.get("id"), "before": before, "after": after, "reason": "拆短句、弱化无证据强判断、增加口播停顿"})
    return {"persona": persona, "persona_label": PERSONA_PRESETS[persona]["label"], "intensity": intensity, "script_items": rewritten, "changes": changes, "quality_report": build_quality_report(script_items=rewritten)}


def build_timeline_blocks(script_items: Sequence[Mapping[str, Any]] | None, evidence_pack: Sequence[Mapping[str, Any]] | None = None) -> List[JsonDict]:
    evidence = list(evidence_pack or [])
    blocks: List[JsonDict] = []
    for seg in normalize_script_segments(script_items or []):
        supporting, score = _supporting_evidence(seg, evidence) if evidence else ([], 0.0)
        blocks.append({"id": seg["id"], "start": seg["start"], "end": seg["end"], "duration": seg["duration"], "label": seg.get("role_label") or "解说段", "narration": seg.get("narration") or "", "emotion": seg.get("emotion") or "neutral", "evidence_support_score": score, "evidence_ids": [ev.get("id") for ev in supporting[:3]], "estimated_tts_duration_sec": seg.get("estimated_tts_duration_sec")})
    return blocks


def write_narration_artifact(*, owner_email: str, project_id: str, artifact_type: str, payload: Mapping[str, Any], label: str, task_id: str = "") -> JsonDict:
    safe_type = re.sub(r"[^a-zA-Z0-9_-]+", "_", artifact_type).strip("_") or "narration"
    output_dir = Path(workspace.analysis_dir(f"projects/{project_id}/narration", create=True))
    path = output_dir / f"{safe_type}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    item = artifact_repository.upsert_artifact(owner_email=owner_email, project_id=project_id, task_id=task_id, artifact_type=artifact_type, path=str(path), label=label, metadata={"source": "narration_workbench", "created_at": _now_iso()})
    return item or {"path": str(path), "artifact_type": artifact_type, "label": label}
