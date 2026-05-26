
from __future__ import annotations

"""Stage-A evidence enrichment for migrating the legacy narration logic.

This module is intentionally about **inputs to narration**, not narration text.
It rebuilds the legacy project's strong layer: global story context, local story
understanding, plot function, conflict/motivation, narration intent, and a
machine-readable evidence completeness score.
"""

from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Sequence

JsonDict = Dict[str, Any]

REQUIRED_EVIDENCE_FIELDS = [
    "subtitle_text",
    "surface_dialogue_meaning",
    "real_narrative_state",
    "conflict_summary",
    "character_motivation",
    "story_function",
    "plot_function",
    "importance_level",
    "narration_intent",
    "_global_summary",
]

RECOMMENDED_EVIDENCE_FIELDS = [
    "local_understanding",
    "story_validation",
    "main_text_evidence",
    "emotion_hint",
    "raw_voice_retain_suggestion",
]


def _text(value: Any, max_chars: int = 0) -> str:
    text = str(value or "").strip()
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def _first_nonempty(*values: Any, max_chars: int = 0) -> str:
    for value in values:
        text = _text(value, max_chars=max_chars)
        if text:
            return text
    return ""


def _unique(values: Iterable[Any], limit: int = 0) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def _join_snippets(values: Iterable[Any], *, limit: int = 5, max_chars: int = 400) -> str:
    pieces = _unique(values, limit=limit)
    text = "；".join(pieces)
    return text[:max_chars].strip("；")


def _item_text(item: Mapping[str, Any]) -> str:
    return _first_nonempty(
        item.get("subtitle_text"),
        item.get("main_text_evidence"),
        item.get("source_text"),
        item.get("text"),
        max_chars=1200,
    )


def _iter_item_text(items: Iterable[Mapping[str, Any]]) -> Iterable[str]:
    for item in items or []:
        if isinstance(item, Mapping):
            text = _item_text(item)
            if text:
                yield text


def _infer_genre(text: str) -> str:
    if any(k in text for k in ["皇上", "朕", "臣", "朝廷", "钦差", "银库", "灾民"]):
        return "历史宫廷/王朝权力"
    if any(k in text for k in ["总裁", "公司", "合同", "项目", "董事", "客户"]):
        return "都市职场/商业冲突"
    if any(k in text for k in ["尸体", "凶手", "警察", "案", "线索", "真相"]):
        return "悬疑罪案"
    if any(k in text for k in ["结婚", "离婚", "孩子", "母亲", "父亲", "家", "妻子", "丈夫"]):
        return "家庭伦理/情感关系"
    return "剧情解说"


def _infer_main_conflict(text: str) -> str:
    if any(k in text for k in ["银库", "催征", "税银", "饥民", "灾", "抗税", "朝廷"]):
        return "权力财政需求与民间生存困境之间的矛盾持续升级。"
    if any(k in text for k in ["皇上", "朕", "臣", "钦差"]):
        return "上位者的命令与执行者面对的现实压力发生冲突。"
    if any(k in text for k in ["真相", "隐瞒", "秘密", "怀疑"]):
        return "被隐藏的信息逐步暴露，人物关系和局势随之改变。"
    if any(k in text for k in ["结婚", "离婚", "背叛", "孩子", "家"]):
        return "人物关系中的隐瞒、责任和情感矛盾不断激化。"
    if any(k in text for k in ["钱", "债", "公司", "合同", "项目"]):
        return "利益压力推动人物作出选择，并引发新的冲突。"
    return "人物目标、外部压力和隐藏信息共同推动剧情向前发展。"


def _infer_theme(text: str, genre: str) -> str:
    if "王朝" in genre or "宫廷" in genre:
        return "权力、财政压力与底层生存之间的冲突。"
    if "悬疑" in genre:
        return "真相被逐步揭开，人物处境随线索改变。"
    if "家庭" in genre or "情感" in genre:
        return "亲密关系中的隐瞒、责任和情绪爆发。"
    if "职场" in genre:
        return "利益博弈下的人物选择与关系变化。"
    return "人物在压力下作出选择，推动冲突和信息逐步展开。"


def _extract_characters(text: str) -> List[str]:
    role_words = [
        "皇上", "皇帝", "娘娘", "大臣", "钦差", "灾民", "百姓", "朱重八", "和尚", "父亲", "母亲",
        "女人", "男人", "女主", "男主", "老板", "总裁", "警察", "凶手", "孩子", "妻子", "丈夫",
    ]
    return _unique([w for w in role_words if w in text], limit=10)


def _summarize_surface(text: str) -> str:
    t = _text(text, 220)
    if not t:
        return ""
    if "任命" in t and "钦差" in t:
        return "皇帝安排臣子承担催税任务，朝廷压力开始向外传导。"
    if "银库" in t or "储银" in t:
        return "朝廷财政吃紧，钱粮危机浮出水面。"
    if "饥民" in t or "灾" in t or "抗税" in t:
        return "民间灾荒与催税压力正面碰撞。"
    if "生日" in t:
        return "宫廷内部仍在关注排场和需求，与外部危机形成反差。"
    if "真相" in t or "秘密" in t or "发现" in t:
        return "隐藏信息开始浮出水面，局势发生变化。"
    if "哭" in t or "求" in t:
        return "人物情绪被推到高点，矛盾开始外化。"
    return t[:120]


def _build_timeline_summary(texts: Sequence[str], max_nodes: int = 6) -> List[str]:
    nodes: List[str] = []
    for text in texts:
        summary = _summarize_surface(text)
        if summary and summary not in nodes:
            nodes.append(summary)
        if len(nodes) >= max_nodes:
            break
    if not nodes:
        nodes = ["剧情开端建立人物处境。", "核心冲突逐步出现。", "人物选择推动后续发展。"]
    return nodes


def _score_global_context(context: Mapping[str, Any]) -> JsonDict:
    required = ["main_conflict", "main_characters", "story_theme", "timeline_summary", "genre"]
    present, missing = [], []
    for key in required:
        value = context.get(key)
        ok = bool(value) and (not isinstance(value, list) or len(value) > 0)
        (present if ok else missing).append(key)
    score = round(len(present) / len(required), 3)
    return {"score": score, "present": present, "missing": missing, "passed": score >= 0.8 and len(context.get("timeline_summary") or []) >= 3}


def build_global_story_context(
    plot_chunks: Sequence[Mapping[str, Any]] | None = None,
    full_subtitle_understanding: Mapping[str, Any] | None = None,
    existing_global_summary: Mapping[str, Any] | None = None,
    *,
    video_title: str = "",
) -> JsonDict:
    chunks = list(plot_chunks or [])
    fsu = dict(full_subtitle_understanding or {})
    existing = dict(existing_global_summary or {})
    texts = list(_iter_item_text(chunks))
    fsu_text = _join_snippets([
        fsu.get("story_summary"), fsu.get("overall_summary"), fsu.get("main_storyline"), fsu.get("full_summary")
    ], limit=4, max_chars=800)
    all_text = _join_snippets([fsu_text] + texts, limit=12, max_chars=2600)

    genre = _first_nonempty(existing.get("genre"), existing.get("story_genre"), fsu.get("genre"), _infer_genre(all_text))
    main_conflict = _first_nonempty(
        existing.get("main_conflict"), existing.get("core_conflict"), fsu.get("main_conflict"), fsu.get("core_conflict"), _infer_main_conflict(all_text), max_chars=260
    )
    story_theme = _first_nonempty(existing.get("story_theme"), existing.get("theme"), fsu.get("story_theme"), _infer_theme(all_text, genre), max_chars=260)
    characters = _unique(
        list(existing.get("main_characters") or []) + list(existing.get("characters") or []) + list(fsu.get("main_characters") or []) + _extract_characters(all_text),
        limit=12,
    )
    timeline_summary = _unique(list(existing.get("timeline_summary") or existing.get("story_beats") or fsu.get("timeline_summary") or []), limit=8)
    if len(timeline_summary) < 3:
        timeline_summary = _unique(timeline_summary + _build_timeline_summary(texts, max_nodes=6), limit=8)
    if len(timeline_summary) < 3:
        timeline_summary = _unique(timeline_summary + [
            "核心矛盾被建立。",
            "人物在压力下作出选择。",
            "后续冲突由此继续推进。",
        ], limit=8)

    context: JsonDict = dict(existing)
    context.update({
        "migration_stage": "stage_a_global_local_evidence",
        "global_story_context_ready": True,
        "video_title": _first_nonempty(video_title, existing.get("video_title")),
        "genre": genre,
        "main_conflict": main_conflict,
        "story_theme": story_theme,
        "main_characters": characters,
        "timeline_summary": timeline_summary,
        "relationship_map": existing.get("relationship_map") or fsu.get("relationship_map") or [],
        "risk_flags": _unique(list(existing.get("risk_flags") or []) + list(fsu.get("risk_flags") or []), limit=12),
        "full_subtitle_understanding": fsu,
    })
    context["migration_quality"] = _score_global_context(context)
    return context


def _infer_plot_function(text: str, item: Mapping[str, Any] | None = None) -> str:
    item = item or {}
    existing = _text(item.get("plot_function"))
    if existing and existing.lower() not in {"none", "null", "nan"}:
        return existing
    if any(k in text for k in ["竟然", "没想到", "突然", "原来", "真相", "反而", "却"]):
        return "反转"
    if any(k in text for k in ["任命", "决定", "命令", "赴", "必须", "现在就", "立刻"]):
        return "关键决定"
    if any(k in text for k in ["饥民", "抗税", "冲", "吵", "杀", "打", "逼", "威胁", "质问"]):
        return "冲突升级"
    if any(k in text for k in ["生日", "银库", "储银", "秘密", "知道", "告诉", "发现"]):
        return "信息揭露"
    if any(k in text for k in ["哭", "求", "舍不得", "绝望", "心疼", "愤怒"]):
        return "情绪爆发"
    if any(k in text for k in ["后来", "从此", "终于", "结局", "最后"]):
        return "结局收束"
    return "信息推进"


def _infer_importance(text: str, plot_function: str, item: Mapping[str, Any] | None = None) -> str:
    item = item or {}
    existing = _text(item.get("importance_level")).lower()
    if existing in {"high", "medium", "low"}:
        return existing
    score = 0
    if plot_function in {"反转", "冲突升级", "情绪爆发", "关键决定", "信息揭露"}:
        score += 2
    if any(k in text for k in ["皇上", "朕", "钦差", "饥民", "灾", "真相", "秘密", "决定", "任命"]):
        score += 1
    if len(text) >= 28:
        score += 1
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"




def _looks_shallow(value: Any, source_text: str) -> bool:
    text = _text(value)
    src = _text(source_text)
    if not text:
        return True
    if src and text == src[:len(text)]:
        return True
    if src and len(text) >= 18 and text in src:
        return True
    if len(text) < 10:
        return True
    return False

def _real_state(text: str, global_context: Mapping[str, Any], plot_function: str) -> str:
    main_conflict = _text(global_context.get("main_conflict"), 180)
    if "任命" in text and "钦差" in text:
        return "这不是简单任命，而是权力把财政压力继续压向地方和百姓。"
    if "饥民" in text or "抗税" in text:
        return "百姓并非单纯反抗命令，而是已经被灾荒和税负逼到生存边缘。"
    if "银库" in text or "储银" in text:
        return "国库空虚成为后续决策的直接压力源。"
    if "生日" in text:
        return "宫廷享乐需求与财政危机形成反差，强化了权力层和民间处境的不对等。"
    if plot_function == "反转":
        return "表面局势被新的信息改写，人物处境发生转向。"
    if plot_function == "情绪爆发":
        return "长期压抑的矛盾在这一刻外露，人物关系进入更激烈阶段。"
    return f"这一段服务于主线：{main_conflict}" if main_conflict else "这一段推动人物处境和故事信息继续展开。"


def _conflict_summary(text: str, global_context: Mapping[str, Any]) -> str:
    if "银库" in text or "储银" in text or "税" in text or "饥民" in text:
        return "朝廷要钱与百姓承受能力之间的矛盾被推到台前。"
    if "皇上" in text or "朕" in text or "臣" in text:
        return "上位者的要求和执行者面对的现实压力出现冲突。"
    if "秘密" in text or "真相" in text:
        return "隐藏信息和人物真实立场之间形成悬念。"
    return _text(global_context.get("main_conflict"), 180) or "人物目标与外部压力之间形成冲突。"


def _character_motivation(text: str, global_context: Mapping[str, Any]) -> str:
    if "皇上" in text or "朕" in text:
        return "掌权者急于解决眼前压力，倾向用命令推进局面。"
    if "臣" in text or "钦差" in text:
        return "执行者既要服从命令，又意识到现实代价。"
    if "饥民" in text or "百姓" in text:
        return "底层人物的行动源于生存压力，而不是单纯对抗。"
    if "生日" in text:
        return "宫廷人物仍在维护自身需求和排场。"
    return "人物在当前压力下作出选择，推动剧情继续向前。"


def _story_function(plot_function: str, text: str) -> str:
    mapping = {
        "关键决定": "推动主线进入执行阶段",
        "冲突升级": "把隐藏矛盾推到明面",
        "信息揭露": "补充观众理解剧情所需的关键信息",
        "反转": "改变观众对局势或人物的判断",
        "情绪爆发": "释放人物长期积累的矛盾情绪",
        "铺垫": "为后续冲突或反转建立背景",
        "结局收束": "回应前文矛盾并完成阶段性收束",
    }
    return mapping.get(plot_function, "推进剧情信息并连接前后事件")


def _emotion_hint(text: str, plot_function: str) -> str:
    if "饥民" in text or "灾" in text or "抗税" in text:
        return "压迫/紧张"
    if "生日" in text:
        return "反差/讽刺"
    if plot_function == "情绪爆发":
        return "强情绪"
    if plot_function == "反转":
        return "震惊/悬念"
    if plot_function == "冲突升级":
        return "紧张"
    return "推进"


def _narration_intent(row: Mapping[str, Any]) -> JsonDict:
    conflict = _text(row.get("conflict_summary"), 160)
    motivation = _text(row.get("character_motivation"), 160)
    story_function = _text(row.get("story_function"), 120)
    plot_function = _text(row.get("plot_function"), 40)
    real_state = _text(row.get("real_narrative_state"), 220)
    return {
        "intent": _join_snippets([
            f"这一段要讲：{real_state}" if real_state else "",
            f"剧情功能：{story_function}" if story_function else "",
            f"核心冲突：{conflict}" if conflict else "",
        ], limit=3, max_chars=360),
        "must_explain": _unique([conflict, motivation, story_function, plot_function], limit=5),
        "avoid": ["逐句复述字幕", "只写某人说了什么", "脱离当前时间窗提前剧透"],
        "evidence_role": plot_function or "信息推进",
    }


def score_evidence_item(item: Mapping[str, Any]) -> JsonDict:
    missing_required, present_required = [], []
    for key in REQUIRED_EVIDENCE_FIELDS:
        value = item.get(key)
        ok = bool(value) and (not isinstance(value, dict) or len(value) > 0) and (not isinstance(value, list) or len(value) > 0)
        (present_required if ok else missing_required).append(key)
    missing_recommended, present_recommended = [], []
    for key in RECOMMENDED_EVIDENCE_FIELDS:
        value = item.get(key)
        ok = bool(value) and (not isinstance(value, dict) or len(value) > 0) and (not isinstance(value, list) or len(value) > 0)
        (present_recommended if ok else missing_recommended).append(key)
    required_score = len(present_required) / max(1, len(REQUIRED_EVIDENCE_FIELDS))
    recommended_score = len(present_recommended) / max(1, len(RECOMMENDED_EVIDENCE_FIELDS))
    score = round(required_score * 0.8 + recommended_score * 0.2, 3)
    return {
        "score": score,
        "required_score": round(required_score, 3),
        "recommended_score": round(recommended_score, 3),
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "passed": required_score >= 0.9,
    }


def enrich_evidence_item(item: Mapping[str, Any], global_context: Mapping[str, Any] | None = None) -> JsonDict:
    global_context = dict(global_context or {})
    row = dict(item or {})
    text = _item_text(row)
    plot_function = _infer_plot_function(text, row)
    importance = _infer_importance(text, plot_function, row)
    inferred_surface = _summarize_surface(text)
    surface = _text(row.get("surface_dialogue_meaning"), 320)
    if _looks_shallow(surface, text):
        surface = inferred_surface
    inferred_real = _real_state(text, global_context, plot_function)
    real = _text(row.get("real_narrative_state"), 420)
    if _looks_shallow(real, text):
        real = inferred_real
    conflict = _first_nonempty(row.get("conflict_summary"), _conflict_summary(text, global_context), max_chars=260)
    motivation = _first_nonempty(row.get("character_motivation"), _character_motivation(text, global_context), max_chars=260)
    story_function = _first_nonempty(row.get("story_function"), _story_function(plot_function, text), max_chars=180)
    local = dict(row.get("local_understanding") or {})
    local.update({
        "surface_dialogue_meaning": surface,
        "real_narrative_state": real,
        "conflict_summary": conflict,
        "character_motivation": motivation,
        "story_function": story_function,
        "plot_function": plot_function,
        "importance_level": importance,
        "emotion": _first_nonempty(local.get("emotion"), row.get("emotion_hint"), _emotion_hint(text, plot_function)),
        "core_event": _first_nonempty(local.get("core_event"), real, surface, max_chars=240),
    })
    row.update({
        "subtitle_text": _first_nonempty(row.get("subtitle_text"), row.get("source_text"), row.get("text"), max_chars=1200),
        "main_text_evidence": _first_nonempty(row.get("main_text_evidence"), row.get("subtitle_text"), row.get("source_text"), row.get("text"), max_chars=1200),
        "surface_dialogue_meaning": surface,
        "real_narrative_state": real,
        "conflict_summary": conflict,
        "character_motivation": motivation,
        "story_function": story_function,
        "plot_function": plot_function,
        "importance_level": importance,
        "emotion_hint": _first_nonempty(row.get("emotion_hint"), local.get("emotion"), _emotion_hint(text, plot_function)),
        "local_understanding": local,
        "_global_summary": global_context,
    })
    if "raw_voice_retain_suggestion" not in row:
        row["raw_voice_retain_suggestion"] = plot_function in {"情绪爆发", "反转"}
    row["narration_intent"] = row.get("narration_intent") or _narration_intent(row)
    row["evidence_completeness"] = score_evidence_item(row)
    return row


def enrich_evidence_items(items: Sequence[Mapping[str, Any]] | None, global_context: Mapping[str, Any] | None = None) -> List[JsonDict]:
    return [enrich_evidence_item(item, global_context) for item in list(items or []) if isinstance(item, Mapping)]


def evaluate_evidence_items(items: Sequence[Mapping[str, Any]] | None, *, min_pass_rate: float = 0.9) -> JsonDict:
    rows = list(items or [])
    total = len(rows)
    scored = []
    for index, item in enumerate(rows, start=1):
        score = item.get("evidence_completeness") if isinstance(item, Mapping) else None
        if not isinstance(score, Mapping):
            score = score_evidence_item(item or {})
        scored.append({
            "idx": index,
            "id": (item or {}).get("highlight_id") or (item or {}).get("segment_id") or (item or {}).get("scene_id") or (item or {}).get("id"),
            "score": score.get("score"),
            "passed": bool(score.get("passed")),
            "missing_required": score.get("missing_required") or [],
            "missing_recommended": score.get("missing_recommended") or [],
        })
    passed = sum(1 for x in scored if x.get("passed"))
    pass_rate = round(passed / total, 3) if total else 0.0
    counter = Counter()
    for row in scored:
        for key in row.get("missing_required") or []:
            counter[key] += 1
    return {
        "stage": "stage_a_global_local_evidence",
        "total": total,
        "passed": passed,
        "failed": max(0, total - passed),
        "pass_rate": pass_rate,
        "target_pass_rate": min_pass_rate,
        "overall_passed": bool(total and pass_rate >= min_pass_rate),
        "top_missing_required": counter.most_common(12),
        "items": scored,
    }


__all__ = [
    "REQUIRED_EVIDENCE_FIELDS",
    "RECOMMENDED_EVIDENCE_FIELDS",
    "build_global_story_context",
    "enrich_evidence_item",
    "enrich_evidence_items",
    "score_evidence_item",
    "evaluate_evidence_items",
]
