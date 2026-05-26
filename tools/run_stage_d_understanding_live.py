#!/usr/bin/env python3
from __future__ import annotations

"""Run bounded live Stage-D understanding samples for an existing audit run.

This tool fixes the Stage-E failure mode where 06c/06d contracts exist but
all writeback rows are missing ``llm_result``.  It does **not** generate final
narration.  It only runs the old-project global/local understanding refinement
samples created in Stage D, caches their JSON results, then rebuilds Stage E
writeback contracts for verification.

Example:
  python tools/run_stage_d_understanding_live.py \
    --audit-dir E:\\aivideo-v5-workspace\\frontend_uploads\\video\\_movie_story_pipeline_audit_clips\\run_xxx \
    --max-live-calls 3 --min-global 1 --min-local 2
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

from app.services.movie_story import understanding_quality, understanding_writeback  # noqa: E402


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
    if candidates:
        return candidates[0]
    return direct


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
    # Keep CSV/manifest reasonably small while items_full stores everything.
    for key in ["prompt_payload", "llm_raw_response", "writeback_payload", "llm_result"]:
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
            writer.writeheader()
            writer.writerows(rows)


def _select_for_live(items: List[Dict[str, Any]], *, max_live_calls: int, min_global: int, min_local: int) -> List[Dict[str, Any]]:
    selected_global = 0
    selected_local = 0
    budget = max(0, max_live_calls)
    out: List[Dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        req = str(item.get("request_type") or item.get("prompt_name") or "")
        should = False
        if budget > 0 and req == "global_story_context_refine" and selected_global < min_global:
            should = True
            selected_global += 1
        elif budget > 0 and req == "local_understanding_refine" and selected_local < min_local:
            should = True
            selected_local += 1
        if should:
            item["llm_call_enabled"] = True
            budget -= 1
        else:
            item["llm_call_enabled"] = False
        out.append(item)
    return out




def _refresh_stage_d_quality(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recompute Stage-D quality after mutating llm_call_enabled/live fields.

    Existing 06c items were generated with llm_call_enabled=false, so their
    embedded understanding_contract_quality also says false.  The live-fill
    tool changes selected rows to true; if we do not refresh the quality block,
    evaluation still reports stage_d_llm_enabled_count=0 and hides the real
    live-call state.
    """
    refreshed: List[Dict[str, Any]] = []
    for raw in items or []:
        item = dict(raw)
        try:
            max_chars = int(item.get("max_input_chars") or 9000)
        except Exception:
            max_chars = 9000
        item["understanding_contract_quality"] = understanding_quality.score_stage_d_item(item, max_input_chars=max_chars)
        refreshed.append(item)
    return refreshed


def _result_source_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items or []:
        key = str(item.get("llm_result_source") or "none")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _stage_e_ready(item: Mapping[str, Any]) -> Dict[str, Any]:
    result = item.get("llm_result") if isinstance(item.get("llm_result"), dict) else {}
    request_type = str(item.get("request_type") or "")
    prompt_name = str(item.get("prompt_name") or "")
    if request_type == "global_story_context_refine" or prompt_name == "global_story_context_refine":
        required = ["main_conflict", "story_theme", "genre", "timeline_summary"]
    else:
        required = ["surface_dialogue_meaning", "real_narrative_state", "conflict_summary", "character_motivation", "story_function"]
    missing = [k for k in required if not result.get(k)]
    return {"ready": bool(result and not missing), "missing": missing, "required": required}


def _live_diagnostics(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    selected = [x for x in (items or []) if x.get("llm_call_enabled") is True]
    ready_items = []
    failed: List[Dict[str, Any]] = []
    for item in selected:
        ready = _stage_e_ready(item)
        if ready.get("ready"):
            ready_items.append(item)
            continue
        q = item.get("llm_result_quality") if isinstance(item.get("llm_result_quality"), dict) else {}
        cache_q = item.get("llm_cache_quality") if isinstance(item.get("llm_cache_quality"), dict) else {}
        failed.append({
            "sample_id": item.get("sample_id"),
            "request_type": item.get("request_type"),
            "source_highlight_id": item.get("source_highlight_id"),
            "result_source": item.get("llm_result_source") or "none",
            "reason": q.get("reason") or q.get("status") or cache_q.get("status") or "no_stage_e_ready_llm_result",
            "stage_e_missing_min_fields": ready.get("missing"),
            "cache_quality": cache_q,
            "config_ready": q.get("config_ready"),
            "model": q.get("model"),
            "has_base_url": q.get("has_base_url"),
            "error": q.get("error"),
            "raw_preview": q.get("raw_preview"),
        })
    return {
        "live_selected_count": len(selected),
        # Count selected rows that are actually ready for Stage-E writeback,
        # whether they came from valid cache or a fresh live call.
        "live_result_count": len(ready_items),
        "live_failed_count": len(failed),
        "llm_result_source_counts": _result_source_counts(items),
        "live_failed_items": failed[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Stage-D understanding samples and rebuild Stage-E writeback contracts.")
    parser.add_argument("--audit-dir", required=True, help="movie_story audit run directory")
    parser.add_argument("--max-live-calls", type=int, default=3, help="maximum live LLM calls; suggested 3")
    parser.add_argument("--min-global", type=int, default=1, help="number of global refine results required")
    parser.add_argument("--min-local", type=int, default=2, help="number of local refine results required")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--cache-dir", default="", help="optional cache dir; default is <audit-dir>/_stage_d_llm_cache")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir).resolve()
    stage_d = _stage_dir(audit_dir, understanding_quality.STAGE_D_STAGE_NAME)
    stage_e = _stage_dir(audit_dir, understanding_writeback.STAGE_E_STAGE_NAME)
    items = _read_items(stage_d)

    if not args.cache_dir and not os.environ.get("MOVIE_STORY_STAGE_D_CACHE_DIR"):
        os.environ["MOVIE_STORY_STAGE_D_CACHE_DIR"] = str(audit_dir / "_stage_d_llm_cache")

    cfg = understanding_quality.resolve_stage_d_llm_config(api_key=args.api_key, base_url=args.base_url, model=args.model)
    config_warning = None
    if not cfg.get("ready"):
        # Do not exit immediately: maybe_run_live_understanding_samples can still
        # hydrate from existing cache files before attempting live calls.  If no
        # cache exists, Stage-E verification will fail with missing llm_result and
        # the report below will expose the config problem.
        config_warning = {
            "reason": "LLM config missing; cache-only hydration attempted",
            "need": ["api_key", "model"],
            "accepted_env": [
                "MOVIE_STORY_STAGE_D_API_KEY / MOVIE_STORY_STAGE_D_MODEL / MOVIE_STORY_STAGE_D_BASE_URL",
                "MOVIE_STORY_TEXT_LLM_API_KEY / MOVIE_STORY_TEXT_LLM_MODEL / MOVIE_STORY_TEXT_LLM_BASE_URL",
                "TEXT_LITELLM_API_KEY / TEXT_LITELLM_MODEL_NAME / TEXT_LITELLM_BASE_URL",
                "OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL",
            ],
            "resolved_model": cfg.get("model"),
            "has_base_url": bool(cfg.get("base_url")),
        }

    prepared = _refresh_stage_d_quality(_select_for_live(items, max_live_calls=args.max_live_calls, min_global=args.min_global, min_local=args.min_local))
    live_items = understanding_quality.maybe_run_live_understanding_samples(
        prepared,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_live_calls=args.max_live_calls,
        timeout=args.timeout,
    )
    live_items = _refresh_stage_d_quality(live_items)
    stage_d_report = understanding_quality.evaluate_stage_d_items(
        live_items,
        max_llm_calls=args.max_live_calls,
        min_local_samples=min(6, max(0, sum(1 for x in live_items if x.get("request_type") == "local_understanding_refine"))),
    )
    _write_stage(stage_d, live_items, meta={
        "source": "stage_d_live_understanding_samples_post_run_tool",
        "migration_stage": "stage_d",
        "overall_passed": stage_d_report.get("overall_passed"),
        "pass_rate": stage_d_report.get("pass_rate"),
        "llm_call_enabled": True,
        "llm_enabled_count": stage_d_report.get("llm_enabled_count"),
        "max_live_calls": args.max_live_calls,
        "global_request_count": stage_d_report.get("global_request_count"),
        "local_sample_count": stage_d_report.get("local_sample_count"),
        "cache_ready_count": stage_d_report.get("cache_ready_count"),
        "over_budget_count": stage_d_report.get("over_budget_count"),
    })

    e_items = understanding_writeback.build_stage_e_writeback_items(live_items)
    e_report = understanding_writeback.evaluate_stage_e_items(
        e_items,
        min_global_results=args.min_global,
        min_local_results=args.min_local,
    )
    _write_stage(stage_e, e_items, meta={
        "source": "stage_e_writeback_contract_from_post_run_live_stage_d",
        "migration_stage": "stage_e",
        "overall_passed": e_report.get("overall_passed"),
        "pass_rate": e_report.get("pass_rate"),
        "global_success_count": e_report.get("global_success_count"),
        "local_success_count": e_report.get("local_success_count"),
        "missing_result_count": e_report.get("missing_result_count"),
        "disallowed_writeback_count": e_report.get("disallowed_writeback_count"),
    })

    diag = _live_diagnostics(live_items)
    report = {
        "overall_passed": bool(e_report.get("overall_passed")),
        "audit_dir": str(audit_dir),
        "stage_d_items": len(live_items),
        "stage_e_items": len(e_items),
        "stage_d_llm_enabled_count": stage_d_report.get("llm_enabled_count"),
        "live_selected_count": diag.get("live_selected_count"),
        "live_result_count": diag.get("live_result_count"),
        "live_failed_count": diag.get("live_failed_count"),
        "llm_result_source_counts": diag.get("llm_result_source_counts"),
        "live_failed_items": diag.get("live_failed_items"),
        "stage_e_global_success_count": e_report.get("global_success_count"),
        "stage_e_local_success_count": e_report.get("local_success_count"),
        "stage_e_missing_result_count": e_report.get("missing_result_count"),
        "config_warning": config_warning,
        "next_command": f"python tools/verify_movie_story_migration_stage.py --stage stage_e --audit-dir {audit_dir} --stage-e-max-llm-calls {args.max_live_calls} --stage-e-min-global-results {args.min_global} --stage-e-min-local-results {args.min_local}",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
