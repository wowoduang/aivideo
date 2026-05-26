# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import StageAuditWriter
from .schemas import to_dict
from .stage1_segmentation import build_segmentation_candidates
from .stage2_evidence import enrich_candidates_with_evidence
from .stage3_highlight_selection import select_highlights_with_report
from .human_narration.pipeline import build_human_narration_package
from .production.subtitle_designer import design_subtitle_cues
from .production.video_quality_gate import check_video_plan_quality


def _split_merge_rows(evidence: List[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in evidence:
        d = to_dict(item)
        if not isinstance(d, dict):
            continue
        rows.append({
            "candidate_id": d.get("candidate_id"),
            "candidate_type": d.get("candidate_type"),
            "video_start": d.get("video_start"),
            "video_end": d.get("video_end"),
            "duration": d.get("duration"),
            "split_merge_suggestion": d.get("split_merge_suggestion") or {},
            "drop_suggestion": d.get("drop_suggestion"),
            "drop_reason": d.get("drop_reason"),
            "subtitle_text": d.get("subtitle_text"),
        })
    return rows


def run_first_three_stages(*, video_path: str, subtitle_segments: List[Dict[str, Any]], output_dir: str,
                           segmentation_mode: str = "hybrid", target_minutes: int = 8,
                           highlight_selectivity: str = "balanced", narrative_strategy: str = "mixed",
                           prologue_end: float | None = None, story_end: float | None = None,
                           video_boundary_candidates: Optional[List[Any]] = None,
                           audio_boundaries: Optional[List[Any]] = None, visual_cards: Optional[Dict[str, Dict[str, Any]]] = None,
                           export_audit_clips: bool = True, max_audit_clips_per_stage: int = 80,
                           keep_audit_runs: int = 2, enable_human_narration: bool = True,
                           narration_style: str = "suspense") -> Dict[str, Any]:
    """运行影视解说前三阶段。

    第一阶段只切全，第二阶段只补证据，第三阶段才筛高光。
    该入口用于重构验证和生产链路逐步替换，输出所有中间产物与审计目录。
    """
    audit = StageAuditWriter(
        Path(output_dir) / "_movie_story_v1_audit",
        source_video_path=video_path,
        export_clips=export_audit_clips,
        max_clips_per_stage=max_audit_clips_per_stage,
        keep_runs=keep_audit_runs,
    )
    scenes, stories, coverage = build_segmentation_candidates(
        video_path,
        subtitle_segments,
        segmentation_mode=segmentation_mode,
        prologue_end=prologue_end,
        story_end=story_end,
        video_boundary_candidates=video_boundary_candidates,
        audio_boundaries=audio_boundaries,
    )
    audit.save_stage("01_scene_candidates", scenes, metadata=coverage)
    audit.save_stage("02_draft_story_candidates", stories, metadata=coverage)

    # 第二阶段以 draft_story 为主；如果未生成故事块，则回退到 scene 候选。
    evidence_input = stories if stories else scenes
    evidence = enrich_candidates_with_evidence(evidence_input, subtitle_segments, visual_cards=visual_cards)
    audit.save_stage("03_evidence_segments", evidence, metadata={"policy": "stage2_enrich_no_delete", "input_count": len(evidence_input)})
    split_merge = _split_merge_rows(evidence)
    audit.save_stage("04_split_merge_suggestions", split_merge, metadata={"policy": "suggest_only_no_delete"})

    selection_report = select_highlights_with_report(
        evidence,
        target_minutes=target_minutes,
        highlight_selectivity=highlight_selectivity,
        narrative_strategy=narrative_strategy,
    )
    selected = selection_report["selected_highlights"]
    rejected = selection_report["rejected_candidates"]
    audit.save_stage("05_selected_highlights", selected, metadata=selection_report["summary"])
    audit.save_stage("06_rejected_candidates", rejected, metadata={"policy": "stage3_rejects_are_audited"})

    human_narration: Dict[str, Any] = {}
    subtitle_cues: List[Dict[str, Any]] = []
    production_quality_gate: Dict[str, Any] = {}
    if enable_human_narration:
        human_narration = build_human_narration_package(
            selected,
            global_summary=" ".join(str(x.get("subtitle_text") or "") for x in to_dict(selected) if isinstance(x, dict))[:1200],
            style_key=narration_style,
        )
        audit.save_stage("07_human_narration_director", human_narration.get("directed_segments") or [], metadata={"style": narration_style})
        audit.save_stage("08_humanized_script_items", human_narration.get("script_items") or [], metadata=human_narration.get("quality_report") or {})
        subtitle_cues = design_subtitle_cues(human_narration.get("script_items") or [])
        audit.save_stage("09_subtitle_design_cues", subtitle_cues, metadata={"policy": "production_layer_advice_only"})
        production_quality_gate = check_video_plan_quality(human_narration.get("script_items") or [], source_highlights=to_dict(selected))

    result = {
        "scene_candidates": to_dict(scenes),
        "draft_story_candidates": to_dict(stories),
        "evidence_segments": to_dict(evidence),
        "split_merge_suggestions": split_merge,
        "selected_highlights": to_dict(selected),
        "rejected_candidates": to_dict(rejected),
        "selection_summary": selection_report["summary"],
        "human_narration": human_narration,
        "subtitle_design_cues": subtitle_cues,
        "production_quality_gate": production_quality_gate,
        "coverage": coverage,
        "audit_dir": str(audit.run_dir),
        "principles": {
            "stage1": "cut_all_no_highlight_filter",
            "stage2": "enrich_and_suggest_no_delete",
            "stage3": "only_stage_allowed_to_select_highlights",
            "timing": "video_start_video_end_are_authoritative; tts_duration_cannot_retime_video",
        },
    }
    out_path = Path(output_dir) / "movie_story_first_three_stages_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
