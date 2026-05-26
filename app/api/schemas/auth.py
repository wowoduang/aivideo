from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=128)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class UserInfo(BaseModel):
    name: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserInfo


class MeResponse(BaseModel):
    user: UserInfo


class LogoutResponse(BaseModel):
    success: bool


class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str
    reset_token: Optional[str] = None
    reset_url: Optional[str] = None
    expires_at: Optional[str] = None


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


class JobHistoryItem(BaseModel):
    task_id: str
    project_id: Optional[str] = None
    job_type: str
    status: str
    progress: int
    message: str
    error: str
    task_dir: str
    created_at: str
    updated_at: str


class JobHistoryResponse(BaseModel):
    items: list[JobHistoryItem]


class AuthStatusResponse(BaseModel):
    has_users: bool
    user_count: int
    bootstrap_enabled: bool
    bootstrap_email: Optional[str] = None
    bootstrap_password: Optional[str] = None
