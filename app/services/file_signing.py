from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path
from typing import Optional

from app.utils import workspace

_DEFAULT_TTL_SECONDS = 15 * 60


def _secret() -> bytes:
    configured = str(os.getenv("AIVIDEO_FILE_SIGNING_SECRET", "") or "").strip()
    if configured:
        return configured.encode("utf-8")
    secret_path = Path(workspace.state_dir("security", create=True)) / "file_signing_secret"
    if secret_path.exists():
        value = secret_path.read_text(encoding="utf-8", errors="ignore").strip()
        if value:
            return value.encode("utf-8")
    token = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    secret_path.write_text(token, encoding="utf-8")
    try:
        secret_path.chmod(0o600)
    except OSError:
        pass  # IO/队列清理，忽略异常
    return token.encode("utf-8")


def _normalize_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _payload(*, scope: str, path: str, user_email: str, expires_at: int) -> str:
    return "\n".join([
        str(scope or "file"),
        _normalize_path(path),
        str(user_email or "").strip().lower(),
        str(int(expires_at)),
    ])


def sign_path(*, scope: str, path: str, user_email: str, ttl_seconds: Optional[int] = None) -> dict[str, str | int]:
    ttl = int(ttl_seconds or int(os.getenv("AIVIDEO_SIGNED_FILE_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))))
    expires_at = int(time.time()) + max(30, ttl)
    payload = _payload(scope=scope, path=path, user_email=user_email, expires_at=expires_at)
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return {"scope": str(scope or "file"), "expires": expires_at, "signature": _b64(digest)}


def verify_path_signature(*, scope: str, path: str, user_email: str, expires: str | int | None, signature: str | None) -> bool:
    try:
        expires_at = int(str(expires or "0"))
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    payload = _payload(scope=scope, path=path, user_email=user_email, expires_at=expires_at)
    digest = _b64(hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest())
    return hmac.compare_digest(digest, str(signature or ""))


def record_signed_file_access(*, user_email: str, scope: str, path: str, bytes_count: int = 0) -> None:
    try:
        from app.services import usage_meter
        usage_meter.record_event(
            owner=user_email,
            event_type="file_access",
            provider="local",
            units=max(0, int(bytes_count or 0)),
            unit_name="bytes",
            metadata={"scope": scope, "path": path},
        )
    except Exception:
        return
