# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..schemas import to_dict
from .director import direct_segments
from .humanize_rewriter import humanize_script_items
from .opening_hook import generate_opening_hooks
from .quality_scorer import score_human_narration
from .style_profile import get_style_profile
from .transition_writer import generate_transitions


def _fallback_script_items(highlights: Iterable[Any], directed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = [to_dict(x) for x in highlights if isinstance(to_dict(x), dict)]
    directed_by_id = {str(x.get("segment_id")): x for x in directed}
    out: List[Dict[str, Any]] = []
    for idx, d in enumerate(items, start=1):
        seg_id = str(d.get("highlight_id") or d.get("candidate_id") or f"h_{idx:03d}")
        source = d.get("source_segment") or d
        plot = str(source.get("plot_function") or "这一段")
        text = str(source.get("subtitle_text") or "").strip()
        if plot in {"信息揭露", "反转"}:
            draft = "真正关键的线索终于出现了。这里别急着跳过，因为它会直接改变后面的走向。"
        elif plot in {"冲突升级", "情感爆发"}:
            draft = "局面到这里彻底压不住了。前面的矛盾，在这一刻直接爆发。"
        elif plot in {"关键决定", "人物转折", "关系变化"}:
            draft = "他终于做出了选择。这个决定，也让两个人的关系开始变味。"
        elif text:
            draft = f"这一段表面是在交代{plot}，但真正重要的是人物的态度开始变了。"
        else:
            draft = "这里不用说太满，留一点原声和画面，让观众自己感受到不对劲。"
        out.append({
            "segment_id": seg_id,
            "source_candidate_id": d.get("source_candidate_id") or d.get("candidate_id"),
            "text": draft,
            "subtitle_text": text,
            "video_start": d.get("video_start"),
            "video_end": d.get("video_end"),
            "human_narration_plan": directed_by_id.get(seg_id) or {},
        })
    return out


def build_human_narration_package(highlights: Iterable[Any], *, existing_script_items: Iterable[Dict[str, Any]] | None = None,
                                  global_summary: str = "", style_key: str | None = None) -> Dict[str, Any]:
    """构建真人解说层包：风格、人设导演、开场钩子、转场、口播化和评分。

    这是完整的可测试闭环：即使上游暂时没有 LLM 生成的脚本，也会产出一个可审查的 fallback 分段稿，供前端编辑或下游接入。
    """
    style = get_style_profile(style_key)
    highlights_list = [to_dict(x) for x in highlights if isinstance(to_dict(x), dict)]
    directed = direct_segments(highlights_list, style_key=style["style_key"])
    plan_by_id = {str(x.get("segment_id")): x for x in directed}
    hooks = generate_opening_hooks(highlights_list, global_summary=global_summary, style_key=style["style_key"])
    transitions = generate_transitions(highlights_list)
    source_script = list(existing_script_items or []) or _fallback_script_items(highlights_list, directed)
    humanized = humanize_script_items(source_script, style_key=style["style_key"], plan_by_segment=plan_by_id)
    quality = score_human_narration(humanized, transitions=transitions)
    return {
        "style_profile": style,
        "opening_hooks": hooks,
        "directed_segments": directed,
        "transitions": transitions,
        "script_items": humanized,
        "quality_report": quality,
        "principles": {
            "human_narration": "decide_intent_before_writing_script",
            "retiming": "human_narration_must_not_modify_video_start_video_end",
        },
    }
