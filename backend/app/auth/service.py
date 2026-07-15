"""
Auth business logic. Fully self-managed: no Supabase Auth involved.

- Passwords are hashed with bcrypt and stored in user_profiles.hashed_password.
- Access tokens are our own JWTs, signed with JWT_SECRET.
- user_profiles is the single source of truth for identity.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.models.database_models import DashboardActivityLog, DashboardSession, UserProfile
from app.models.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, UpdateUserRequest
from app.utils.logger import logger


def register_user(db: Session, payload: RegisterRequest) -> UserProfile:
    existing = db.query(UserProfile).filter(UserProfile.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    profile = UserProfile(
        id=uuid.uuid4(),
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="user",
        is_active=True,
    )
    db.add(profile)
    db.flush()  # get profile.id before committing

    db.add(
        DashboardActivityLog(
            id=uuid.uuid4(),
            user_id=profile.id,
            action="register",
            description="User registered",
        )
    )
    db.commit()
    db.refresh(profile)

    return profile


def login_user(
    db: Session,
    payload: LoginRequest,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[dict, UserProfile]:
    profile = db.query(UserProfile).filter(UserProfile.email == payload.email).first()

    if profile is None or not verify_password(payload.password, profile.hashed_password):
        logger.warning(f"Login failed for {payload.email}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not profile.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")

    # Create the session first so its id can be embedded in the JWT ("sid"
    # claim). That's what lets /auth/logout actually revoke the token later —
    # get_current_user checks this session's is_active flag on every request.
    dash_session = DashboardSession(
        id=uuid.uuid4(),
        user_id=profile.id,
        login_time=datetime.now(timezone.utc),
        ip_address=ip_address,
        user_agent=user_agent,
        is_active=True,
    )
    db.add(dash_session)
    db.flush()  # assign dash_session.id without committing yet

    access_token, expires_in = create_access_token(
        subject=str(profile.id),
        extra_claims={"email": profile.email, "role": profile.role, "sid": str(dash_session.id)},
    )

    db.add(
        DashboardActivityLog(
            id=uuid.uuid4(),
            user_id=profile.id,
            action="login",
            description="User logged in",
        )
    )
    db.commit()
    db.refresh(profile)

    token_data = {
        "access_token": access_token,
        "refresh_token": None,
        "token_type": "bearer",
        "expires_in": expires_in,
    }

    return token_data, profile


def logout_user(db: Session, profile: UserProfile) -> None:
    active_session = (
        db.query(DashboardSession)
        .filter(DashboardSession.user_id == profile.id, DashboardSession.is_active == True)  # noqa: E712
        .order_by(DashboardSession.login_time.desc())
        .first()
    )
    if active_session:
        active_session.is_active = False
        active_session.logout_time = datetime.now(timezone.utc)

    db.add(
        DashboardActivityLog(
            id=uuid.uuid4(),
            user_id=profile.id,
            action="logout",
            description="User logged out",
        )
    )
    db.commit()


def change_password(db: Session, profile: UserProfile, payload: ChangePasswordRequest) -> None:
    """
    Lets a user change their own password. Requires the current password
    for verification — this is not an admin action and never touches
    anyone else's account (profile is always the caller's own, from
    get_current_user).

    All of the user's active sessions are revoked afterward (including the
    one making this request), since every JWT they were issued was signed
    off the old credentials. They'll need to log in again with the new
    password — this mirrors how logout already revokes access via the
    "sid" session check in get_current_user.
    """
    if not verify_password(payload.current_password, profile.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    profile.hashed_password = hash_password(payload.new_password)

    db.query(DashboardSession).filter(
        DashboardSession.user_id == profile.id,
        DashboardSession.is_active == True,  # noqa: E712
    ).update({"is_active": False, "logout_time": datetime.now(timezone.utc)})

    db.add(
        DashboardActivityLog(
            id=uuid.uuid4(),
            user_id=profile.id,
            action="change_password",
            description="User changed their own password",
        )
    )
    db.commit()


def list_users(
    db: Session, current_user: UserProfile, include_inactive: bool = False
) -> list[UserProfile]:
    """
    Returns employee/user records, scoped to what the requesting user is
    allowed to see in Settings > Employee / User Management:

      - admin:   everyone (admins, managers, users)
      - manager: other managers and users, but NOT admins
      - user:    nobody else - just their own record

    By default only active employees are returned (is_active = true), which
    is what the "normal" employee list in the frontend uses. Pass
    include_inactive=True to also include soft-deleted/deactivated accounts
    (e.g. for the admin-only "show inactive" view).

    is_active is defined NOT NULL with a server default of true, so NULL
    shouldn't occur for rows created through this app. As a defensive
    measure against any pre-existing/legacy row where it's NULL anyway, we
    treat NULL the same as true here so an employee can never silently
    disappear from the active list due to an unset flag.
    """
    query = db.query(UserProfile)
    if not include_inactive:
        query = query.filter(
            (UserProfile.is_active == True) | (UserProfile.is_active.is_(None))  # noqa: E712
        )

    role = (current_user.role or "").strip().lower()
    if role == "admin":
        pass  # no additional restriction
    elif role == "manager":
        query = query.filter(UserProfile.role.in_(["manager", "user"]))
    else:
        # Plain "user" role: can't browse other employees at all.
        query = query.filter(UserProfile.id == current_user.id)

    return query.order_by(UserProfile.created_at.desc()).all()


def update_user(db: Session, user_id: uuid.UUID, payload: UpdateUserRequest) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.full_name is not None:
        profile.full_name = payload.full_name
    if payload.role is not None:
        profile.role = payload.role.strip().lower()
    if payload.is_active is not None:
        profile.is_active = payload.is_active

    db.commit()
    db.refresh(profile)
    return profile


def delete_user(db: Session, user_id: uuid.UUID) -> None:
    """
    Soft-deletes an employee/user.

    Per product requirements, employee records must never be permanently
    removed from the database. "Deleting" an employee sets is_active=False
    so the record is excluded from the normal (active-only) employee list
    while remaining intact in the database.
    """
    profile = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    profile.is_active = False

    db.add(
        DashboardActivityLog(
            id=uuid.uuid4(),
            user_id=profile.id,
            action="deactivate",
            description="User soft-deleted (is_active set to false)",
        )
    )
    db.commit()