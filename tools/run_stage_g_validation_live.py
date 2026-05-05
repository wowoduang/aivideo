#!/usr/bin/env python3
from __future__ import annotations

"""Run bounded live Stage-G narration_validation samples from an existing audit run."""

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

from app.services.movie_story import narration_validation_sample  # noqa: E402


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
    for key in ["validation_prompt_payload", "segment_json", "narration_result", "validation_result", "llm_raw_response"]:
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
        q = item.get("validation_quality") if isinstance(item.get("validation_quality"), dict) else {}
        if not q.get("passed"):
            failed.append({
                "validation_id": item.get("validation_id"),
                "highlight_id": item.get("highlight_id"),
                "source": item.get("validation_result_source"),
                "reason": q.get("reason"),
                "status": q.get("status"),
                "missing_result_fields": q.get("missing_result_fields"),
                "missing_input_flags": q.get("missing_input_flags"),
                "llm_error": item.get("llm_error"),
                "raw_preview": str(item.get("llm_raw_response") or "")[:400],
            })
    return {
        "overall_passed": bool(report.get("overall_passed")),
        "stage_g_items": len(items),
        "stage_g_passed": report.get("passed"),
        "stage_g_missing_result_count": report.get("missing_result_count"),
        "stage_g_live_or_cache_result_count": report.get("live_or_cache_result_count"),
        "stage_g_llm_enabled_count": report.get("llm_enabled_count"),
        "status_counts": report.get("status_counts"),
        "review_or_reject_count": report.get("review_or_reject_count"),
        "rewrite_ready_count": report.get("rewrite_ready_count"),
        "failed_items": failed[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded Stage-G narration_validation samples from an existing audit run.")
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
        os.environ["MOVIE_STORY_STAGE_G_CACHE_DIR"] = args.cache_dir
    elif not os.environ.get("MOVIE_STORY_STAGE_G_CACHE_DIR"):
        os.environ["MOVIE_STORY_STAGE_G_CACHE_DIR"] = str(audit_dir / "_stage_g_llm_cache")

    stage_f = _stage_dir(audit_dir, "07a_narration_generation_sample_contract")
    stage_g = _stage_dir(audit_dir, narration_validation_sample.STAGE_G_STAGE_NAME)

    f_items = _read_items(stage_f)
    g_items = narration_validation_sample.build_stage_g_validation_items(
        f_items,
        min_samples=args.min_results,
        max_live_calls=args.max_live_calls,
        max_input_chars=args.max_input_chars,
    )
    g_items = narration_validation_sample.maybe_run_live_validation_samples(
        g_items,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_live_calls=args.max_live_calls,
        timeout=args.timeout,
    )
    report = narration_validation_sample.evaluate_stage_g_items(
        g_items,
        min_results=args.min_results,
        max_llm_calls=args.max_live_calls,
        max_input_chars=args.max_input_chars,
    )
    _write_stage(stage_g, g_items, meta={
        "source": "stage_g_post_run_bounded_narration_validation_samples",
        "migration_stage": "stage_g",
        "overall_passed": report.get("overall_passed"),
        "pass_rate": report.get("pass_rate"),
        "passed": report.get("passed"),
        "min_results": args.min_results,
        "max_live_calls": args.max_live_calls,
        "live_or_cache_result_count": report.get("live_or_cache_result_count"),
        "missing_result_count": report.get("missing_result_count"),
    })
    out = _summary(g_items, report)
    out["audit_dir"] = str(audit_dir)
    out["next_command"] = f"python tools/verify_movie_story_migration_stage.py --stage stage_g --audit-dir {audit_dir} --stage-g-max-llm-calls {args.max_live_calls} --stage-g-min-results {args.min_results}"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
