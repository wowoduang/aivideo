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
    except Exception as _e:
        logger.debug("配置读取失败，返回 default: {}", _e)
    return default

def _import_callable(path: str) -> Callable[..., Any]:
    module_name, func_name = path.split(":", 1)
    module = importlib.import_module(module_name); func = getattr(module, func_name)
    if not callable(func): raise TypeError(f"{path} is not callable")
    return func

"""Adapter for the project's existing video composition pipeline. Does not replace it."""

def _resolve_callable(options: Optional[Mapping[str, Any]]) -> str:
    opts = dict(options or {})
    return str(opts.get("video_compose_callable") or os.environ.get("MOVIE_STORY_VIDEO_COMPOSE_CALLABLE") or _read_project_config("movie_story_video_compose_callable", "") or "")

def compose_commentary_video(input_video: str | Path, selected_highlights: Sequence[Mapping[str, Any]], narration_script: Mapping[str, Any], tts_manifest: Mapping[str, Any], output_dir: str | Path, *, options: Optional[Mapping[str, Any]] = None) -> Record:
    out = Path(output_dir) / "08_video"; out.mkdir(parents=True, exist_ok=True)
    options_dict = dict(options or {}); callable_path = _resolve_callable(options_dict)
    manifest: Record = {"stage":"08_video_compose", "created_at":time.strftime("%Y-%m-%d %H:%M:%S"), "policy":"adapter_to_existing_video_compose_pipeline", "callable":callable_path, "status":"pending_existing_video_compose_callable_not_configured", "input_video":str(input_video), "selected_highlight_count":len(selected_highlights), "narration_line_count":len(narration_script.get("lines") or []), "tts_status":tts_manifest.get("status"), "final_video":None, "errors":[]}
    if callable_path:
        try:
            result = _import_callable(callable_path)(input_video=str(input_video), selected_highlights=list(selected_highlights), narration_script=dict(narration_script), tts_manifest=dict(tts_manifest), output_dir=str(out), options=options_dict)
            if isinstance(result, Mapping): manifest.update(dict(result))
            else: manifest["result"] = result
            if manifest.get("status", "").startswith("pending"): manifest["status"] = "ok"
            manifest.setdefault("status", "ok")
        except Exception as exc:
            manifest["status"] = "error"; manifest["errors"].append(f"{type(exc).__name__}: {exc}")
    path = out / "08_video_compose_manifest.json"; manifest["manifest_path"] = str(path); path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest

__all__ = ["compose_commentary_video"]
