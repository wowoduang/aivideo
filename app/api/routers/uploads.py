from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from app.api.deps import assert_rate_limit, require_user
from app.services import auth_store, file_signing, usage_meter
from app.utils import utils

router = APIRouter(prefix="/uploads", tags=["uploads"])


MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("AIVIDEO_MAX_VIDEO_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
MAX_SUBTITLE_UPLOAD_BYTES = int(os.getenv("AIVIDEO_MAX_SUBTITLE_UPLOAD_BYTES", str(20 * 1024 * 1024)))
_UPLOAD_CHUNK_BYTES = 1024 * 1024


class CropVideoRequest(BaseModel):
    path: str
    start_sec: float
    end_sec: float


def _ffmpeg_trim_video(source: Path, target: Path, start_sec: float, end_sec: float) -> None:
    duration = max(0.1, end_sec - start_sec)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_sec:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(target),
    ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0 or not target.exists():
        detail = completed.stderr.strip() or "ffmpeg_trim_failed"
        raise HTTPException(status_code=500, detail=detail)


def _workspace_relative_url(kind: str, filename: str) -> str:
    return f"/uploads/{kind}/{filename}"


def _signed_upload_url(kind: str, filename: str, path: Path, user_email: str) -> str:
    base = _workspace_relative_url(kind, filename)
    signed = file_signing.sign_path(scope=f"upload:{kind}", path=str(path), user_email=user_email)
    return (
        f"{base}?signed_user={user_email}"
        f"&expires={signed['expires']}"
        f"&signature={signed['signature']}"
    )


def _safe_name(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "file")
    return cleaned or "file"


def _upload_root(kind: str) -> Path:
    root = Path(utils.workspace_dir()) / "frontend_uploads" / kind
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _save_upload(kind: str, file: UploadFile, *, max_bytes: int, owner_email: str = "") -> dict:
    filename = _safe_name(file.filename or f"{kind}.bin")
    unique_filename = f"{uuid4().hex}_{filename}"
    target = _upload_root(kind) / unique_filename
    size = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="upload_too_large")
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    usage_meter.record_event(
        owner=owner_email,
        event_type="upload",
        provider="local",
        units=size,
        unit_name="bytes",
        metadata={"kind": kind, "filename": filename},
    )
    return {
        "path": str(target),
        "filename": filename,
        "size": size,
        "kind": kind,
        "url": _signed_upload_url(kind, unique_filename, target, owner_email) if owner_email else f"/uploads/{kind}/{unique_filename}",
        "raw_url": f"/uploads/{kind}/{unique_filename}",
    }


@router.post("/video")
async def upload_video(file: UploadFile = File(...), user: auth_store.StoredUser = Depends(require_user)):
    assert_rate_limit(user.email, "uploads:video", limit=20, window_seconds=60)
    if not str(file.content_type or "").startswith("video/"):
        raise HTTPException(status_code=400, detail="invalid_video_file")
    _ = user
    return await _save_upload("video", file, max_bytes=MAX_VIDEO_UPLOAD_BYTES, owner_email=user.email)


@router.post("/subtitle")
async def upload_subtitle(file: UploadFile = File(...), user: auth_store.StoredUser = Depends(require_user)):
    assert_rate_limit(user.email, "uploads:subtitle", limit=60, window_seconds=60)
    filename = str(file.filename or "").lower()
    if not filename.endswith((".srt", ".vtt", ".txt")):
        raise HTTPException(status_code=400, detail="invalid_subtitle_file")
    _ = user
    return await _save_upload("subtitle", file, max_bytes=MAX_SUBTITLE_UPLOAD_BYTES, owner_email=user.email)


def _parse_srt_timestamp(value: str) -> str:
    return value.replace(",", ".").strip()


def _resolve_uploaded_file(kind: str, raw_path: str) -> Path:
    root = _upload_root(kind).resolve()
    candidate = Path(raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="path_outside_upload_root") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"{kind}_not_found")
    return candidate


@router.get("/subtitle-content")
def subtitle_content(path: str = Query(...), user: auth_store.StoredUser = Depends(require_user)):
    _ = user
    subtitle_path = _resolve_uploaded_file("subtitle", path)

    text = subtitle_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []

    blocks = re.split(r"\n\s*\n+", text)
    lines = []
    for index, block in enumerate(blocks, start=1):
        raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(raw_lines) < 2:
            continue
        time_line = raw_lines[1] if "-->" in raw_lines[1] else raw_lines[0]
        text_lines = raw_lines[2:] if "-->" in raw_lines[1] else raw_lines[1:]
        match = re.search(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", time_line)
        start = _parse_srt_timestamp(match.group(1)) if match else f"{(index - 1) * 5}.0s"
        end = _parse_srt_timestamp(match.group(2)) if match else f"{index * 5}.0s"
        lines.append({
            "id": index,
            "start": start,
            "end": end,
            "text": " ".join(text_lines).strip() or f"字幕 {index}",
        })
    return lines


@router.post("/video/crop")
def crop_video(request: CropVideoRequest, user: auth_store.StoredUser = Depends(require_user)):
    _ = user
    source = _resolve_uploaded_file("video", request.path)
    upload_root = _upload_root("video")

    start_sec = max(0.0, float(request.start_sec or 0.0))
    end_sec = max(start_sec + 0.1, float(request.end_sec or 0.0))

    target_name = f"{uuid4().hex}_cropped_{source.name}"
    target = upload_root / target_name
    _ffmpeg_trim_video(source, target, start_sec, end_sec)
    size = target.stat().st_size if target.exists() else 0
    usage_meter.record_event(
        owner=user.email,
        event_type="video_crop",
        provider="ffmpeg",
        units=size,
        unit_name="bytes",
        metadata={"source": str(source), "target": str(target)},
    )
    return {
        "path": str(target),
        "filename": target.name,
        "size": size,
        "kind": "video",
        "url": _signed_upload_url("video", target_name, target, user.email),
        "raw_url": _workspace_relative_url("video", target_name),
    }
