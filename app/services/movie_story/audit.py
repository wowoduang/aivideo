# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .schemas import item_duration, item_time_range, to_dict

logger = logging.getLogger(__name__)


class StageAuditWriter:
    """前三阶段统一审计：JSON、CSV、summary 和可选视频片段。"""

    def __init__(self, root_dir: str | Path, *, source_video_path: str | Path | None = None,
                 export_clips: bool = True, max_clips_per_stage: int = 80,
                 keep_runs: int = 2, run_id: str | None = None) -> None:
        self.root_dir = Path(root_dir)
        self.source_video_path = str(source_video_path or "")
        self.export_clips = export_clips
        self.max_clips_per_stage = max(1, int(max_clips_per_stage))
        self.keep_runs = max(1, int(keep_runs))
        self.run_id = run_id or os.environ.get("AIVIDEO_AUDIT_RUN_ID") or time.strftime("run_%Y%m%d_%H%M%S")
        os.environ["AIVIDEO_AUDIT_RUN_ID"] = self.run_id
        self.run_dir = self.root_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_runs()

    def _cleanup_old_runs(self) -> None:
        runs = [p for p in self.root_dir.glob("run_*") if p.is_dir()]
        runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in runs[self.keep_runs:]:
            shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def _safe(name: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))[:120]

    @staticmethod
    def _brief(item: Any, idx: int) -> Dict[str, Any]:
        d = to_dict(item)
        if not isinstance(d, dict):
            return {"idx": idx, "value": str(d)[:500]}
        return {
            "idx": idx,
            "id": d.get("candidate_id") or d.get("highlight_id") or d.get("segment_id") or d.get("id"),
            "candidate_type": d.get("candidate_type"),
            "video_start": d.get("video_start", d.get("start")),
            "video_end": d.get("video_end", d.get("end")),
            "evidence_start": d.get("evidence_start"),
            "evidence_end": d.get("evidence_end"),
            "semantic_start": d.get("semantic_start"),
            "semantic_end": d.get("semantic_end"),
            "duration": item_duration(d),
            "plot_function": d.get("plot_function"),
            "importance_level": d.get("importance_level"),
            "selected": d.get("selected"),
            "selection_mode": d.get("selection_mode"),
            "score": (d.get("scores") or {}).get("highlight_score") if isinstance(d.get("scores"), dict) else "",
            "drop_suggestion": d.get("drop_suggestion"),
            "drop_reason": d.get("drop_reason"),
            "rejected_reason": d.get("rejected_reason"),
            "reasons": json.dumps(d.get("selection_reasons") or d.get("merge_reason") or [], ensure_ascii=False),
            "text": str(d.get("subtitle_text") or "")[:320],
        }

    def _export_clip(self, output_path: Path, start: float, end: float) -> bool:
        if not self.source_video_path or not Path(self.source_video_path).exists():
            return False
        duration = max(end - start, 0.1)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-i", self.source_video_path, "-t", f"{duration:.3f}",
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "25", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output_path),
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
                               timeout=max(30, int(duration) + 30))
            if r.returncode != 0:
                logger.warning("导出审计片段失败: %s | %s", output_path, (r.stderr or "")[:300])
                return False
            return True
        except Exception as exc:
            logger.warning("导出审计片段异常: %s | %s", output_path, exc)
            return False

    def save_stage(self, stage_name: str, items: Iterable[Any], *, metadata: Optional[Dict[str, Any]] = None) -> Path:
        items = list(items or [])
        stage_dir = self.run_dir / self._safe(stage_name)
        clips_dir = stage_dir / "clips"
        stage_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        rows: List[Dict[str, Any]] = []
        full_items: List[Any] = []
        exported = 0
        for idx, item in enumerate(items, start=1):
            data = to_dict(item)
            full_items.append(data)
            row = self._brief(item, idx)
            s, e = item_time_range(item)
            if self.export_clips and idx <= self.max_clips_per_stage and s is not None and e is not None:
                raw_id = str(row.get("id") or "segment")[:40].replace("/", "_").replace(chr(92), "_")
                name = f"{idx:03d}_{raw_id}_{s:.3f}_{e:.3f}.mp4"
                clip_path = clips_dir / name
                ok = self._export_clip(clip_path, s, e)
                row["clip_path"] = str(clip_path)
                row["exported"] = ok
                exported += int(ok)
            else:
                row["clip_path"] = ""
                row["exported"] = False
            rows.append(row)
        total = round(sum(item_duration(x) for x in items), 3)
        summary = {
            "stage": stage_name,
            "count": len(items),
            "exported": exported,
            "total_duration": total,
            "metadata": metadata or {},
        }
        manifest = {**summary, "items": rows}
        (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (stage_dir / "items_full.json").write_text(json.dumps(full_items, ensure_ascii=False, indent=2), encoding="utf-8")
        (stage_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        if rows:
            with (stage_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        else:
            (stage_dir / "manifest.csv").write_text("idx,id\n", encoding="utf-8-sig")
        self._append_index(stage_name, stage_dir, summary)
        return stage_dir

    def _append_index(self, stage_name: str, stage_dir: Path, summary: Dict[str, Any]) -> None:
        idx_path = self.run_dir / "_stage_index.json"
        try:
            index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
        except Exception:
            index = []
        index.append({
            "stage": stage_name,
            "dir": str(stage_dir),
            "manifest": str(stage_dir / "manifest.json"),
            "items_full": str(stage_dir / "items_full.json"),
            "summary": str(stage_dir / "summary.json"),
            "csv": str(stage_dir / "manifest.csv"),
            "count": summary.get("count", 0),
            "exported": summary.get("exported", 0),
            "total_duration": summary.get("total_duration", 0),
        })
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
