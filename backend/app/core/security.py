from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_signed_token(
    subject: str,
    *,
    token_type: str,
    minutes: int,
    role: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    if role:
        payload["role"] = role
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str,
    role: str,
    *,
    token_version: int = 0,
    session_id: int | None = None,
    branch_id: int | None = None,
) -> str:
    extra: dict[str, Any] = {"ver": token_version}
    if session_id is not None:
        extra["sid"] = session_id
    if branch_id is not None:
        extra["branch_id"] = branch_id
    return create_signed_token(
        subject,
        token_type="access",
        minutes=settings.access_token_minutes,
        role=role,
        extra=extra,
    )


def create_temporary_token(
    subject: str,
    token_type: str,
    *,
    role: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    return create_signed_token(
        subject,
        token_type=token_type,
        minutes=settings.temporary_token_minutes,
        role=role,
        extra=extra,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def decode_typed_token(token: str, expected_type: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected {expected_type} token")
    return payload
