# -*- coding: utf-8 -*-
"""Highlight type classification rules.

Pure module: no file I/O, no config access, no LLM call.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping
import re

Record = Dict[str, Any]

TYPE_CONFIGS: List[Record] = [
    {"key":"conflict_escalation","label":"冲突升级","quota":8,"aliases":["冲突升级","冲突","对抗","危机升级"],"keywords":["杀","打","打仗","开战","报仇","威胁","战场","敌","围","攻","拼命","死","刀","枪","炮","兵"],"score_fields":["story_score","emotion_score","audio_score"],"hint":"冲突被点燃或升级，人物对抗变得更直接。"},
    {"key":"information_reveal","label":"信息揭露","quota":7,"aliases":["信息揭露","真相揭露","背景交代","线索揭露"],"keywords":["原来","其实","告诉","知道","明白","发现","真相","身份","皇上","消息","情报","秘密","证据","为什么","怎么回事","什么是"],"score_fields":["information_score","story_score"],"hint":"片段交代关键背景、身份、真相或情报。"},
    {"key":"relationship_shift","label":"人物关系变化","quota":6,"aliases":["人物关系变化","关系转折","阵营变化"],"keywords":["兄弟","大哥","爹","娘","父","母","朋友","恩","背叛","投靠","认","相信","不信","救","欠","跟着","孙大哥","韩爷"],"score_fields":["character_score","story_score"],"hint":"人物称呼、立场、信任、敌友或亲缘关系出现变化。"},
    {"key":"goal_mission","label":"任务目标确立","quota":6,"aliases":["任务确立","目标确立","行动部署","计划推进"],"keywords":["必须","任务","命令","调令","率","主力","目标","计划","安排","部署","行动","一定","不能","先","杀出","伏击","重任"],"score_fields":["story_score","information_score"],"hint":"片段明确下一步目标、任务、行动路线或战术安排。"},
    {"key":"reversal_crisis","label":"反转危机","quota":6,"aliases":["反转","危机","意外","局势变化"],"keywords":["没想到","突然","但是","可是","却","糟了","坏了","危险","埋伏","中计","陷阱","不对","变了","来不及","完了","恐怕"],"score_fields":["story_score","emotion_score"],"hint":"局势突然变化，人物陷入危险或原有判断被推翻。"},
    {"key":"emotional_outburst","label":"情绪爆发","quota":6,"aliases":["情绪爆发","情绪变化","情绪冲突"],"keywords":["哭","笑","怒","生气","激动","求","恨","怕","伤心","高兴","别","滚","闭嘴","放开","混蛋","放屁","哼"],"score_fields":["emotion_score","audio_score"],"hint":"片段包含明显情绪释放，适合做情绪型高光。"},
    {"key":"character_moment","label":"人物高光","quota":5,"aliases":["人物高光","角色高光","人物抉择"],"keywords":["我来","交给我","我不怕","我不能","我不会","我一定","让我","我去","放心","扛","保护","担当","重任","英雄"],"score_fields":["character_score","story_score","emotion_score"],"hint":"人物展现能力、态度、承担、选择或价值立场。"},
    {"key":"suspense_foreshadow","label":"悬念伏笔","quota":5,"aliases":["悬念","伏笔","线索"],"keywords":["等着","以后","迟早","秘密","线索","不知道","还有","未必","恐怕","小心","记住","总有一天","究竟","到底"],"score_fields":["information_score","story_score"],"hint":"片段埋下后续疑问、线索或危险预告。"},
    {"key":"action_visual","label":"动作视觉场面","quota":5,"aliases":["动作","视觉场面","战斗"],"keywords":["枪","炮","刀","马","冲","跑","追","打","炸","火","军","兵","战","杀出","伏击"],"score_fields":["visual_score","audio_score","story_score"],"hint":"片段具有动作、战斗、运动或视听冲击。"},
    {"key":"comedy_relief","label":"喜剧爽点","quota":4,"aliases":["喜剧","爽点","轻松段落"],"keywords":["哈哈","笑","笨","傻","有意思","逗","玩笑","胡说","吹牛","别闹","喝酒吃肉"],"score_fields":["emotion_score","audio_score"],"hint":"片段带有轻松、反差、幽默或爽感表达。"},
    {"key":"key_line","label":"关键台词","quota":6,"aliases":["关键台词","金句","核心台词"],"keywords":["记住","告诉","必须","一定","不能","不许","从今以后","这就是","我告诉你","你给我","我问你"],"score_fields":["story_score","character_score","emotion_score"],"hint":"台词短而有力，能直接承载剧情信息或人物态度。"},
]

KEY_BY_LABEL = {c["label"]: c["key"] for c in TYPE_CONFIGS}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(x) for x in value)
    if isinstance(value, dict):
        return " ".join(f"{k}:{_as_text(v)}" for k, v in value.items())
    return str(value)


def item_text(item: Mapping[str, Any]) -> str:
    parts = []
    for key in ("text", "subtitle_text", "source_text", "summary", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(dict.fromkeys(parts))


def _evidence_snippet(text: str, keywords: List[str]) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    for kw in keywords:
        pos = clean.find(kw)
        if pos >= 0:
            return clean[max(0, pos - 22): min(len(clean), pos + len(kw) + 42)].strip()
    return clean[:80].strip()


def classify_scene(item: Mapping[str, Any], *, min_confidence: float = 0.52, fallback_confidence: float = 0.45) -> List[Record]:
    """Return concrete highlight types supported by text/rule evidence."""
    text = item_text(item)
    searchable = " ".join([text, _as_text(item.get("plot_function")), _as_text(item.get("selection_reasons")), _as_text(item.get("reasons")), _as_text(item.get("highlight_reasons"))])
    base_score = safe_float(item.get("highlight_score", item.get("score", 0.0)))
    out: List[Record] = []
    for cfg in TYPE_CONFIGS:
        matched = [kw for kw in cfg["keywords"] if kw and kw in searchable]
        plot_text = _as_text(item.get("plot_function"))
        plot_hit = bool(plot_text and any(alias in plot_text for alias in cfg["aliases"]))
        reason_hit = any(alias in searchable for alias in cfg["aliases"])
        evidence = []
        if matched:
            evidence.append("keyword:" + ",".join(matched[:5]))
        if plot_hit:
            evidence.append("plot_function")
        elif reason_hit:
            evidence.append("reason_alias")
        if not evidence:
            continue
        score_signal = sum(safe_float(item.get(f, 0.0)) for f in cfg["score_fields"]) / max(1, len(cfg["score_fields"]))
        # A plot_function match is curated upstream evidence.  It must be enough
        # to create a typed candidate even when the audit/source text is empty
        # (common after aggressive subtitle cleaning or manifest-only replays).
        confidence = 0.20 + min(0.36, 0.10 * len(matched)) + (0.34 if plot_hit else 0.12 if reason_hit else 0.0) + min(0.22, score_signal * 0.18) + min(0.10, base_score * 0.12)
        confidence = max(0.0, min(0.98, confidence))
        if confidence < fallback_confidence:
            continue
        snippet = _evidence_snippet(text, matched or cfg["keywords"])
        if not snippet and plot_hit:
            snippet = plot_text
        if not snippet and reason_hit:
            snippet = searchable[:80].strip()
        if not snippet:
            continue
        out.append({
            "highlight_type_key": cfg["key"],
            "highlight_type": cfg["label"],
            "type_confidence": round(confidence, 3),
            "type_evidence": evidence,
            "matched_keywords": matched[:8],
            "evidence_text": snippet,
            "narration_hint": cfg["hint"],
            "selected": confidence >= min_confidence,
        })
    out.sort(key=lambda x: (safe_float(x.get("type_confidence")), len(x.get("matched_keywords") or [])), reverse=True)
    return out


def parse_type_quotas(raw: str | None) -> Dict[str, int]:
    quotas = {c["key"]: int(c.get("quota", 5)) for c in TYPE_CONFIGS}
    if not raw:
        return quotas
    for part in str(raw).replace("；", ",").replace(";", ",").split(","):
        if ":" not in part:
            continue
        name, value = [x.strip() for x in part.split(":", 1)]
        try:
            quota = max(0, int(float(value)))
        except Exception:
            continue
        key = KEY_BY_LABEL.get(name, name)
        if key in quotas:
            quotas[key] = quota
    return quotas
