"""
Dashboard business logic. For now this only covers placeholder stats and
reading the current user's own activity logs — pipeline and OneDrive
integrations are intentionally out of scope for this phase.
"""

from sqlalchemy.orm import Session

from app.database.postgres import check_connection
from app.models.database_models import DashboardActivityLog, UserProfile
from app.models.schemas import DashboardStats


def get_health() -> dict:
    db_ok = check_connection()
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}


def get_placeholder_stats() -> DashboardStats:
    # OneDrive + pipeline integrations come later. Placeholder values only.
    return DashboardStats()


def get_recent_activity(db: Session, user: UserProfile, limit: int = 20) -> list[DashboardActivityLog]:
    return (
        db.query(DashboardActivityLog)
        .filter(DashboardActivityLog.user_id == user.id)
        .order_by(DashboardActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )
