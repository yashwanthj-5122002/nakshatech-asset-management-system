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
from app.core.roles import EMPLOYEE_ROLE, VALID_ROLES, role_is_allowed
from app.modules.employee_portal.models import UserSession

security = HTTPBearer()

# The only role a bearer token is permitted to assert: signing in with
# ``access_mode="employee_support"`` deliberately mints a lower-privilege token.
EMPLOYEE_DOWNGRADE_CLAIM = EMPLOYEE_ROLE


@dataclass
class CurrentAuth:
    user: User
    claims: dict[str, Any]
    session: UserSession | None

    @property
    def effective_role(self) -> str:
        """Role actually in force for this request.

        The database row is authoritative. The JWT ``role`` claim is only ever
        honoured as a *downgrade*, because that is the single thing a token can
        legitimately carry: signing in with ``access_mode="employee_support"``
        mints ``role="employee"`` for a management account.

        Trusting the claim in both directions was an authorization bypass: the
        token lives 8 hours, so a role revoked in the database stayed effective
        until expiry, and any forged or stale elevated claim passed every
        ``require_roles`` gate. Reading the role from the row (which
        ``resolve_access_token`` already loads on each request) closes that.
        """
        db_role = (self.user.role or "").strip().lower()
        claimed_role = str(self.claims.get("role") or "").strip().lower()
        if claimed_role == EMPLOYEE_DOWNGRADE_CLAIM and db_role and db_role != EMPLOYEE_DOWNGRADE_CLAIM:
            return EMPLOYEE_DOWNGRADE_CLAIM
        return db_role or claimed_role


def resolve_access_token(
    db: Session,
    token: str,
) -> tuple[User, dict[str, Any], UserSession | None]:
    """Validate a bearer access token and return its user, claims and session.

    Shared by the HTTP dependency and the WebSocket handshake, which cannot use
    ``Depends(HTTPBearer())`` but must enforce exactly the same checks.
    """
    try:
        payload = decode_access_token(token)
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
    return user, payload, session


def get_current_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentAuth:
    user, payload, session = resolve_access_token(db, credentials.credentials)
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
