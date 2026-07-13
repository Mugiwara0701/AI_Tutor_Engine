"""
Pydantic schemas for request validation and response serialization.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- Auth ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None


# ---------- User Profile ----------

class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: Optional[str] = None
    email: str
    role: str
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginResponse(BaseModel):
    session: TokenResponse
    user: UserProfileOut


class RegisterResponse(BaseModel):
    user: UserProfileOut
    message: str = "Registration successful"


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ---------- Activity Logs ----------

class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    description: Optional[str] = None
    log_metadata: Optional[dict[str, Any]] = None
    created_at: datetime


# ---------- Dashboard ----------

class DashboardStats(BaseModel):
    total_files: int = 0
    total_pipelines: int = 0
    completed_pipelines: int = 0
    failed_pipelines: int = 0


class HealthResponse(BaseModel):
    status: str
    database: bool


# ---------- Generic API envelope ----------

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
