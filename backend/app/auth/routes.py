"""
Authentication routes: /auth/register, /auth/login, /auth/logout, /auth/me,
/auth/users (list/update/delete)
"""
from fastapi import APIRouter, Depends, Query, Request
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.database.postgres import get_db
from app.models.database_models import UserProfile
from app.models.schemas import (
    APIResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdateUserRequest,
    UserProfileOut,
)
from app.utils.response import success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=APIResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    profile = service.register_user(db, payload)
    data = RegisterResponse(user=UserProfileOut.model_validate(profile))
    return success_response(message="Registration successful", data=data.model_dump(mode="json"), status_code=201)


@router.post("/login", response_model=APIResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    token_data, profile = service.login_user(db, payload, ip_address=ip_address, user_agent=user_agent)

    data = LoginResponse(
        session=TokenResponse(**token_data),
        user=UserProfileOut.model_validate(profile),
    )
    return success_response(message="Login successful", data=data.model_dump(mode="json"))


@router.post("/logout", response_model=APIResponse)
def logout(db: Session = Depends(get_db), current_user: UserProfile = Depends(get_current_user)):
    service.logout_user(db, current_user)
    return success_response(message="Logout successful")


@router.get("/me", response_model=APIResponse)
def me(current_user: UserProfile = Depends(get_current_user)):
    data = UserProfileOut.model_validate(current_user)
    return success_response(message="Current user fetched", data=data.model_dump(mode="json"))


@router.get("/users", response_model=APIResponse)
def list_users(
    include_inactive: bool = Query(
        default=False,
        description="If true, also include soft-deleted/deactivated (is_active=false) employees.",
    ),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    users = service.list_users(db, include_inactive=include_inactive)
    data = [UserProfileOut.model_validate(user).model_dump(mode="json") for user in users]
    return success_response(message="Users fetched", data=data)


@router.patch("/users/{user_id}", response_model=APIResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    profile = service.update_user(db, user_id, payload)
    data = UserProfileOut.model_validate(profile)
    return success_response(message="User updated", data=data.model_dump(mode="json"))


@router.delete("/users/{user_id}", response_model=APIResponse)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    service.delete_user(db, user_id)
    return success_response(message="User deactivated")