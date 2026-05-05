# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
import importlib, json, os, time
Record = Dict[str, Any]

def _read_project_config(key: str, default: Any = "") -> Any:
    try:
        from app.config import config as app_config  # type: ignore
        app = getattr(app_config, "app", None)
        if isinstance(app, dict) and key in app: return app.get(key, default)
        if app is not None and hasattr(app, key): return getattr(app, key)
        if isinstance(app_config, dict):
            if key in app_config: return app_config.get(key, default)
            if isinstance(app_config.get("app"), dict): return app_config["app"].get(key, default)
    except Exception: pass
    return default

def _import_callable(path: str) -> Callable[..., Any]:
    module_name, func_name = path.split(":", 1)
    module = importlib.import_module(module_name); func = getattr(module, func_name)
    if not callable(func): raise TypeError(f"{path} is not callable")
    return func

"""Adapter for the project's existing TTS pipeline. Does not implement a new TTS engine."""

def _resolve_callable(options: Optional[Mapping[str, Any]]) -> str:
    opts = dict(options or {})
    return str(opts.get("tts_callable") or os.environ.get("MOVIE_STORY_TTS_CALLABLE") or _read_project_config("movie_story_tts_callable", "") or "")

def synthesize_narration(script: Mapping[str, Any], output_dir: str | Path, *, options: Optional[Mapping[str, Any]] = None) -> Record:
    out = Path(output_dir) / "07_tts"; out.mkdir(parents=True, exist_ok=True)
    options_dict = dict(options or {}); callable_path = _resolve_callable(options_dict)
    manifest: Record = {"stage":"07_tts", "created_at":time.strftime("%Y-%m-%d %H:%M:%S"), "policy":"adapter_to_existing_tts_pipeline", "callable":callable_path, "status":"pending_existing_tts_callable_not_configured", "line_count":len(script.get("lines") or []), "audio_files":[], "full_audio":None, "errors":[]}
    if callable_path:
        try:
            result = _import_callable(callable_path)(script=script, output_dir=str(out), options=options_dict)
            if isinstance(result, Mapping): manifest.update(dict(result))
            else: manifest["result"] = result
            if manifest.get("status", "").startswith("pending"): manifest["status"] = "ok"
            manifest.setdefault("status", "ok")
        except Exception as exc:
            manifest["status"] = "error"; manifest["errors"].append(f"{type(exc).__name__}: {exc}")
    path = out / "07_tts_manifest.json"; manifest["manifest_path"] = str(path); path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest

__all__ = ["synthesize_narration"]
