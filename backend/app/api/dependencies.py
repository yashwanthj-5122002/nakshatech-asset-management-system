from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.entities import User
from app.core.roles import VALID_ROLES, role_is_allowed
from app.modules.employee_portal.models import UserSession

security = HTTPBearer()


@dataclass
class CurrentAuth:
    user: User
    claims: dict[str, Any]
    session: UserSession | None

    @property
    def effective_role(self) -> str:
        claimed_role = str(self.claims.get("role") or "").strip().lower()
        return claimed_role if claimed_role in VALID_ROLES else self.user.role


def get_current_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentAuth:
    try:
        payload = decode_access_token(credentials.credentials)
        email = payload.get("sub")
        token_type = payload.get("type")
        if token_type not in (None, "access"):
            raise jwt.InvalidTokenError("Not an access token")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    user = db.scalar(select(User).where(func.lower(User.email) == str(email or "").lower()))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")
    if int(payload.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This session is no longer valid")

    session = None
    session_id = payload.get("sid")
    if session_id is not None:
        try:
            session = db.get(UserSession, int(session_id))
        except (TypeError, ValueError):
            session = None
        if not session or session.user_id != user.id or session.ended_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This session has ended")
    return CurrentAuth(user=user, claims=payload, session=session)


def get_current_user(auth: CurrentAuth = Depends(get_current_auth)) -> User:
    return auth.user


def require_roles(*roles: str):
    allowed = set(roles)

    def checker(auth: CurrentAuth = Depends(get_current_auth)) -> User:
        if not role_is_allowed(auth.effective_role, allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission")
        return auth.user

    return checker
