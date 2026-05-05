"""Engine execution result helpers for the movie_story unified layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, MutableMapping


@dataclass(frozen=True)
class EngineBackendInfo:
    """Structured metadata about which engine backend handled a request."""

    engine_kind: str
    requested_backend: str
    selected_backend: str
    fallback_backend: str
    native_ready: bool
    reason: str
    compatibility_engine: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def attach_engine_backend_info(payload: MutableMapping[str, Any] | None, info: EngineBackendInfo) -> Dict[str, Any]:
    """Attach backend metadata to a normal pipeline payload.

    Legacy engines return plain dictionaries. This helper keeps the
    compatibility boundary tolerant while making the selected backend visible
    to callers, logs, tests, and audits.
    """

    result = dict(payload or {})
    result["engine_backend"] = info.selected_backend
    result["engine_backend_info"] = info.as_dict()

    warnings = result.setdefault("warnings", [])
    if info.requested_backend != info.selected_backend and isinstance(warnings, list):
        warnings.append(
            f"engine backend '{info.requested_backend}' resolved to "
            f"'{info.selected_backend}': {info.reason}"
        )

    return result


__all__ = [
    "EngineBackendInfo",
    "attach_engine_backend_info",
]
