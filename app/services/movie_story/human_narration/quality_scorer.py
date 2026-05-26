# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

TEMPLATE_WORDS = ["首先", "其次", "然后", "随后", "与此同时", "然而", "由此可见", "故事情节", "事情并不简单"]
SUBTITLE_REPEAT_MIN = 16


def _sentences(text: str) -> List[str]:
    return [x.strip() for x in re.split(r"[。！？!?\n]+", str(text or "")) if x.strip()]


def _subtitle_repetition(text: str, source_text: str) -> float:
    t = re.sub(r"\s+", "", text or "")
    s = re.sub(r"\s+", "", source_text or "")
    if not t or not s:
        return 0.0
    hits = 0
    checks = 0
    for i in range(0, max(1, len(t) - SUBTITLE_REPEAT_MIN + 1), SUBTITLE_REPEAT_MIN):
        part = t[i:i + SUBTITLE_REPEAT_MIN]
        if len(part) < SUBTITLE_REPEAT_MIN:
            continue
        checks += 1
        hits += int(part in s)
    return round(hits / checks, 3) if checks else 0.0


def score_human_narration(script_items: Iterable[Dict[str, Any]], *, transitions: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    items = [x for x in script_items or [] if isinstance(x, dict)]
    transitions = list(transitions or [])
    issues: List[str] = []
    rewrite_candidates: List[str] = []
    if not items:
        return {"human_like_score": 0.0, "issues": ["没有可评分的解说脚本"], "rewrite_candidates": []}

    template_hits = 0
    repetition_scores: List[float] = []
    short_sentence_ratio_values: List[float] = []
    hook_like = 0
    subtext_like = 0

    for idx, item in enumerate(items, start=1):
        seg_id = str(item.get("segment_id") or item.get("highlight_id") or item.get("id") or idx)
        text = str(item.get("text") or item.get("narration") or item.get("script") or "")
        source_text = str(item.get("subtitle_text") or (item.get("source_segment") or {}).get("subtitle_text") or item.get("source_subtitle_text") or "")
        sents = _sentences(text)
        if not text.strip():
            issues.append(f"第 {idx} 段没有解说文本")
            rewrite_candidates.append(seg_id)
            continue
        template_hits += sum(1 for w in TEMPLATE_WORDS if w in text)
        rep = _subtitle_repetition(text, source_text)
        repetition_scores.append(rep)
        if rep >= 0.45:
            issues.append(f"第 {idx} 段复述字幕倾向较高")
            rewrite_candidates.append(seg_id)
        if sents:
            short_sentence_ratio_values.append(sum(1 for s in sents if len(s) <= 24) / len(sents))
        if any(k in text for k in ["没想到", "但他不知道", "真正", "注意看", "问题是"]):
            hook_like += 1
        if any(k in text for k in ["其实", "表面", "说明", "掩饰", "不是因为", "而是"]):
            subtext_like += 1

    avg_rep = sum(repetition_scores) / len(repetition_scores) if repetition_scores else 0.0
    short_ratio = sum(short_sentence_ratio_values) / len(short_sentence_ratio_values) if short_sentence_ratio_values else 0.0
    template_penalty = min(0.3, template_hits * 0.04)
    transition_score = min(1.0, len(transitions) / max(1, len(items) - 1)) if len(items) > 1 else 1.0
    hook_score = min(1.0, hook_like / max(1, min(3, len(items))))
    subtext_score = min(1.0, subtext_like / max(1, len(items)))
    human_like = max(0.0, min(1.0, 0.30 * (1 - avg_rep) + 0.22 * short_ratio + 0.18 * transition_score + 0.15 * hook_score + 0.15 * subtext_score - template_penalty))

    if template_hits >= 3:
        issues.append("模板化连接词偏多，建议进入反 AI 味改写")
    if transition_score < 0.6:
        issues.append("段落转场不足，整体像片段拼接")
    if hook_score < 0.35:
        issues.append("钩子句偏少，开头和转折不够抓人")

    return {
        "human_like_score": round(human_like, 3),
        "subtitle_repetition_score": round(avg_rep, 3),
        "transition_score": round(transition_score, 3),
        "sentence_rhythm_score": round(short_ratio, 3),
        "hook_score": round(hook_score, 3),
        "subtext_score": round(subtext_score, 3),
        "template_word_hits": template_hits,
        "issues": issues,
        "rewrite_candidates": sorted(set(rewrite_candidates)),
    }
