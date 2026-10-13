"""Capability check for notification settings management.

SECURITY NOTE
-------------
Authorization is based on the STABLE seeded account identity already defined in
``app.core.management_access`` (``vinod@nakshatech.com`` / ``chethan@nakshatech.com``),
never on a display-name string comparison such as ``user.full_name == "Chethana"``.

The account list can be overridden with the ``NOTIFICATION_SETTINGS_ADMIN_EMAILS``
environment variable (comma separated), but configuration can never widen access
beyond the Management role.
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.management_access import MANAGEMENT_EMAILS
from app.models.entities import User

CAPABILITY_MANAGE_NOTIFICATION_SETTINGS = "manage_notification_settings"

MANAGEMENT_ROLE = "management"


def _configured_admin_emails() -> frozenset[str]:
    raw = os.getenv("NOTIFICATION_SETTINGS_ADMIN_EMAILS", "").strip()
    if not raw:
        return MANAGEMENT_EMAILS
    configured = frozenset(
        value.strip().lower() for value in raw.split(",") if value.strip()
    )
    # Never let configuration widen access beyond the Management role.
    return frozenset(configured & MANAGEMENT_EMAILS) or MANAGEMENT_EMAILS


def can_manage_notification_settings(user: User, effective_role: str) -> bool:
    """True only for the approved Management accounts holding this capability."""

    role = (effective_role or "").strip().lower()
    if role != MANAGEMENT_ROLE:
        return False
    return (user.email or "").strip().lower() in _configured_admin_emails()


def require_notification_settings_permission(
    auth: CurrentAuth = Depends(get_current_auth),
) -> User:
    """FastAPI dependency that enforces the capability on the BACKEND."""

    if not can_manage_notification_settings(auth.user, auth.effective_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )
    return auth.user