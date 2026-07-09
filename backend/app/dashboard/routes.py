"""
Dashboard routes: health (public), stats/profile/activity (protected).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.dashboard import service
from app.database.postgres import get_db
from app.models.database_models import UserProfile
from app.models.schemas import ActivityLogOut, APIResponse, UserProfileOut
from app.utils.response import success_response

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/health", response_model=APIResponse)
def health():
    data = service.get_health()
    return success_response(message="Backend status", data=data)


@router.get("/stats", response_model=APIResponse)
def stats(current_user: UserProfile = Depends(get_current_user)):
    data = service.get_placeholder_stats()
    return success_response(message="Dashboard stats (placeholder)", data=data.model_dump())


@router.get("/profile", response_model=APIResponse)
def profile(current_user: UserProfile = Depends(get_current_user)):
    data = UserProfileOut.model_validate(current_user)
    return success_response(message="Current user profile", data=data.model_dump(mode="json"))


@router.get("/activity", response_model=APIResponse)
def activity(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    logs = service.get_recent_activity(db, current_user)
    data = [ActivityLogOut.model_validate(log).model_dump(mode="json") for log in logs]
    return success_response(message="Recent activity logs", data=data)
