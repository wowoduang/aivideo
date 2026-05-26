from __future__ import annotations

from typing import Any, Dict, Mapping

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_user
from app.api.schemas.narration import (
    HighlightSelectionResponse,
    HighlightSelectionSaveRequest,
    HighlightSelectionSaveResponse,
    NarrationHumanizeRequest,
    NarrationHumanizeResponse,
    NarrationQualityReportPayload,
    NarrationQualityRequest,
    NarrationScriptVersionListResponse,
    NarrationScriptVersionRequest,
    NarrationScriptVersionResponse,
    NarrationWorkbenchResponse,
)
from app.repositories import artifact_repository, project_repository
from app.services import auth_store
from app.services.narration_quality import (
    build_evidence_pack,
    build_quality_report,
    build_timeline_blocks,
    humanize_script_segments,
    normalize_script_segments,
    write_narration_artifact,
)

router = APIRouter(prefix="/projects/{project_id}/narration", tags=["narration"])



def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except Exception:
        return default


def _first_text(raw: Mapping[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if not isinstance(value, (dict, list, tuple, set)):
            text = str(value).strip()
            if text:
                return text
    return default


def _normalize_reasons(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.replace("；", ";").split(";") if x.strip()]
    return []


def _normalize_highlight_selection_items(items: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    for index, raw_item in enumerate(items, start=1):
        raw = dict(raw_item or {})
        start = _safe_float(raw.get("video_start", raw.get("start", raw.get("start_sec", 0))))
        end = _safe_float(raw.get("video_end", raw.get("end", raw.get("end_sec", 0))))
        duration = _safe_float(raw.get("duration", 0))
        if end <= start and duration > 0:
            end = start + duration
        if end <= start:
            end = start + 0.1
        source_id = _first_text(raw, ["source_id", "source_candidate_id", "highlight_id", "candidate_id", "id"], f"h{index}")
        item_id = _first_text(raw, ["id", "highlight_id", "candidate_id"], source_id)
        reasons = _normalize_reasons(raw.get("selection_reasons") or raw.get("reasons") or raw.get("reason"))
        summary = _first_text(raw, ["summary", "narration", "subtitle_text", "main_text_evidence", "text", "content"], "")
        title = _first_text(raw, ["title", "label", "chapter_title"], "") or f"高光 {index}"
        scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
        if not scores:
            score_value = raw.get("highlight_score", raw.get("score", raw.get("importance_score")))
            if score_value is not None:
                scores = {"highlight_score": _safe_float(score_value)}
        selected = bool(raw.get("selected", not bool(raw.get("drop_suggestion", False))))
        normalized.append({
            "id": str(item_id),
            "source_id": str(source_id),
            "index": index,
            "rank": int(_safe_float(raw.get("rank", raw.get("highlight_rank", index)), index)),
            "selected": selected,
            "locked": bool(raw.get("locked", False)),
            "video_start": round(start, 3),
            "video_end": round(end, 3),
            "duration": round(max(0.1, end - start), 3),
            "title": title,
            "summary": summary,
            "reason": reasons[0] if reasons else _first_text(raw, ["reason", "drop_reason"], ""),
            "selection_reasons": reasons,
            "scores": scores,
            "character_trace": raw.get("character_trace") if isinstance(raw.get("character_trace"), dict) else {},
            "source_type": _first_text(raw, ["source_type", "candidate_type"], "highlight"),
            "raw": raw,
        })
    normalized.sort(key=lambda item: (int(item.get("rank") or 0), float(item.get("video_start") or 0), int(item.get("index") or 0)))
    for idx, item in enumerate(normalized, start=1):
        item["index"] = idx
    return normalized


def _build_highlight_selection_response(project_id: str, items: list[Dict[str, Any]], *, latest_artifact: Dict[str, Any] | None = None, source: str = "generated") -> HighlightSelectionResponse:
    selected_items = [x for x in items if x.get("selected")]
    return HighlightSelectionResponse(
        project_id=project_id,
        items=items,
        selected_count=len(selected_items),
        total_count=len(items),
        selected_duration_sec=round(sum(_safe_float(x.get("duration")) for x in selected_items), 3),
        latest_artifact=latest_artifact,
        source=source,
    )


def _load_highlight_selection_candidates(project: Mapping[str, Any], project_id: str) -> tuple[list[Dict[str, Any]], Dict[str, Any] | None, str]:
    latest_selection = artifact_repository.get_latest_project_artifact(project_id, "highlight_selection")
    saved_payload = artifact_repository.read_json_artifact_content(latest_selection, {})
    if isinstance(saved_payload, dict) and isinstance(saved_payload.get("items"), list):
        return _normalize_highlight_selection_items(saved_payload.get("items") or []), latest_selection, "saved"
    payloads = _load_latest_project_payloads(project, project_id)
    raw_candidates = payloads.get("highlights") or payloads.get("highlight_segments") or payloads.get("script_items") or []
    return _normalize_highlight_selection_items([x for x in raw_candidates if isinstance(x, Mapping)]), latest_selection, "generated"


def _require_project(user_email: str, project_id: str) -> Dict[str, Any]:
    item = project_repository.get_project(user_email, project_id)
    if not item:
        raise HTTPException(status_code=404, detail="project_not_found")
    return item


def _load_latest_project_payloads(project: Mapping[str, Any], project_id: str) -> Dict[str, Any]:
    latest_script = artifact_repository.get_latest_project_artifact(project_id, "script")
    latest_highlights = artifact_repository.get_latest_project_artifact(project_id, "highlights")
    latest_segments = artifact_repository.get_latest_project_artifact(project_id, "highlight_narration_segments")
    latest_audit = artifact_repository.get_latest_project_artifact(project_id, "audit")
    script_items = project.get("scriptItems") or artifact_repository.read_json_artifact_content(latest_script, []) or []
    highlights = artifact_repository.read_json_artifact_content(latest_highlights, []) or []
    highlight_segments = artifact_repository.read_json_artifact_content(latest_segments, []) or []
    audit = artifact_repository.read_json_artifact_content(latest_audit, {}) or {}
    if not isinstance(script_items, list): script_items = []
    if not isinstance(highlights, list): highlights = []
    if not isinstance(highlight_segments, list): highlight_segments = []
    if not isinstance(audit, dict): audit = {}
    if not highlights and highlight_segments:
        highlights = highlight_segments
    return {"script_items": script_items, "highlights": highlights, "audit": audit, "latest_artifacts": {"script": latest_script, "highlights": latest_highlights, "highlight_narration_segments": latest_segments, "audit": latest_audit}}


@router.get("/workbench", response_model=NarrationWorkbenchResponse)
def get_narration_workbench(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> NarrationWorkbenchResponse:
    project = _require_project(user.email, project_id)
    payloads = _load_latest_project_payloads(project, project_id)
    evidence_pack = build_evidence_pack(script_items=payloads["script_items"], highlights=payloads["highlights"], audit=payloads["audit"])
    script_segments = normalize_script_segments(payloads["script_items"])
    quality_report = build_quality_report(script_items=script_segments, evidence_pack=evidence_pack, highlights=payloads["highlights"], audit=payloads["audit"])
    timeline_blocks = build_timeline_blocks(script_segments, evidence_pack)
    return NarrationWorkbenchResponse(project_id=project_id, script_segments=script_segments, evidence_pack=evidence_pack, quality_report=quality_report, timeline_blocks=timeline_blocks, latest_artifacts=payloads["latest_artifacts"])


@router.post("/quality-report", response_model=NarrationQualityReportPayload)
def create_narration_quality_report(project_id: str, payload: NarrationQualityRequest, user: auth_store.StoredUser = Depends(require_user)) -> NarrationQualityReportPayload:
    project = _require_project(user.email, project_id)
    payloads = _load_latest_project_payloads(project, project_id)
    script_items = payload.script_items if payload.script_items is not None else payloads["script_items"]
    evidence_pack = payload.evidence_pack or build_evidence_pack(script_items=script_items, highlights=payloads["highlights"], audit=payloads["audit"])
    report = build_quality_report(script_items=script_items, evidence_pack=evidence_pack, highlights=payloads["highlights"], audit=payloads["audit"], speed=payload.speed)
    if payload.save_report:
        report["artifact"] = write_narration_artifact(owner_email=user.email, project_id=project_id, artifact_type="narration_quality_report", payload=report, label="解说质量评分报告")
    return NarrationQualityReportPayload(**report)


@router.post("/humanize", response_model=NarrationHumanizeResponse)
def humanize_narration(project_id: str, payload: NarrationHumanizeRequest, user: auth_store.StoredUser = Depends(require_user)) -> NarrationHumanizeResponse:
    _require_project(user.email, project_id)
    result = humanize_script_segments(payload.script_items, persona=payload.persona, intensity=payload.intensity)
    artifact = None
    if payload.save_version:
        artifact = write_narration_artifact(owner_email=user.email, project_id=project_id, artifact_type="script_version", payload={"kind": "humanized_script_version", "persona": result.get("persona"), "persona_label": result.get("persona_label"), "script_items": result.get("script_items") or [], "changes": result.get("changes") or [], "quality_report": result.get("quality_report") or {}}, label=f"真人口播优化 · {result.get('persona_label') or payload.persona}")
    return NarrationHumanizeResponse(**result, artifact=artifact)


@router.post("/scripts/versions", response_model=NarrationScriptVersionResponse)
def save_narration_script_version(project_id: str, payload: NarrationScriptVersionRequest, user: auth_store.StoredUser = Depends(require_user)) -> NarrationScriptVersionResponse:
    _require_project(user.email, project_id)
    report = payload.quality_report or build_quality_report(script_items=payload.script_items)
    artifact_payload = {"kind": "manual_script_version", "label": payload.label, "note": payload.note, "script_items": normalize_script_segments(payload.script_items), "quality_report": report}
    artifact = write_narration_artifact(owner_email=user.email, project_id=project_id, artifact_type="script_version", payload=artifact_payload, label=payload.label)
    return NarrationScriptVersionResponse(artifact=artifact, quality_report=report)


@router.get("/scripts/versions", response_model=NarrationScriptVersionListResponse)
def list_narration_script_versions(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> NarrationScriptVersionListResponse:
    _require_project(user.email, project_id)
    return NarrationScriptVersionListResponse(items=artifact_repository.list_project_artifacts(project_id, "script_version"))



@router.get("/highlights/selection", response_model=HighlightSelectionResponse)
def get_highlight_selection(project_id: str, user: auth_store.StoredUser = Depends(require_user)) -> HighlightSelectionResponse:
    project = _require_project(user.email, project_id)
    items, latest_artifact, source = _load_highlight_selection_candidates(project, project_id)
    return _build_highlight_selection_response(project_id, items, latest_artifact=latest_artifact, source=source)


@router.post("/highlights/selection", response_model=HighlightSelectionSaveResponse)
def save_highlight_selection(project_id: str, payload: HighlightSelectionSaveRequest, user: auth_store.StoredUser = Depends(require_user)) -> HighlightSelectionSaveResponse:
    project = _require_project(user.email, project_id)
    incoming = payload.items
    if not incoming:
        incoming, _, _ = _load_highlight_selection_candidates(project, project_id)
    items = _normalize_highlight_selection_items([x for x in incoming if isinstance(x, Mapping)])
    selection = _build_highlight_selection_response(project_id, items, source="saved")
    artifact_payload = {
        "kind": "highlight_selection",
        "project_id": project_id,
        "note": payload.note,
        "items": items,
        "selected_count": selection.selected_count,
        "total_count": selection.total_count,
        "selected_duration_sec": selection.selected_duration_sec,
    }
    artifact = write_narration_artifact(
        owner_email=user.email,
        project_id=project_id,
        artifact_type="highlight_selection",
        payload=artifact_payload,
        label="高光复选结果",
    )
    saved_selection = _build_highlight_selection_response(project_id, items, latest_artifact=artifact, source="saved")
    return HighlightSelectionSaveResponse(project_id=project_id, artifact=artifact, selection=saved_selection)
