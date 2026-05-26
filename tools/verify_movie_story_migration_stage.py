#!/usr/bin/env python3
from __future__ import annotations

"""Verify movie-story migration stage targets.

Usage:
  python tools/verify_movie_story_migration_stage.py --stage stage_a --audit-dir <run_dir>
  python tools/verify_movie_story_migration_stage.py --stage stage_a --audit-json <movie_story_audit.json>

Stage A checks whether the old project's global/local understanding and rich
scene_evidence layer has been migrated into the new pipeline. It does not judge
final narration wording.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.movie_story.evidence_enrichment import (  # noqa: E402
    REQUIRED_EVIDENCE_FIELDS,
    evaluate_evidence_items,
    score_evidence_item,
)
from app.services.movie_story.highlight_planning import (  # noqa: E402
    STAGE_B_REQUIRED_HIGHLIGHT_FIELDS,
    STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS,
    evaluate_stage_b_highlights,
    score_stage_b_highlight,
)
from app.services.movie_story.narration_contract import (  # noqa: E402
    STAGE_C_REQUIRED_ITEM_FIELDS,
    STAGE_C_REQUIRED_PAYLOAD_FIELDS,
    STAGE_C_REQUIRED_SEGMENT_FIELDS,
    evaluate_stage_c_replay_items,
    score_stage_c_item,
)
from app.services.movie_story.understanding_quality import (  # noqa: E402
    STAGE_D_REQUIRED_ITEM_FIELDS,
    STAGE_D_REQUIRED_PAYLOAD_FIELDS,
    STAGE_D_GLOBAL_TARGET_FIELDS,
    STAGE_D_LOCAL_TARGET_FIELDS,
    evaluate_stage_d_items,
    score_stage_d_item,
)
from app.services.movie_story.understanding_writeback import (  # noqa: E402
    STAGE_E_REQUIRED_ITEM_FIELDS,
    STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS,
    STAGE_E_LOCAL_REQUIRED_MIN_FIELDS,
    evaluate_stage_e_items,
    score_stage_e_item,
)

from app.services.movie_story.narration_sample import (  # noqa: E402
    STAGE_F_REQUIRED_ITEM_FIELDS,
    STAGE_F_REQUIRED_RESULT_FIELDS,
    STAGE_F_REQUIRED_INPUT_FLAGS,
    STAGE_F_STAGE_NAME,
    evaluate_stage_f_items,
    score_stage_f_item,
)

from app.services.movie_story.narration_validation_sample import (  # noqa: E402
    STAGE_G_REQUIRED_ITEM_FIELDS,
    STAGE_G_REQUIRED_RESULT_FIELDS,
    STAGE_G_REQUIRED_INPUT_FLAGS,
    STAGE_G_STAGE_NAME,
    evaluate_stage_g_items,
    score_stage_g_item,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_items(path: Path) -> List[Dict[str, Any]]:
    # Prefer full raw records when available.  manifest.json rows are deliberately
    # compact for CSV/audit display and may omit Stage-A rich evidence fields.
    full = path.parent / "items_full.json"
    if full.exists():
        try:
            payload = _load_json(full)
            if isinstance(payload, list):
                return [x for x in payload if isinstance(x, dict)]
        except Exception:
            pass
    payload = _load_json(path)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("records") or []
        return [x for x in items if isinstance(x, dict)]
    return []


def _find_stage_manifest(audit_dir: Path, stage_name: str) -> Path | None:
    """Find stage manifests across legacy and namespaced audit layouts.

    Current movie_story runtime stores active pipeline audit outputs under
    producer namespaces such as ``runtime/`` and maps some legacy names to
    explicit runtime names. The verifier accepts both layouts so migration
    checks can validate the current contract without reconnecting old output
    directories.
    """

    alias_map = {
        "04_global_story_context": ["04_runtime_story_context", "04_story_audit_global_context"],
        "05_selected_highlights": ["05_runtime_selected_highlight_candidates", "05_story_audit_selected_highlights"],
        "06_scene_evidence_for_narration": [
            "06_runtime_scene_evidence_for_narration",
            "06_story_audit_scene_evidence_for_narration",
        ],
        "06a_evidence_completeness": ["06a_runtime_evidence_completeness", "06a_story_audit_evidence_completeness"],
    }
    aliases = {stage_name, *alias_map.get(stage_name, [])}
    for alias in aliases:
        direct = audit_dir / alias / "manifest.json"
        if direct.exists():
            return direct
        for namespace in ("runtime", "story_audit"):
            namespaced = audit_dir / namespace / alias / "manifest.json"
            if namespaced.exists():
                return namespaced

    patterns: list[str] = []
    for alias in aliases:
        patterns.extend([
            f"run_*/{alias}/manifest.json",
            f"run_*/*/{alias}/manifest.json",
            f"*/{alias}/manifest.json",
        ])
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(audit_dir.glob(pattern))
    candidates = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _extract_from_audit_json(path: Path) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return {}, []
    global_summary = payload.get("global_summary") or {}
    evidence = payload.get("highlight_narration_segments") or payload.get("selected_scene_evidence") or []
    return global_summary if isinstance(global_summary, dict) else {}, [x for x in evidence if isinstance(x, dict)]


def _global_context_status(global_row_or_context: Mapping[str, Any] | None) -> Dict[str, Any]:
    ctx = dict(global_row_or_context or {})
    # Full records may store the context nested under global_context.
    if isinstance(ctx.get("global_context"), dict):
        nested = dict(ctx.get("global_context") or {})
        nested.update({k: v for k, v in ctx.items() if v not in (None, "", [], {})})
        ctx = nested
    # Manifest rows store most details in text, but also expose summary fields.
    if "text" in ctx and not ctx.get("main_conflict"):
        try:
            parsed = json.loads(str(ctx.get("text") or "{}"))
            if isinstance(parsed, dict):
                ctx.update(parsed)
        except Exception:
            pass
    required = ["main_conflict", "story_theme", "genre", "main_characters", "timeline_summary"]
    missing = []
    for key in required:
        value = ctx.get(key)
        if isinstance(value, str) and value.startswith("["):
            try:
                value = json.loads(value)
            except Exception:
                pass
        if not value or (isinstance(value, list) and len(value) == 0):
            missing.append(key)
    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "main_conflict": ctx.get("main_conflict", ""),
        "genre": ctx.get("genre", ""),
        "timeline_nodes": len(ctx.get("timeline_summary") or []) if isinstance(ctx.get("timeline_summary"), list) else None,
    }


def verify_stage_a(audit_dir: Path | None = None, audit_json: Path | None = None, min_pass_rate: float = 0.9) -> Dict[str, Any]:
    global_status: Dict[str, Any]
    evidence_items: List[Dict[str, Any]]
    source = ""
    if audit_json:
        global_summary, evidence_items = _extract_from_audit_json(audit_json)
        global_status = _global_context_status(global_summary)
        source = str(audit_json)
    elif audit_dir:
        global_manifest = _find_stage_manifest(audit_dir, "04_global_story_context")
        evidence_manifest = _find_stage_manifest(audit_dir, "06_scene_evidence_for_narration")
        if not global_manifest:
            global_status = {"passed": False, "missing": ["04_global_story_context"], "main_conflict": "", "genre": ""}
        else:
            rows = _manifest_items(global_manifest)
            global_status = _global_context_status(rows[0] if rows else {})
        if not evidence_manifest:
            evidence_items = []
        else:
            evidence_items = _manifest_items(evidence_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    # Manifest rows may include only brief evidence fields. Score those directly.
    scored = []
    for item in evidence_items:
        if "evidence_completeness" not in item:
            item = dict(item)
            item["evidence_completeness"] = score_evidence_item(item)
        scored.append(item)
    evidence_status = evaluate_evidence_items(scored, min_pass_rate=min_pass_rate)
    checks = {
        "global_context_ready": bool(global_status.get("passed")),
        "evidence_stage_present": bool(evidence_items),
        "required_evidence_pass_rate": evidence_status.get("pass_rate", 0.0),
        "required_evidence_target": min_pass_rate,
        "required_fields": REQUIRED_EVIDENCE_FIELDS,
    }
    overall = bool(global_status.get("passed")) and bool(evidence_items) and bool(evidence_status.get("overall_passed"))
    next_targets = []
    if not global_status.get("passed"):
        next_targets.append("补齐 04_global_story_context：main_conflict / story_theme / genre / main_characters / timeline_summary")
    if not evidence_items:
        next_targets.append("生成 06_scene_evidence_for_narration 审计产物")
    if evidence_items and not evidence_status.get("overall_passed"):
        missing = evidence_status.get("top_missing_required") or []
        next_targets.append("补齐 rich scene_evidence 缺失字段：" + ", ".join(f"{k}({v})" for k, v in missing[:8]))
    if overall:
        next_targets.append("阶段 A 已达标，可进入阶段 B：旧项目高光规划与 narration_generation 输入契约验收")
    return {
        "stage": "stage_a_global_local_evidence",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "global_context": global_status,
        "evidence_completeness": evidence_status,
        "next_targets": next_targets,
    }



def verify_stage_b(audit_dir: Path | None = None, audit_json: Path | None = None, min_pass_rate: float = 0.9) -> Dict[str, Any]:
    """Verify Stage B: legacy highlight planning + narration input contract.

    This stage still does not judge final narration wording and does not call
    an LLM.  It verifies that selected highlights are no longer just time/text
    rows: each highlight must carry story_role, selection_reason, score_breakdown,
    source_scene_ids, and a narration_generation_input payload that the legacy
    narration_generation prompt can consume later.
    """
    source = ""
    stage_a_status: Dict[str, Any] = {"overall_passed": False}
    highlight_items: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            highlight_items = [x for x in (payload.get("selected_highlights") or payload.get("highlights") or []) if isinstance(x, dict)]
            evidence_items = [x for x in (payload.get("highlight_narration_segments") or payload.get("selected_scene_evidence") or []) if isinstance(x, dict)]
        source = str(audit_json)
    elif audit_dir:
        stage_a_status = verify_stage_a(audit_dir=audit_dir, min_pass_rate=min_pass_rate)
        planning_manifest = _find_stage_manifest(audit_dir, "05b_highlight_planning_contract")
        selected_manifest = _find_stage_manifest(audit_dir, "05_selected_highlights")
        evidence_manifest = _find_stage_manifest(audit_dir, "06_scene_evidence_for_narration")
        if planning_manifest:
            highlight_items = _manifest_items(planning_manifest)
        elif selected_manifest:
            highlight_items = _manifest_items(selected_manifest)
        if evidence_manifest:
            evidence_items = _manifest_items(evidence_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored_highlights: List[Dict[str, Any]] = []
    for item in highlight_items:
        cur = dict(item)
        if "stage_b_quality" not in cur:
            cur["stage_b_quality"] = score_stage_b_highlight(cur)
        scored_highlights.append(cur)
    highlight_status = evaluate_stage_b_highlights(scored_highlights, min_pass_rate=min_pass_rate)

    scored_evidence = []
    for item in evidence_items:
        cur = dict(item)
        if "evidence_completeness" not in cur:
            cur["evidence_completeness"] = score_evidence_item(cur)
        scored_evidence.append(cur)
    evidence_status = evaluate_evidence_items(scored_evidence, min_pass_rate=min_pass_rate)

    checks = {
        "stage_a_prerequisite_passed": bool(stage_a_status.get("overall_passed")),
        "highlight_planning_stage_present": bool(highlight_items),
        "evidence_stage_present": bool(evidence_items),
        "highlight_contract_pass_rate": highlight_status.get("pass_rate", 0.0),
        "highlight_contract_target": min_pass_rate,
        "highlight_type_count": highlight_status.get("type_count", 0),
        "highlight_type_min": highlight_status.get("min_type_count", 3),
        "highlight_arc_count": highlight_status.get("arc_count", 0),
        "highlight_arc_min": highlight_status.get("min_arc_count", 3),
        "evidence_contract_pass_rate": evidence_status.get("pass_rate", 0.0),
        "required_highlight_fields": STAGE_B_REQUIRED_HIGHLIGHT_FIELDS,
        "required_narration_input_fields": STAGE_B_REQUIRED_NARRATION_INPUT_FIELDS,
    }
    overall = (
        bool(stage_a_status.get("overall_passed"))
        and bool(highlight_items)
        and bool(evidence_items)
        and bool(highlight_status.get("overall_passed"))
        and bool(evidence_status.get("overall_passed"))
    )
    next_targets = []
    if not stage_a_status.get("overall_passed"):
        next_targets.append("先修复阶段 A：global_summary / local_understanding / rich scene_evidence 未达标")
    if not highlight_items:
        next_targets.append("生成 05b_highlight_planning_contract 审计产物")
    if highlight_items and not highlight_status.get("overall_passed"):
        next_targets.append("补齐 Stage-B 高光规划字段：story_role / selection_reason / score_breakdown / source_scene_ids / narration_generation_input")
    if highlight_status.get("type_count", 0) < highlight_status.get("min_type_count", 3):
        next_targets.append("提高高光类型多样性：selected_highlights 至少覆盖 3 类 highlight_type")
    if highlight_status.get("arc_count", 0) < highlight_status.get("min_arc_count", 3):
        next_targets.append("补齐故事弧线角色：至少覆盖 opening/conflict/reveal/reversal/ending 中的 3 类")
    if not evidence_items:
        next_targets.append("生成 06_scene_evidence_for_narration 审计产物")
    if evidence_items and not evidence_status.get("overall_passed"):
        next_targets.append("保持阶段 A rich evidence 合同：06 evidence 不得被高光规划阶段降级")
    if overall:
        next_targets.append("阶段 B 已达标，可进入阶段 C：旧项目 narration_generation prompt 接入与禁用最终 LLM 的输入回放验收")

    return {
        "stage": "stage_b_highlight_planning_contract",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_a_prerequisite": {"overall_passed": bool(stage_a_status.get("overall_passed"))},
        "highlight_planning": highlight_status,
        "evidence_completeness": evidence_status,
        "next_targets": next_targets,
    }


def verify_stage_c(
    audit_dir: Path | None = None,
    audit_json: Path | None = None,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 12000,
) -> Dict[str, Any]:
    """Verify Stage C: legacy narration_generation prompt input replay.

    This stage does not call an LLM and does not judge final narration wording.
    It verifies that every selected highlight can be converted into the legacy
    narration_generation prompt payload while LLM calls are explicitly disabled.
    """
    source = ""
    stage_b_status: Dict[str, Any] = {"overall_passed": False}
    replay_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            replay_items = [x for x in (payload.get("narration_generation_input_replay") or payload.get("stage_c_items") or []) if isinstance(x, dict)]
        source = str(audit_json)
    elif audit_dir:
        stage_b_status = verify_stage_b(audit_dir=audit_dir, min_pass_rate=min_pass_rate)
        replay_manifest = _find_stage_manifest(audit_dir, "06b_narration_generation_input_contract")
        if replay_manifest:
            replay_items = _manifest_items(replay_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored: List[Dict[str, Any]] = []
    for item in replay_items:
        cur = dict(item)
        if "input_contract_quality" not in cur:
            cur["input_contract_quality"] = score_stage_c_item(cur, max_input_chars=max_input_chars)
        scored.append(cur)
    stage_c_status = evaluate_stage_c_replay_items(scored, min_pass_rate=min_pass_rate, max_input_chars=max_input_chars)

    checks = {
        "stage_b_prerequisite_passed": bool(stage_b_status.get("overall_passed")),
        "narration_input_stage_present": bool(replay_items),
        "narration_input_pass_rate": stage_c_status.get("pass_rate", 0.0),
        "narration_input_target": min_pass_rate,
        "llm_enabled_count": stage_c_status.get("llm_enabled_count", 0),
        "over_budget_count": stage_c_status.get("over_budget_count", 0),
        "required_item_fields": STAGE_C_REQUIRED_ITEM_FIELDS,
        "required_payload_fields": STAGE_C_REQUIRED_PAYLOAD_FIELDS,
        "required_segment_fields": STAGE_C_REQUIRED_SEGMENT_FIELDS,
    }
    overall = (
        bool(stage_b_status.get("overall_passed"))
        and bool(replay_items)
        and bool(stage_c_status.get("overall_passed"))
    )
    next_targets = []
    if not stage_b_status.get("overall_passed"):
        next_targets.append("先修复阶段 B：高光规划与 narration_generation 输入前置合同未达标")
    if not replay_items:
        next_targets.append("生成 06b_narration_generation_input_contract 审计产物")
    if replay_items and not stage_c_status.get("overall_passed"):
        next_targets.append("补齐 Stage-C 旧 narration_generation prompt 输入：segment_json / project_context / narration_intent / char_budget / llm_call_enabled=false")
    if stage_c_status.get("llm_enabled_count", 0):
        next_targets.append("Stage C 必须禁用最终 LLM：所有 replay item 的 llm_call_enabled 必须为 false")
    if stage_c_status.get("over_budget_count", 0):
        next_targets.append("压缩 narration_generation 输入包：payload_chars 不得超过 max_input_chars")
    if overall:
        next_targets.append("阶段 C 已达标，可进入阶段 D：开启/抽样迁移旧项目全局与局部 LLM 理解质量")

    return {
        "stage": "stage_c_narration_generation_input_replay",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_b_prerequisite": {"overall_passed": bool(stage_b_status.get("overall_passed"))},
        "narration_generation_input_contract": stage_c_status,
        "next_targets": next_targets,
    }


def verify_stage_d(
    audit_dir: Path | None = None,
    audit_json: Path | None = None,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 9000,
    max_llm_calls: int = 0,
    min_local_samples: int = 6,
) -> Dict[str, Any]:
    """Verify Stage D: legacy global/local understanding quality sample contract.

    Stage D still does not check final narration.  It verifies that old-project
    global_summary/add_local_understanding LLM refinement can be reintroduced in
    a bounded, cached, sample-based way.  By default max_llm_calls=0, so the
    contract can pass without spending tokens.  If live sampling is enabled in a
    run, set --max-llm-calls accordingly.
    """
    source = ""
    stage_c_status: Dict[str, Any] = {"overall_passed": False}
    sample_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            sample_items = [x for x in (payload.get("understanding_quality_samples") or payload.get("stage_d_items") or []) if isinstance(x, dict)]
        # Direct audit-json mode is used for isolated Stage-D reports/replay; do
        # not require the whole A/B/C directory stack in that mode.
        stage_c_status = {"overall_passed": bool(sample_items)}
        source = str(audit_json)
    elif audit_dir:
        stage_c_status = verify_stage_c(audit_dir=audit_dir, min_pass_rate=min_pass_rate, max_input_chars=12000)
        sample_manifest = _find_stage_manifest(audit_dir, "06c_understanding_quality_sample_contract")
        if sample_manifest:
            sample_items = _manifest_items(sample_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored: List[Dict[str, Any]] = []
    for item in sample_items:
        cur = dict(item)
        if "understanding_contract_quality" not in cur:
            cur["understanding_contract_quality"] = score_stage_d_item(cur, max_input_chars=max_input_chars)
        scored.append(cur)
    stage_d_status = evaluate_stage_d_items(
        scored,
        min_pass_rate=min_pass_rate,
        max_input_chars=max_input_chars,
        max_llm_calls=max_llm_calls,
        min_local_samples=min_local_samples,
    )

    checks = {
        "stage_c_prerequisite_passed": bool(stage_c_status.get("overall_passed")),
        "understanding_sample_stage_present": bool(sample_items),
        "understanding_sample_pass_rate": stage_d_status.get("pass_rate", 0.0),
        "understanding_sample_target": min_pass_rate,
        "global_request_count": stage_d_status.get("global_request_count", 0),
        "local_sample_count": stage_d_status.get("local_sample_count", 0),
        "min_local_samples": min_local_samples,
        "llm_enabled_count": stage_d_status.get("llm_enabled_count", 0),
        "max_llm_calls": max_llm_calls,
        "cache_ready_count": stage_d_status.get("cache_ready_count", 0),
        "over_budget_count": stage_d_status.get("over_budget_count", 0),
        "required_item_fields": STAGE_D_REQUIRED_ITEM_FIELDS,
        "required_payload_fields": STAGE_D_REQUIRED_PAYLOAD_FIELDS,
        "global_target_fields": STAGE_D_GLOBAL_TARGET_FIELDS,
        "local_target_fields": STAGE_D_LOCAL_TARGET_FIELDS,
    }
    overall = (
        bool(stage_c_status.get("overall_passed"))
        and bool(sample_items)
        and bool(stage_d_status.get("overall_passed"))
    )
    next_targets = []
    if not stage_c_status.get("overall_passed"):
        next_targets.append("先修复阶段 C：旧 narration_generation prompt 输入契约未达标")
    if not sample_items:
        next_targets.append("生成 06c_understanding_quality_sample_contract 审计产物")
    if sample_items and not stage_d_status.get("overall_passed"):
        next_targets.append("补齐 Stage-D 理解抽样合同：global/local prompt_payload / cache_key / quality_targets / budget")
    if stage_d_status.get("global_request_count", 0) < 1:
        next_targets.append("Stage-D 必须至少包含 1 条 global_story_context_refine 样本")
    if stage_d_status.get("local_sample_count", 0) < min_local_samples:
        next_targets.append(f"Stage-D local_understanding_refine 样本不足：至少 {min_local_samples} 条")
    if stage_d_status.get("llm_enabled_count", 0) > max_llm_calls:
        next_targets.append("Stage-D LLM 抽样调用数超过预算；调低配置或提高 --max-llm-calls")
    if stage_d_status.get("over_budget_count", 0):
        next_targets.append("压缩 Stage-D 理解输入包：payload_chars 不得超过 max_input_chars")
    if overall:
        next_targets.append("阶段 D 已达标，可进入阶段 E：受控开启旧项目理解 LLM 结果回写与质量评分")

    return {
        "stage": "stage_d_understanding_quality_sample_contract",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_c_prerequisite": {"overall_passed": bool(stage_c_status.get("overall_passed"))},
        "understanding_quality_samples": stage_d_status,
        "next_targets": next_targets,
    }




def verify_stage_e(
    audit_dir: Path | None = None,
    audit_json: Path | None = None,
    min_pass_rate: float = 0.9,
    stage_d_max_input_chars: int = 9000,
    stage_d_max_llm_calls: int = 20,
    min_local_samples: int = 6,
    min_global_results: int = 1,
    min_local_results: int = 2,
) -> Dict[str, Any]:
    """Verify Stage E: legacy understanding LLM result writeback.

    Stage E is expected to fail until Stage-D live/cached understanding results
    exist.  It still does not check final narration.  It validates that only
    whitelisted global/local understanding fields are ready to be written back.
    """
    source = ""
    stage_d_status: Dict[str, Any] = {"overall_passed": False}
    writeback_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            writeback_items = [x for x in (payload.get("understanding_result_writebacks") or payload.get("stage_e_items") or []) if isinstance(x, dict)]
        stage_d_status = {"overall_passed": bool(writeback_items)}
        source = str(audit_json)
    elif audit_dir:
        stage_d_status = verify_stage_d(
            audit_dir=audit_dir,
            min_pass_rate=min_pass_rate,
            max_input_chars=stage_d_max_input_chars,
            max_llm_calls=stage_d_max_llm_calls,
            min_local_samples=min_local_samples,
        )
        writeback_manifest = _find_stage_manifest(audit_dir, "06d_understanding_result_writeback_contract")
        if writeback_manifest:
            writeback_items = _manifest_items(writeback_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored: List[Dict[str, Any]] = []
    for item in writeback_items:
        cur = dict(item)
        if "writeback_quality" not in cur:
            cur["writeback_quality"] = score_stage_e_item(cur)
        scored.append(cur)
    stage_e_status = evaluate_stage_e_items(
        scored,
        min_pass_rate=min_pass_rate,
        min_global_results=min_global_results,
        min_local_results=min_local_results,
    )

    checks = {
        "stage_d_prerequisite_passed": bool(stage_d_status.get("overall_passed")),
        "understanding_writeback_stage_present": bool(writeback_items),
        "writeback_pass_rate": stage_e_status.get("pass_rate", 0.0),
        "writeback_target": min_pass_rate,
        "global_success_count": stage_e_status.get("global_success_count", 0),
        "local_success_count": stage_e_status.get("local_success_count", 0),
        "min_global_results": min_global_results,
        "min_local_results": min_local_results,
        "missing_result_count": stage_e_status.get("missing_result_count", 0),
        "disallowed_writeback_count": stage_e_status.get("disallowed_writeback_count", 0),
        "required_item_fields": STAGE_E_REQUIRED_ITEM_FIELDS,
        "global_required_min_fields": STAGE_E_GLOBAL_REQUIRED_MIN_FIELDS,
        "local_required_min_fields": STAGE_E_LOCAL_REQUIRED_MIN_FIELDS,
    }
    overall = (
        bool(stage_d_status.get("overall_passed"))
        and bool(writeback_items)
        and bool(stage_e_status.get("overall_passed"))
    )
    next_targets = []
    if not stage_d_status.get("overall_passed"):
        next_targets.append("先修复阶段 D：理解抽样合同或 LLM 调用预算未达标")
    if not writeback_items:
        next_targets.append("生成 06d_understanding_result_writeback_contract 审计产物")
    if writeback_items and not stage_e_status.get("overall_passed"):
        next_targets.append("补齐 Stage-E 真实 LLM 理解结果：至少 1 条 global 与 2 条 local 可白名单回写")
    if stage_e_status.get("missing_result_count", 0) and not overall:
        next_targets.append("Stage-E 缺少 llm_result：运行 tools/run_stage_d_understanding_live.py 对现有 audit 执行受控理解抽样，不需要重跑最终解说")
    if stage_e_status.get("disallowed_writeback_count", 0):
        next_targets.append("Stage-E 出现非白名单回写字段，必须过滤后再回写")
    if overall:
        next_targets.append("阶段 E 已达标，可进入阶段 F：使用回写后的理解结果进行最终 narration_generation 抽样生成")

    return {
        "stage": "stage_e_understanding_result_writeback_contract",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_d_prerequisite": {"overall_passed": bool(stage_d_status.get("overall_passed"))},
        "understanding_result_writebacks": stage_e_status,
        "next_targets": next_targets,
    }



def verify_stage_f(
    audit_dir: Path | None = None,
    audit_json: Path | None = None,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 12000,
    stage_e_min_global_results: int = 1,
    stage_e_min_local_results: int = 2,
    stage_e_max_llm_calls: int = 20,
    min_results: int = 2,
    max_llm_calls: int = 2,
) -> Dict[str, Any]:
    """Verify Stage F: bounded final narration_generation sample contract.

    Stage F is the first small-budget final narration check. It requires Stage E
    to have at least one global and two local understanding writebacks.  It then
    validates that 07a_narration_generation_sample_contract contains generated
    sample narration rows that used Stage-E writebacks and stayed within budget.
    """
    source = ""
    stage_e_status: Dict[str, Any] = {"overall_passed": False}
    sample_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            sample_items = [x for x in (payload.get("narration_generation_samples") or payload.get("stage_f_items") or []) if isinstance(x, dict)]
        stage_e_status = {"overall_passed": bool(sample_items)}
        source = str(audit_json)
    elif audit_dir:
        stage_e_status = verify_stage_e(
            audit_dir=audit_dir,
            min_pass_rate=min_pass_rate,
            stage_d_max_input_chars=9000,
            stage_d_max_llm_calls=stage_e_max_llm_calls,
            min_local_samples=6,
            min_global_results=stage_e_min_global_results,
            min_local_results=stage_e_min_local_results,
        )
        sample_manifest = _find_stage_manifest(audit_dir, STAGE_F_STAGE_NAME)
        if sample_manifest:
            sample_items = _manifest_items(sample_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored: List[Dict[str, Any]] = []
    for item in sample_items:
        cur = dict(item)
        if "narration_quality" not in cur:
            cur["narration_quality"] = score_stage_f_item(cur, max_input_chars=max_input_chars)
        scored.append(cur)
    stage_f_status = evaluate_stage_f_items(
        scored,
        min_pass_rate=min_pass_rate,
        min_results=min_results,
        max_llm_calls=max_llm_calls,
        max_input_chars=max_input_chars,
    )

    checks = {
        "stage_e_prerequisite_passed": bool(stage_e_status.get("overall_passed")),
        "narration_sample_stage_present": bool(sample_items),
        "narration_sample_pass_rate": stage_f_status.get("pass_rate", 0.0),
        "narration_sample_target": min_pass_rate,
        "passed_sample_count": stage_f_status.get("passed", 0),
        "min_results": min_results,
        "live_or_cache_result_count": stage_f_status.get("live_or_cache_result_count", 0),
        "llm_enabled_count": stage_f_status.get("llm_enabled_count", 0),
        "max_llm_calls": max_llm_calls,
        "missing_result_count": stage_f_status.get("missing_result_count", 0),
        "required_item_fields": STAGE_F_REQUIRED_ITEM_FIELDS,
        "required_result_fields": STAGE_F_REQUIRED_RESULT_FIELDS,
        "required_input_flags": STAGE_F_REQUIRED_INPUT_FLAGS,
    }
    overall = bool(stage_e_status.get("overall_passed")) and bool(sample_items) and bool(stage_f_status.get("overall_passed"))
    next_targets = []
    if not stage_e_status.get("overall_passed"):
        next_targets.append("先修复阶段 E：至少 1 条 global 与 2 条 local 理解结果必须可白名单回写")
    if not sample_items:
        next_targets.append("运行 tools/run_stage_f_narration_live.py 生成 07a_narration_generation_sample_contract")
    if sample_items and not stage_f_status.get("overall_passed"):
        next_targets.append("补齐 Stage-F narration_generation 抽样结果：至少生成 min_results 条，并确认使用 Stage-E global/local writeback、narration_intent、story_function、char_budget")
    if stage_f_status.get("llm_enabled_count", 0) > max_llm_calls:
        next_targets.append("Stage-F LLM 抽样数超过预算，调低 --max-live-calls 或提高 --stage-f-max-llm-calls")
    if overall:
        next_targets.append("阶段 F 已达标，可进入阶段 G：旧项目 narration_validation 抽样校验与安全重写契约")

    return {
        "stage": "stage_f_narration_generation_sample_contract",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_e_prerequisite": {"overall_passed": bool(stage_e_status.get("overall_passed"))},
        "narration_generation_samples": stage_f_status,
        "next_targets": next_targets,
    }



def verify_stage_g(
    audit_dir: Path | None = None,
    audit_json: Path | None = None,
    min_pass_rate: float = 0.9,
    max_input_chars: int = 12000,
    stage_e_min_global_results: int = 1,
    stage_e_min_local_results: int = 2,
    stage_e_max_llm_calls: int = 20,
    stage_f_min_results: int = 2,
    stage_f_max_llm_calls: int = 2,
    min_results: int = 2,
    max_llm_calls: int = 2,
) -> Dict[str, Any]:
    """Verify Stage G: bounded narration_validation sample contract.

    Stage G requires Stage F to have generated bounded narration samples, then
    verifies that 07b_narration_validation_sample_contract contains validation
    rows that used the generated narration and the original rich evidence.
    """
    source = ""
    stage_f_status: Dict[str, Any] = {"overall_passed": False}
    validation_items: List[Dict[str, Any]] = []

    if audit_json:
        payload = _load_json(audit_json)
        if isinstance(payload, dict):
            validation_items = [x for x in (payload.get("narration_validation_samples") or payload.get("stage_g_items") or []) if isinstance(x, dict)]
        stage_f_status = {"overall_passed": bool(validation_items)}
        source = str(audit_json)
    elif audit_dir:
        stage_f_status = verify_stage_f(
            audit_dir=audit_dir,
            min_pass_rate=min_pass_rate,
            max_input_chars=max_input_chars,
            stage_e_min_global_results=stage_e_min_global_results,
            stage_e_min_local_results=stage_e_min_local_results,
            stage_e_max_llm_calls=stage_e_max_llm_calls,
            min_results=stage_f_min_results,
            max_llm_calls=stage_f_max_llm_calls,
        )
        sample_manifest = _find_stage_manifest(audit_dir, STAGE_G_STAGE_NAME)
        if sample_manifest:
            validation_items = _manifest_items(sample_manifest)
        source = str(audit_dir)
    else:
        raise ValueError("需要提供 --audit-dir 或 --audit-json")

    scored: List[Dict[str, Any]] = []
    for item in validation_items:
        cur = dict(item)
        if "validation_quality" not in cur:
            cur["validation_quality"] = score_stage_g_item(cur, max_input_chars=max_input_chars)
        scored.append(cur)
    stage_g_status = evaluate_stage_g_items(
        scored,
        min_pass_rate=min_pass_rate,
        min_results=min_results,
        max_llm_calls=max_llm_calls,
        max_input_chars=max_input_chars,
    )

    checks = {
        "stage_f_prerequisite_passed": bool(stage_f_status.get("overall_passed")),
        "narration_validation_stage_present": bool(validation_items),
        "narration_validation_pass_rate": stage_g_status.get("pass_rate", 0.0),
        "narration_validation_target": min_pass_rate,
        "passed_validation_count": stage_g_status.get("passed", 0),
        "min_results": min_results,
        "live_or_cache_result_count": stage_g_status.get("live_or_cache_result_count", 0),
        "llm_enabled_count": stage_g_status.get("llm_enabled_count", 0),
        "max_llm_calls": max_llm_calls,
        "missing_result_count": stage_g_status.get("missing_result_count", 0),
        "review_or_reject_count": stage_g_status.get("review_or_reject_count", 0),
        "rewrite_ready_count": stage_g_status.get("rewrite_ready_count", 0),
        "required_item_fields": STAGE_G_REQUIRED_ITEM_FIELDS,
        "required_result_fields": STAGE_G_REQUIRED_RESULT_FIELDS,
        "required_input_flags": STAGE_G_REQUIRED_INPUT_FLAGS,
    }
    overall = bool(stage_f_status.get("overall_passed")) and bool(validation_items) and bool(stage_g_status.get("overall_passed"))
    next_targets = []
    if not stage_f_status.get("overall_passed"):
        next_targets.append("先修复阶段 F：至少生成 2 条使用 Stage-E 回写的 narration_generation 抽样结果")
    if not validation_items:
        next_targets.append("运行 tools/run_stage_g_validation_live.py 生成 07b_narration_validation_sample_contract")
    if validation_items and not stage_g_status.get("overall_passed"):
        next_targets.append("补齐 Stage-G narration_validation 抽样结果：至少校验 min_results 条，并确认使用源 narration、segment evidence、Stage-E writeback、narration_intent、story_function")
    if stage_g_status.get("llm_enabled_count", 0) > max_llm_calls:
        next_targets.append("Stage-G LLM 抽样数超过预算，调低 --max-live-calls 或提高 --stage-g-max-llm-calls")
    if overall:
        next_targets.append("阶段 G 已达标，可进入阶段 H：安全重写结果回写到抽样 script_items，并建立最终脚本质量门禁")

    return {
        "stage": "stage_g_narration_validation_sample_contract",
        "source": source,
        "overall_passed": overall,
        "checks": checks,
        "stage_f_prerequisite": {"overall_passed": bool(stage_f_status.get("overall_passed"))},
        "narration_validation_samples": stage_g_status,
        "next_targets": next_targets,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="stage_a", choices=["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f", "stage_g"])
    ap.add_argument("--max-input-chars", type=int, default=12000, help="Stage C/D prompt input max chars")
    ap.add_argument("--max-llm-calls", type=int, default=0, help="Stage D allowed live LLM calls; default 0 for no-token contract check")
    ap.add_argument("--min-local-samples", type=int, default=6, help="Stage D minimum local understanding samples")
    ap.add_argument("--stage-e-min-global-results", type=int, default=1, help="Stage E minimum successful global writebacks")
    ap.add_argument("--stage-e-min-local-results", type=int, default=2, help="Stage E minimum successful local writebacks")
    ap.add_argument("--stage-e-max-llm-calls", type=int, default=20, help="Stage E accepted Stage-D LLM call budget when verifying prerequisite")
    ap.add_argument("--stage-f-min-results", type=int, default=2, help="Stage F minimum generated narration samples")
    ap.add_argument("--stage-f-max-llm-calls", type=int, default=2, help="Stage F maximum final narration LLM sample calls")
    ap.add_argument("--stage-g-min-results", type=int, default=2, help="Stage G minimum validation samples")
    ap.add_argument("--stage-g-max-llm-calls", type=int, default=2, help="Stage G maximum narration validation LLM sample calls")
    ap.add_argument("--audit-dir", type=Path)
    ap.add_argument("--audit-json", type=Path)
    ap.add_argument("--min-pass-rate", type=float, default=0.9)
    ap.add_argument("--output", type=Path, help="可选：写入 JSON 验收报告")
    ap.add_argument("--no-fail", action="store_true", help="即使未达标也返回 0")
    args = ap.parse_args()
    result = (
        verify_stage_a(args.audit_dir, args.audit_json, args.min_pass_rate)
        if args.stage == "stage_a"
        else verify_stage_b(args.audit_dir, args.audit_json, args.min_pass_rate)
        if args.stage == "stage_b"
        else verify_stage_c(args.audit_dir, args.audit_json, args.min_pass_rate, args.max_input_chars)
        if args.stage == "stage_c"
        else verify_stage_d(
            args.audit_dir,
            args.audit_json,
            args.min_pass_rate,
            max_input_chars=args.max_input_chars,
            max_llm_calls=args.max_llm_calls,
            min_local_samples=args.min_local_samples,
        )
        if args.stage == "stage_d"
        else verify_stage_e(
            args.audit_dir,
            args.audit_json,
            args.min_pass_rate,
            stage_d_max_input_chars=args.max_input_chars,
            stage_d_max_llm_calls=args.stage_e_max_llm_calls,
            min_local_samples=args.min_local_samples,
            min_global_results=args.stage_e_min_global_results,
            min_local_results=args.stage_e_min_local_results,
        )
        if args.stage == "stage_e"
        else verify_stage_f(
            args.audit_dir,
            args.audit_json,
            args.min_pass_rate,
            max_input_chars=args.max_input_chars,
            stage_e_min_global_results=args.stage_e_min_global_results,
            stage_e_min_local_results=args.stage_e_min_local_results,
            stage_e_max_llm_calls=args.stage_e_max_llm_calls,
            min_results=args.stage_f_min_results,
            max_llm_calls=args.stage_f_max_llm_calls,
        )
        if args.stage == "stage_f"
        else verify_stage_g(
            args.audit_dir,
            args.audit_json,
            args.min_pass_rate,
            max_input_chars=args.max_input_chars,
            stage_e_min_global_results=args.stage_e_min_global_results,
            stage_e_min_local_results=args.stage_e_min_local_results,
            stage_e_max_llm_calls=args.stage_e_max_llm_calls,
            stage_f_min_results=args.stage_f_min_results,
            stage_f_max_llm_calls=args.stage_f_max_llm_calls,
            min_results=args.stage_g_min_results,
            max_llm_calls=args.stage_g_max_llm_calls,
        )
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0 if (args.no_fail or result.get("overall_passed")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
