from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UnifiedEditResult:
    """Stable internal result shape shared by movie-story and highlight entries."""

    success: bool
    entry: str
    mode: str
    payload: Dict[str, Any] = field(default_factory=dict)
    script_items: List[Dict[str, Any]] = field(default_factory=list)
    composition_plan: Optional[Dict[str, Any]] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error: str = ""

    @classmethod
    def from_payload(cls, *, entry: str, mode: str, payload: Dict[str, Any]) -> "UnifiedEditResult":
        script_items = payload.get("script_items") if isinstance(payload, dict) else []
        composition_plan = payload.get("composition_plan") if isinstance(payload, dict) else None
        warnings = payload.get("warnings") if isinstance(payload, dict) else []
        artifacts: Dict[str, Any] = {}
        if isinstance(payload, dict):
            for key in [
                "script_path",
                "composition_plan_path",
                "highlights_path",
                "highlight_script_path",
                "audit_path",
                "output_paths",
            ]:
                if payload.get(key):
                    artifacts[key] = payload.get(key)
        return cls(
            success=bool(payload.get("success", False)) if isinstance(payload, dict) else False,
            entry=entry,
            mode=mode,
            payload=dict(payload or {}),
            script_items=list(script_items or []) if isinstance(script_items, list) else [],
            composition_plan=dict(composition_plan or {}) if isinstance(composition_plan, dict) else None,
            artifacts=artifacts,
            warnings=list(warnings or []) if isinstance(warnings, list) else [],
            error=str(payload.get("error", "") or "") if isinstance(payload, dict) else "invalid_payload",
        )

    def to_payload(self) -> Dict[str, Any]:
        result = dict(self.payload or {})
        result.setdefault("success", self.success)
        result.setdefault("script_items", self.script_items)
        if self.composition_plan is not None:
            result.setdefault("composition_plan", self.composition_plan)
        result.setdefault("warnings", self.warnings)
        result.setdefault("error", self.error)
        result["unified_entry"] = self.entry
        result["unified_mode"] = self.mode
        result["unified_artifacts"] = self.artifacts
        return result
