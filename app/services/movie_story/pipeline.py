# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import StageAuditWriter
from .schemas import to_dict
from .stage1_segmentation import build_segmentation_candidates
from .stage2_evidence import enrich_candidates_with_evidence
from .stage3_highlight_selection import select_highlights


def run_first_three_stages(*, video_path: str, subtitle_segments: List[Dict[str, Any]], output_dir: str,
                           segmentation_mode: str = "hybrid", target_minutes: int = 8,
                           highlight_selectivity: str = "balanced", prologue_end: float | None = None,
                           story_end: float | None = None, video_boundary_candidates: Optional[List[Any]] = None,
                           audio_boundaries: Optional[List[Any]] = None, visual_cards: Optional[Dict[str, Dict[str, Any]]] = None,
                           export_audit_clips: bool = True, max_audit_clips_per_stage: int = 80,
                           keep_audit_runs: int = 2) -> Dict[str, Any]:
    audit = StageAuditWriter(Path(output_dir) / "_movie_story_v1_audit", source_video_path=video_path,
                             export_clips=export_audit_clips, max_clips_per_stage=max_audit_clips_per_stage,
                             keep_runs=keep_audit_runs)
    scenes, stories, coverage = build_segmentation_candidates(
        video_path, subtitle_segments, segmentation_mode=segmentation_mode, prologue_end=prologue_end,
        story_end=story_end, video_boundary_candidates=video_boundary_candidates, audio_boundaries=audio_boundaries)
    audit.save_stage("01_scene_candidates", scenes, metadata=coverage)
    audit.save_stage("02_draft_story_candidates", stories, metadata=coverage)
    evidence_input = stories if stories else scenes
    evidence = enrich_candidates_with_evidence(evidence_input, subtitle_segments, visual_cards=visual_cards)
    audit.save_stage("03_evidence_segments", evidence)
    highlights = select_highlights(evidence, target_minutes=target_minutes, highlight_selectivity=highlight_selectivity)
    audit.save_stage("04_selected_highlights", highlights, metadata={"highlight_selectivity": highlight_selectivity, "target_minutes": target_minutes})
    result = {"scene_candidates": to_dict(scenes), "draft_story_candidates": to_dict(stories),
              "evidence_segments": to_dict(evidence), "selected_highlights": to_dict(highlights),
              "coverage": coverage, "audit_dir": str(audit.run_dir)}
    out_path = Path(output_dir) / "movie_story_first_three_stages_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
