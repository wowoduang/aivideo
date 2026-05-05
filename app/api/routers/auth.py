from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas.auth import (
    AuthResponse,
    AuthStatusResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    JobHistoryResponse,
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UserInfo,
)
from app.services import auth_store, job_history

router = APIRouter(tags=["auth"])


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _user_info(user: auth_store.StoredUser) -> UserInfo:
    return UserInfo(name=user.name, email=user.email, created_at=user.created_at)


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing_token")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid_token")
    return authorization.split(" ", 1)[1].strip()


def _require_user(authorization: Optional[str]) -> tuple[str, auth_store.StoredUser]:
    token = _extract_token(authorization)
    user = auth_store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_token")
    auth_store.touch_session(token, _now_iso())
    return token, user


def _validate_email(value: str) -> None:
    if "@" not in value or "." not in value:
        raise HTTPException(status_code=400, detail="invalid_email")


def _auth_status_payload() -> AuthStatusResponse:
    count = auth_store.user_count()
    bootstrap_enabled = str(__import__("os").getenv("AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN", "1")).strip().lower() not in {"0", "false", "no"}
    bootstrap_email = None
    bootstrap_password = None
    if count == 0 and bootstrap_enabled:
        bootstrap_email = str(__import__("os").getenv("AIVIDEO_BOOTSTRAP_EMAIL", "demo@aivideo.local") or "demo@aivideo.local").strip().lower()
        bootstrap_password = str(__import__("os").getenv("AIVIDEO_BOOTSTRAP_PASSWORD", "12345678") or "12345678")
    return AuthStatusResponse(
        has_users=count > 0,
        user_count=count,
        bootstrap_enabled=bootstrap_enabled,
        bootstrap_email=bootstrap_email,
        bootstrap_password=bootstrap_password,
    )




@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status() -> AuthStatusResponse:
    return _auth_status_payload()


@router.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest) -> AuthResponse:
    _validate_email(payload.email)
    created_at = _now_iso()
    try:
        user = auth_store.register_user(payload.name, payload.email, payload.password, created_at)
    except ValueError as exc:
        if str(exc) == "email_exists":
            raise HTTPException(status_code=409, detail="email_exists") from exc
        raise
    token = auth_store.create_session(user.email, created_at)
    return AuthResponse(token=token, user=_user_info(user))


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    _validate_email(payload.email)
    if auth_store.user_count() == 0:
        auth_store.ensure_bootstrap_user(_now_iso())
    user = auth_store.authenticate(payload.email, payload.password)
    if not user:
        detail = "no_users_registered" if auth_store.user_count() == 0 else "invalid_credentials"
        raise HTTPException(status_code=401, detail=detail)
    created_at = _now_iso()
    token = auth_store.create_session(user.email, created_at)
    return AuthResponse(token=token, user=_user_info(user))


@router.get("/auth/me", response_model=MeResponse)
def me(authorization: Optional[str] = Header(default=None)) -> MeResponse:
    _token, user = _require_user(authorization)
    return MeResponse(user=_user_info(user))


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(authorization: Optional[str] = Header(default=None)) -> LogoutResponse:
    auth_store.revoke_token(_extract_token(authorization))
    return LogoutResponse(success=True)


@router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
    _validate_email(payload.email)
    record = auth_store.issue_password_reset(payload.email, _now_iso())
    if not record:
        return ForgotPasswordResponse(success=True, message="如果该邮箱已注册，系统已生成密码重置方式。")
    return ForgotPasswordResponse(
        success=True,
        message="已生成本地重置链接。由于当前是本地模式，请直接打开返回的链接完成重置。",
        reset_token=record.token,
        reset_url=f"/reset-password?token={record.token}",
        expires_at=record.expires_at,
    )


@router.post("/auth/reset-password", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    user = auth_store.consume_password_reset(payload.token, payload.password)
    if not user:
        raise HTTPException(status_code=400, detail="invalid_or_expired_reset_token")
    return ResetPasswordResponse(success=True, message="密码已重置，请使用新密码重新登录。")


@router.post("/auth/change-password", response_model=ChangePasswordResponse)
def change_password(payload: ChangePasswordRequest, authorization: Optional[str] = Header(default=None)) -> ChangePasswordResponse:
    token, user = _require_user(authorization)
    try:
        auth_store.change_password(user.email, payload.current_password, payload.new_password)
    except ValueError as exc:
        if str(exc) == "invalid_credentials":
            raise HTTPException(status_code=400, detail="invalid_current_password") from exc
        raise
    auth_store.revoke_token(token)
    return ChangePasswordResponse(success=True, message="密码已更新，请重新登录。")


@router.get("/auth/jobs", response_model=JobHistoryResponse)
def list_jobs(authorization: Optional[str] = Header(default=None)) -> JobHistoryResponse:
    _token, user = _require_user(authorization)
    return JobHistoryResponse(items=job_history.list_jobs(user.email))
