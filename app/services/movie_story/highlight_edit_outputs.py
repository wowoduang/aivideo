from __future__ import annotations

"""Output helpers for highlight-edit runs.

Stage-L extraction target.  This module owns file output and response-shape
assembly so the public pipeline can stay a thin orchestrator.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from app.utils import utils


def write_outputs(video_hash: str, composition_plan: Dict[str, Any], script_items: List[Dict[str, Any]]) -> Dict[str, str]:
    """Persist CompositionPlan and script item artifacts under the script directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    composition_plan_path = os.path.join(utils.script_dir(), f"{video_hash}_highlight_edit_{timestamp}.json")
    script_path = os.path.join(utils.script_dir(), f"{video_hash}_highlight_edit_script_{timestamp}.json")
    os.makedirs(os.path.dirname(composition_plan_path), exist_ok=True)
    with open(composition_plan_path, "w", encoding="utf-8") as handle:
        json.dump(composition_plan, handle, ensure_ascii=False, indent=2)
    with open(script_path, "w", encoding="utf-8") as handle:
        json.dump(script_items, handle, ensure_ascii=False, indent=2)
    return {
        "composition_plan_path": composition_plan_path,
        "script_path": script_path,
    }


def build_error_response(error: str) -> Dict[str, Any]:
    """Return the stable public error shape expected by callers."""
    return {
        "success": False,
        "error": str(error or ""),
        "composition_plan": {},
        "composition_plan_path": "",
        "script_items": [],
        "script_path": "",
        "candidate_clips": [],
        "selected_clips": [],
    }


def build_success_response(
    *,
    mode: str,
    subtitle_result: Dict[str, Any],
    subtitle_segments: List[Dict[str, Any]],
    scene_segments: List[Dict[str, Any]],
    video_boundary_candidates: List[Dict[str, Any]],
    plot_chunks: List[Dict[str, Any]],
    plot_candidate_clips: List[Dict[str, Any]],
    candidate_clips: List[Dict[str, Any]],
    scene_candidate_clips: List[Dict[str, Any]],
    candidate_stats: Dict[str, Any],
    highlight_profile: Dict[str, Any],
    highlight_capabilities: Dict[str, Any],
    selected_clips: List[Dict[str, Any]],
    narration_units: List[Dict[str, Any]],
    narration_matches: List[Dict[str, Any]],
    composition_plan: Dict[str, Any],
    output_paths: Dict[str, str],
    script_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the stable success response for highlight-edit jobs."""
    return {
        "success": True,
        "error": "",
        "mode": mode,
        "subtitle_result": subtitle_result,
        "subtitle_segments": subtitle_segments,
        "scene_segments": scene_segments,
        "video_boundary_candidates": video_boundary_candidates,
        "plot_chunks": plot_chunks,
        "plot_candidate_clips": plot_candidate_clips,
        "candidate_clips": candidate_clips,
        "scene_candidate_clips": scene_candidate_clips,
        "candidate_stats": candidate_stats,
        "highlight_profile": highlight_profile,
        "highlight_capabilities": highlight_capabilities,
        "selected_clips": selected_clips,
        "narration_units": narration_units,
        "narration_matches": narration_matches,
        "composition_plan": composition_plan,
        "composition_plan_path": output_paths.get("composition_plan_path", ""),
        "script_items": script_items,
        "script_path": output_paths.get("script_path", ""),
    }
