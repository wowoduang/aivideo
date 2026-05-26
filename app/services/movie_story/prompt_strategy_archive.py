from __future__ import annotations

"""Prompt strategy profiles and score archive for movie-story narration.

This module deliberately stores prompt *strategy*, not fallback copy.  A strategy
describes how the model should write and what it must avoid.  Test runs can
record scores by movie category so future runs can prefer strategies that worked
well for similar material.
"""

import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from loguru import logger

from app.utils.workspace import project_root

JsonDict = Dict[str, Any]


STRATEGY_PROFILES: Dict[str, JsonDict] = {
    "historical_pressure": {
        "strategy_id": "historical_pressure",
        "label": "历史压迫线",
        "suited_categories": ["历史宫廷", "战争权谋", "通用剧情"],
        "draft_instruction": (
            "按历史正剧冷沉写实风写。先抓时代压力、阶级压迫和权力传导，再落到人物处境。"
            "少描述动作，多解读背后原因；不要复述字幕，不要网红文案，不要堆成论文腔。"
        ),
        "visual_rewrite_instruction": (
            "视觉二改优先使用朝堂、官差、跪求、抢夺、饥荒、军营等可见动作和场景，"
            "让压迫感从画面里出来。"
        ),
        "do_write": [
            "按时间轴一段镜头一段解说",
            "70%镜头解读、20%历史/时代背景、10%人物心理",
            "把税、粮、饥荒、权力压迫写成因果链",
            "用低沉、冷静、克制的中年旁白口吻",
        ],
        "do_not_write": [
            "不要写成历史论文或学术术语堆砌",
            "不要复述表面剧情或照搬字幕",
            "不要结尾升华、鸡汤或总结大道理",
            "不要反复使用乱世、压迫、活路等同一组词",
            "不要用看透人性、人间疾苦、乱世浮沉、宿命轮回、凡尘棋局、至高格局",
        ],
    },
    "character_growth": {
        "strategy_id": "character_growth",
        "label": "人物成长线",
        "suited_categories": ["历史宫廷", "家庭伦理", "爱情情感", "通用剧情"],
        "draft_instruction": (
            "围绕主角从处境、选择、代价到转变来写。不要急着拔高成传奇，"
            "先让观众看见这个人为什么一步步变成后来那样。"
        ),
        "visual_rewrite_instruction": (
            "视觉二改优先抓主角的沉默、低头、跪求、递物、奔走、挨饿等动作，"
            "把人物变化写得具体。"
        ),
        "do_write": [
            "用人物遭遇串起事件",
            "把选择写成被处境逼出来的结果",
            "转场句要自然承接人物心境",
        ],
        "do_not_write": [
            "不要每段都说命运转折",
            "不要提前把人物写成未来大人物",
            "不要空泛夸主角格局、城府、非池中物",
        ],
    },
    "suspense_short_video": {
        "strategy_id": "suspense_short_video",
        "label": "短视频悬念线",
        "suited_categories": ["悬疑罪案", "江湖动作", "都市职场", "通用剧情"],
        "draft_instruction": (
            "句子更短，推进更快。每个高光都要给观众一个继续看的理由，"
            "但不能编造悬念，不能把还没发生的剧情提前说破。"
        ),
        "visual_rewrite_instruction": (
            "视觉二改优先抓异常动作、对峙、追逐、刀兵、表情变化和沉默停顿。"
        ),
        "do_write": [
            "开头要快进入冲突",
            "高光处增强危险感或反差",
            "过渡段少写，别拖",
        ],
        "do_not_write": [
            "不要滥用'真正的看点来了'",
            "不要每句都制造悬念",
            "不要把剧情说成营销标题",
        ],
    },
    "documentary_plain": {
        "strategy_id": "documentary_plain",
        "label": "纪录片旁白线",
        "suited_categories": ["战争权谋", "历史宫廷", "通用剧情"],
        "draft_instruction": (
            "语气克制、清楚、稳。重点是把事实、因果、人物处境讲明白，"
            "不追求夸张爽点。"
        ),
        "visual_rewrite_instruction": (
            "视觉二改只补确定能看见的动作和环境，不强行煽情。"
        ),
        "do_write": [
            "用清楚的因果句",
            "保留适当留白",
            "少用套路形容词",
        ],
        "do_not_write": [
            "不要短视频口号",
            "不要夸张反问",
            "不要把每个片段都写成高潮",
        ],
    },
    "visual_action": {
        "strategy_id": "visual_action",
        "label": "视觉动作线",
        "suited_categories": ["江湖动作", "战争权谋", "喜剧轻松"],
        "draft_instruction": (
            "字幕只做剧情锚点，动作、场面和节奏是主要写作抓手。"
            "适合动作戏、战争戏、无对白强画面段。"
        ),
        "visual_rewrite_instruction": (
            "视觉二改可以更主动使用镜头里的动作顺序，但仍不能改变字幕确认的事实。"
        ),
        "do_write": [
            "动作先行，再补意义",
            "短句配合快速画面",
            "强场面可以让原声多留一点空间",
        ],
        "do_not_write": [
            "不要只写剧情概括",
            "不要在没有画面证据时编动作",
            "不要让动作句超出时间窗",
        ],
    },
}


_CATEGORY_DEFAULT = {
    "历史宫廷": "historical_pressure",
    "战争权谋": "historical_pressure",
    "悬疑罪案": "suspense_short_video",
    "江湖动作": "visual_action",
    "喜剧轻松": "visual_action",
    "家庭伦理": "character_growth",
    "爱情情感": "character_growth",
    "都市职场": "suspense_short_video",
}


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return " ".join(_as_text(v) for v in value.values())
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return " ".join(_as_text(x) for x in value)
    return str(value or "").strip()


def strategy_archive_path() -> Path:
    return Path(project_root()) / "reports" / "narration_prompt_strategies" / "strategy_scores.jsonl"


def get_prompt_strategy(strategy_id: str = "", movie_category: str = "") -> JsonDict:
    sid = str(strategy_id or "").strip()
    if sid in STRATEGY_PROFILES:
        return dict(STRATEGY_PROFILES[sid])
    return dict(STRATEGY_PROFILES.get(_CATEGORY_DEFAULT.get(str(movie_category or ""), "character_growth")))


def _read_score_rows(path: Path | None = None) -> List[JsonDict]:
    try:
        path = path or strategy_archive_path()
    except Exception as exc:
        logger.warning("解析解说提示词策略评分归档路径失败: {}", exc)
        return []
    if not path.exists():
        return []
    rows: List[JsonDict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
    except Exception as exc:
        logger.warning("读取解说提示词策略评分归档失败: {}", exc)
    return rows


def select_prompt_strategy(movie_category: str, *, stage: str = "subtitle_draft", min_samples: int = 2) -> JsonDict:
    rows = [
        row for row in _read_score_rows()
        if row.get("movie_category") == movie_category and row.get("stage") == stage
    ]
    scores: Dict[str, List[float]] = {}
    for row in rows:
        sid = str(row.get("strategy_id") or "")
        try:
            score = float(row.get("score", 0.0) or 0.0)
        except Exception:
            score = 0.0
        if sid in STRATEGY_PROFILES:
            scores.setdefault(sid, []).append(score)
    best_id = ""
    best_avg = -1.0
    for sid, vals in scores.items():
        if len(vals) < min_samples:
            continue
        avg = sum(vals) / max(1, len(vals))
        if avg > best_avg:
            best_id = sid
            best_avg = avg
    return get_prompt_strategy(best_id, movie_category)


def get_candidate_prompt_strategies(movie_category: str, *, stage: str = "subtitle_draft", max_candidates: int = 3) -> List[JsonDict]:
    """Return bounded prompt strategies for one generation attempt.

    Order matters: historical best for the category first, then the category
    default, then other profiles explicitly suited to the category.  This makes
    tests compare strategies without exploding token cost.
    """
    candidates: List[JsonDict] = []

    def add(profile: JsonDict) -> None:
        sid = str(profile.get("strategy_id") or "")
        if sid and sid not in {str(x.get("strategy_id") or "") for x in candidates}:
            candidates.append(dict(profile))

    add(select_prompt_strategy(movie_category, stage=stage))
    add(get_prompt_strategy(movie_category=movie_category))
    for profile in STRATEGY_PROFILES.values():
        if movie_category in list(profile.get("suited_categories") or []):
            add(profile)
        if len(candidates) >= max_candidates:
            break
    if not candidates:
        add(get_prompt_strategy("character_growth"))
    return candidates[:max(1, int(max_candidates or 1))]


def _compact_zh(text: str) -> str:
    import re

    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE)


def score_narration_items(items: Iterable[Mapping[str, Any]], *, source_text: str = "", expected_total: int = 0) -> JsonDict:
    rows = [dict(x) for x in (items or []) if isinstance(x, Mapping)]
    texts = [_as_text(row.get("narration") or row.get("text")) for row in rows]
    nonempty = [x for x in texts if x]
    total = len(rows)
    expected = max(int(expected_total or 0), total)
    empty_count = total - len(nonempty)
    missing_count = max(0, expected - total)
    unique_count = len({_compact_zh(x)[:36] for x in nonempty if _compact_zh(x)})
    duplicate_ratio = 0.0 if not nonempty else max(0.0, 1.0 - unique_count / max(1, len(nonempty)))
    cliche_hits = sum(
        1 for x in nonempty
        if any(token in x for token in ("这一段", "推动矛盾", "信息揭露功能", "真正的看点", "观众会意识到"))
    )
    source_norm = _compact_zh(source_text)
    recite_hits = 0
    if source_norm:
        for x in nonempty:
            nx = _compact_zh(x)
            if nx and SequenceMatcher(None, nx[:500], source_norm[:2500]).ratio() >= 0.72:
                recite_hits += 1
    avg_len = sum(len(x) for x in nonempty) / max(1, len(nonempty))

    score = 1.0
    score -= min(0.35, duplicate_ratio * 0.7)
    score -= min(0.25, cliche_hits * 0.06)
    score -= min(0.20, recite_hits * 0.05)
    score -= min(0.15, empty_count * 0.05)
    score -= min(0.30, missing_count * 0.10)
    if avg_len < 18:
        score -= 0.08
    if avg_len > 150:
        score -= 0.06
    score = round(max(0.0, min(1.0, score)), 3)
    return {
        "score": score,
        "total": total,
        "expected_total": expected,
        "missing_count": missing_count,
        "empty_count": empty_count,
        "duplicate_ratio": round(duplicate_ratio, 3),
        "cliche_hits": cliche_hits,
        "subtitle_recitation_hits": recite_hits,
        "avg_len": round(avg_len, 1),
        "passed": bool(score >= 0.78 and empty_count == 0 and missing_count == 0 and duplicate_ratio <= 0.20 and cliche_hits == 0),
    }


def record_prompt_strategy_result(
    *,
    movie_category: str,
    strategy_id: str,
    stage: str,
    score_report: Mapping[str, Any],
    sample: Mapping[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    row = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "movie_category": str(movie_category or "通用剧情"),
        "strategy_id": str(strategy_id or ""),
        "stage": str(stage or ""),
        "score": float(score_report.get("score", 0.0) or 0.0),
        "score_report": dict(score_report),
        "sample": dict(sample or {}),
    }
    try:
        out = path or strategy_archive_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("写入解说提示词策略评分归档失败: {}", exc)
