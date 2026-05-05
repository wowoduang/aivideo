# -*- coding: utf-8 -*-
"""Post-selection commentary pipeline: 05 -> 06 -> 07 adapter -> 08 adapter."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
import json, time
from app.services.movie_story.narration_writer import write_narration_script, save_narration_script
from app.services.movie_story.tts_adapter import synthesize_narration
from app.services.movie_story.video_compose_adapter import compose_commentary_video
Record = Dict[str, Any]

def _read_json(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8", errors="replace"))

def _extract_records(obj: Any) -> Optional[List[Record]]:
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj): return list(obj)
    if isinstance(obj, dict):
        for key in ("items", "records", "data", "clips", "highlights", "selected_highlights", "lines"):
            value = obj.get(key)
            if isinstance(value, list) and all(isinstance(x, dict) for x in value): return list(value)
    return None

def load_selected_highlights(path_or_dir: str | Path) -> List[Record]:
    p = Path(path_or_dir); candidates: List[Path] = []
    if p.is_file(): candidates = [p]
    elif p.is_dir():
        seen = set()
        for pat in ["05_selected_highlights*.json", "**/05_selected_highlights*.json", "**/*selected_highlights*.json", "**/items.json", "**/records.json", "**/data.json"]:
            for file in p.glob(pat):
                if file.name.startswith("_stage_index"): continue
                if file.suffix.lower() == ".json" and file not in seen:
                    seen.add(file); candidates.append(file)
    for file in candidates:
        try:
            records = _extract_records(_read_json(file))
            if records: return records
        except Exception: continue
    raise FileNotFoundError(f"无法从 {p} 找到 05_selected_highlights JSON 记录")

def run_commentary_pipeline(input_video: str | Path, selected_highlights: Sequence[Mapping[str, Any]], output_dir: str | Path, *, global_summary: str = "", narration_options: Optional[Mapping[str, Any]] = None, tts_options: Optional[Mapping[str, Any]] = None, composer_options: Optional[Mapping[str, Any]] = None) -> Record:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True); selected = [dict(x) for x in selected_highlights]
    (out / "05_selected_highlights_input.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    script = write_narration_script(selected, global_summary=global_summary, options=narration_options); script_paths = save_narration_script(script, out)
    tts_manifest = synthesize_narration(script, out, options=tts_options)
    video_manifest = compose_commentary_video(input_video, selected, script, tts_manifest, out, options=composer_options)
    report = {"stage":"09_commentary_pipeline_report", "created_at":time.strftime("%Y-%m-%d %H:%M:%S"), "input_video":str(input_video), "output_dir":str(out), "selected_highlight_count":len(selected), "narration":{"paths":script_paths, "metadata":script.get("metadata")}, "tts":{"manifest_path":tts_manifest.get("manifest_path"), "status":tts_manifest.get("status"), "full_audio":tts_manifest.get("full_audio")}, "video":{"manifest_path":video_manifest.get("manifest_path"), "status":video_manifest.get("status"), "final_video":video_manifest.get("final_video")}, "status":"ok" if video_manifest.get("final_video") else "partial"}
    report_path = out / "09_commentary_pipeline_report.json"; report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"); report["report_path"] = str(report_path); return report

def run_commentary_from_audit(audit_dir: str | Path, input_video: str | Path, output_dir: Optional[str | Path] = None, **kwargs: Any) -> Record:
    audit = Path(audit_dir); selected = load_selected_highlights(audit); out = Path(output_dir) if output_dir else audit / "commentary_pipeline"; return run_commentary_pipeline(input_video, selected, out, **kwargs)

__all__ = ["load_selected_highlights", "run_commentary_pipeline", "run_commentary_from_audit"]
