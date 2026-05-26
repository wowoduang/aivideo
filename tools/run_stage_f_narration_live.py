#!/usr/bin/env python3
from __future__ import annotations

"""Run bounded live Stage-F final narration_generation samples.

This tool consumes an existing audit run after Stage E has passed.  It does not
create a full final script.  It samples a tiny number of highlights that already
have Stage-E writeback, calls the old narration_generation-style prompt, writes
07a_narration_generation_sample_contract, and leaves full narration/TTS for later
stages.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.movie_story import narration_sample  # noqa: E402


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _stage_dir(audit_dir: Path, stage: str) -> Path:
    direct = audit_dir / stage
    if direct.exists():
        return direct
    candidates = sorted(audit_dir.glob(f"run_*/{stage}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else direct


def _read_items(stage: Path) -> List[Dict[str, Any]]:
    full = stage / "items_full.json"
    manifest = stage / "manifest.json"
    src = full if full.exists() else manifest
    if not src.exists():
        raise FileNotFoundError(f"缺少阶段产物: {stage}/items_full.json 或 manifest.json")
    payload = _load_json(src)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("records") or []
        return [x for x in items if isinstance(x, dict)]
    return []


def _compact_row(item: Mapping[str, Any]) -> Dict[str, Any]:
    row = dict(item)
    for key in ["legacy_prompt_payload", "segment_json", "project_context", "llm_raw_response", "narration_result"]:
        if key in row and not isinstance(row.get(key), (str, int, float, bool, type(None))):
            row[key] = json.dumps(row[key], ensure_ascii=False, default=str)[:2000]
    return row


def _write_stage(stage: Path, items: List[Dict[str, Any]], *, meta: Dict[str, Any]) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "clips").mkdir(exist_ok=True)
    _write_json(stage / "items_full.json", items)
    rows = [_compact_row(x) for x in items]
    manifest = dict(meta)
    manifest["items"] = rows
    manifest["count"] = len(rows)
    _write_json(stage / "manifest.json", manifest)
    if rows:
        fieldnames: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in fieldnames:
                    fieldnames.append(k)
        with (stage / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)


def _summary(items: List[Dict[str, Any]], report: Dict[str, Any]) -> Dict[str, Any]:
    failed = []
    for item in items:
        q = item.get("narration_quality") if isinstance(item.get("narration_quality"), dict) else {}
        if not q.get("passed"):
            failed.append({
                "sample_id": item.get("sample_id"),
                "highlight_id": item.get("highlight_id"),
                "source": item.get("narration_result_source"),
                "reason": q.get("reason"),
                "missing_result_fields": q.get("missing_result_fields"),
                "missing_input_flags": q.get("missing_input_flags"),
                "llm_error": item.get("llm_error"),
                "raw_preview": str(item.get("llm_raw_response") or "")[:400],
            })
    return {
        "overall_passed": bool(report.get("overall_passed")),
        "stage_f_items": len(items),
        "stage_f_passed": report.get("passed"),
        "stage_f_missing_result_count": report.get("missing_result_count"),
        "stage_f_live_or_cache_result_count": report.get("live_or_cache_result_count"),
        "stage_f_llm_enabled_count": report.get("llm_enabled_count"),
        "failed_items": failed[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded Stage-F narration_generation samples from an existing audit run.")
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--max-live-calls", type=int, default=2)
    parser.add_argument("--min-results", type=int, default=2)
    parser.add_argument("--max-input-chars", type=int, default=12000)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir).resolve()
    if args.cache_dir:
        os.environ["MOVIE_STORY_STAGE_F_CACHE_DIR"] = args.cache_dir
    elif not os.environ.get("MOVIE_STORY_STAGE_F_CACHE_DIR"):
        os.environ["MOVIE_STORY_STAGE_F_CACHE_DIR"] = str(audit_dir / "_stage_f_llm_cache")

    stage_c = _stage_dir(audit_dir, "06b_narration_generation_input_contract")
    stage_e = _stage_dir(audit_dir, "06d_understanding_result_writeback_contract")
    stage_f = _stage_dir(audit_dir, narration_sample.STAGE_F_STAGE_NAME)

    c_items = _read_items(stage_c)
    e_items = _read_items(stage_e)
    f_items = narration_sample.build_stage_f_sample_items(
        c_items,
        e_items,
        min_samples=args.min_results,
        max_live_calls=args.max_live_calls,
        max_input_chars=args.max_input_chars,
    )
    f_items = narration_sample.maybe_run_live_narration_samples(
        f_items,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_live_calls=args.max_live_calls,
        timeout=args.timeout,
    )
    report = narration_sample.evaluate_stage_f_items(
        f_items,
        min_results=args.min_results,
        max_llm_calls=args.max_live_calls,
        max_input_chars=args.max_input_chars,
    )
    _write_stage(stage_f, f_items, meta={
        "source": "stage_f_post_run_bounded_narration_generation_samples",
        "migration_stage": "stage_f",
        "overall_passed": report.get("overall_passed"),
        "pass_rate": report.get("pass_rate"),
        "passed": report.get("passed"),
        "min_results": args.min_results,
        "max_live_calls": args.max_live_calls,
        "live_or_cache_result_count": report.get("live_or_cache_result_count"),
        "missing_result_count": report.get("missing_result_count"),
    })
    out = _summary(f_items, report)
    out["audit_dir"] = str(audit_dir)
    out["next_command"] = f"python tools/verify_movie_story_migration_stage.py --stage stage_f --audit-dir {audit_dir} --stage-f-max-llm-calls {args.max_live_calls} --stage-f-min-results {args.min_results}"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
