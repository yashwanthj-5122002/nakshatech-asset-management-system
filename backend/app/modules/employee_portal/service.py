from __future__ import annotations

import base64
from datetime import datetime, timedelta
from email.message import EmailMessage
import hashlib
import hmac
import json
import logging
import secrets
import struct
import time
import smtplib
import ssl
from typing import Any
from urllib.parse import quote

from cryptography.fernet import Fernet
import qrcode
import qrcode.image.svg
from fastapi import HTTPException, Request, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import EMPLOYEE_ROLE, SOFTWARE_TEAM_ROLE
from app.core.security import (
    create_access_token,
    create_temporary_token,
    decode_typed_token,
    hash_password,
    verify_password,
)
from app.models.entities import User, utc_now
from app.modules.employee_portal.models import (
    AuditEvent,
    AuthenticatorCredential,
    Branch,
    EmailOTPChallenge,
    SupportTicket,
    TicketMessage,
    TicketNotification,
    UserBranchAccess,
    UserSession,
)

logger = logging.getLogger(__name__)

REGISTRATION_PURPOSE = "registration"
PASSWORD_RESET_PURPOSE = "password_reset"
VALID_TICKET_DEPARTMENTS = {"it", "drone", "software_team", "management"}
VALID_TICKET_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_TICKET_STATUSES = {
    "new",
    "assigned",
    "in_progress",
    "waiting_for_employee",
    "resolved",
    "closed",
    "reopened",
}
DEPARTMENT_CODES = {
    "it": "IT",
    "drone": "DR",
    "software_team": "SW",
    "management": "MG",
}


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, *, timestamp: int | None = None, interval: int = 30, digits: int = 6) -> str:
    moment = int(time.time() if timestamp is None else timestamp)
    counter = moment // interval
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def verify_totp_code(secret: str, code: str, *, valid_window: int = 1) -> bool:
    now = int(time.time())
    for offset in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(totp_code(secret, timestamp=now + offset * 30), code):
            return True
    return False


def provisioning_uri(secret: str, email: str) -> str:
    issuer = settings.totp_issuer
    label = quote(f"{issuer}:{email}", safe="")
    return (
        f"otpauth://totp/{label}?secret={quote(secret, safe='')}"
        f"&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period=30"
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def ensure_allowed_email(email: str) -> str:
    normalized = normalize_email(email)
    domain = normalized.rsplit("@", 1)[-1] if "@" in normalized else ""
    if domain not in settings.allowed_email_domain_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only organization email addresses from {', '.join(settings.allowed_email_domain_list)} are allowed",
        )
    return normalized


def request_metadata(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


def record_audit(
    db: Session,
    *,
    event_type: str,
    request: Request | None = None,
    user: User | None = None,
    actor_email: str | None = None,
    result: str = "success",
    branch_id: int | None = None,
    module: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict[str, Any] | str | None = None,
) -> AuditEvent:
    ip, user_agent = request_metadata(request) if request is not None else (None, None)
    if isinstance(details, dict):
        details_text = json.dumps(details, ensure_ascii=True, separators=(",", ":"))
    else:
        details_text = details
    event = AuditEvent(
        user_id=user.id if user else None,
        actor_email=(user.email if user else actor_email),
        event_type=event_type,
        result=result,
        branch_id=branch_id,
        module=module,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details_text,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(event)
    return event


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="Password must contain at least 10 characters")
    checks = {
        "uppercase letter": any(char.isupper() for char in password),
        "lowercase letter": any(char.islower() for char in password),
        "number": any(char.isdigit() for char in password),
        "special character": any(not char.isalnum() for char in password),
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        raise HTTPException(status_code=400, detail=f"Password must include at least one {', '.join(missing)}")


def _fernet() -> Fernet:
    source = (settings.totp_encryption_key or settings.jwt_secret).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(source).digest())
    return Fernet(key)


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_totp_secret(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")


def build_qr_data_uri(uri: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(uri, image_factory=factory, box_size=8, border=3)
    payload = image.to_string(encoding="unicode")
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def send_email(*, recipient: str, subject: str, body: str) -> None:
    mode = settings.email_delivery_mode.strip().lower()
    if mode in {"console", "log"}:
        logger.warning("Development email to %s | %s | %s", recipient, subject, body)
        return
    if mode != "smtp":
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(body)
    try:
        context = ssl.create_default_context()
        if settings.smtp_use_ssl:
            smtp_client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
                context=context,
            )
        else:
            smtp_client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with smtp_client as smtp:
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception("Could not send CRM email")
        raise HTTPException(status_code=503, detail="The verification email could not be sent. Please try again later.") from exc


def _otp_email_body(code: str, purpose: str) -> tuple[str, str]:
    if purpose == REGISTRATION_PURPOSE:
        subject = "Verify your NakshaTech CRM account"
        action = "complete your NakshaTech CRM account registration"
    else:
        subject = "Reset your NakshaTech CRM password"
        action = "reset your NakshaTech CRM password"
    body = (
        f"Your NakshaTech CRM verification code is: {code}\n\n"
        f"Use this code within {settings.email_otp_expiry_minutes} minutes to {action}.\n"
        "Do not share this code with anyone. NakshaTech staff will never ask you for it."
    )
    return subject, body


def issue_email_otp(db: Session, *, email: str, purpose: str, request: Request) -> str:
    now = utc_now()
    recent_cutoff = now - timedelta(hours=1)
    recent_count = db.scalar(
        select(func.count(EmailOTPChallenge.id)).where(
            EmailOTPChallenge.email == email,
            EmailOTPChallenge.purpose == purpose,
            EmailOTPChallenge.created_at >= recent_cutoff,
        )
    ) or 0
    if recent_count >= settings.email_otp_max_requests_per_hour:
        raise HTTPException(status_code=429, detail="Too many OTP requests. Please try again later.")

    latest = db.scalar(
        select(EmailOTPChallenge)
        .where(EmailOTPChallenge.email == email, EmailOTPChallenge.purpose == purpose)
        .order_by(EmailOTPChallenge.created_at.desc())
        .limit(1)
    )
    if latest and (now - latest.created_at).total_seconds() < settings.email_otp_resend_seconds:
        wait = settings.email_otp_resend_seconds - int((now - latest.created_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Please wait {max(wait, 1)} seconds before requesting another OTP")

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.execute(
        update(EmailOTPChallenge)
        .where(
            EmailOTPChallenge.email == email,
            EmailOTPChallenge.purpose == purpose,
            EmailOTPChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    challenge = EmailOTPChallenge(
        email=email,
        purpose=purpose,
        code_hash=hash_password(code),
        max_attempts=settings.email_otp_max_attempts,
        expires_at=now + timedelta(minutes=settings.email_otp_expiry_minutes),
    )
    db.add(challenge)
    subject, body = _otp_email_body(code, purpose)
    send_email(recipient=email, subject=subject, body=body)
    record_audit(
        db,
        event_type="EMAIL_OTP_REQUESTED",
        request=request,
        actor_email=email,
        module="authentication",
        details={"purpose": purpose},
    )
    db.commit()
    return code


def verify_email_otp(db: Session, *, email: str, purpose: str, code: str, request: Request) -> None:
    now = utc_now()
    challenge = db.scalar(
        select(EmailOTPChallenge)
        .where(
            EmailOTPChallenge.email == email,
            EmailOTPChallenge.purpose == purpose,
            EmailOTPChallenge.consumed_at.is_(None),
        )
        .order_by(EmailOTPChallenge.created_at.desc())
        .limit(1)
    )
    if not challenge or challenge.expires_at < now:
        record_audit(
            db,
            event_type="EMAIL_OTP_VERIFICATION_FAILED",
            request=request,
            actor_email=email,
            result="failed",
            module="authentication",
            details={"purpose": purpose, "reason": "expired_or_missing"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="The OTP is invalid or has expired")
    if challenge.attempts >= challenge.max_attempts:
        raise HTTPException(status_code=429, detail="Too many incorrect OTP attempts. Request a new code.")
    challenge.attempts += 1
    if not verify_password(code, challenge.code_hash):
        record_audit(
            db,
            event_type="EMAIL_OTP_VERIFICATION_FAILED",
            request=request,
            actor_email=email,
            result="failed",
            module="authentication",
            details={"purpose": purpose, "reason": "incorrect_code"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="The OTP is invalid or has expired")
    challenge.consumed_at = now
    record_audit(
        db,
        event_type="EMAIL_VERIFIED" if purpose == REGISTRATION_PURPOSE else "PASSWORD_RESET_OTP_VERIFIED",
        request=request,
        actor_email=email,
        module="authentication",
    )
    db.commit()


def ensure_default_branch(db: Session) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.code == "HO"))
    if branch:
        return branch
    branch = Branch(code="HO", name="Head Office", address="NakshaTech Head Office")
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


def active_branches(db: Session) -> list[Branch]:
    ensure_default_branch(db)
    return list(db.scalars(select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.name)).all())


def get_branch(db: Session, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if not branch or not branch.is_active:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


def user_can_select_branch(db: Session, user: User, branch_id: int) -> bool:
    branch = db.get(Branch, branch_id)
    if not branch or not branch.is_active:
        return False
    if user.role == EMPLOYEE_ROLE:
        return True
    access = db.scalar(
        select(UserBranchAccess.id).where(
            UserBranchAccess.user_id == user.id,
            UserBranchAccess.branch_id == branch_id,
        )
    )
    if access:
        return True
    return branch.name.strip().lower() == (user.branch or "").strip().lower()


def get_user_branches(db: Session, user: User) -> list[Branch]:
    branches = active_branches(db)
    if user.role == EMPLOYEE_ROLE:
        return branches
    allowed_ids = set(
        db.scalars(select(UserBranchAccess.branch_id).where(UserBranchAccess.user_id == user.id)).all()
    )
    matched = [
        branch for branch in branches
        if branch.id in allowed_ids or branch.name.strip().lower() == (user.branch or "").strip().lower()
    ]
    return matched or branches[:1]


def create_user_session(db: Session, user: User, request: Request, branch_id: int | None = None) -> UserSession:
    ip, user_agent = request_metadata(request)
    session = UserSession(
        user_id=user.id,
        selected_branch_id=branch_id,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(session)
    db.flush()
    user.last_login_at = utc_now()
    record_audit(
        db,
        event_type="LOGIN_SUCCESS",
        request=request,
        user=user,
        branch_id=branch_id,
        module="authentication",
        target_type="session",
        target_id=session.id,
    )
    db.commit()
    db.refresh(session)
    return session


def issue_access_for_user(
    db: Session,
    *,
    user: User,
    request: Request,
    branch_id: int | None = None,
    existing_session: UserSession | None = None,
) -> tuple[str, UserSession]:
    session = existing_session or create_user_session(db, user, request, branch_id)
    if existing_session is not None and branch_id is not None:
        session.selected_branch_id = branch_id
        session.last_seen_at = utc_now()
        db.commit()
    token = create_access_token(
        user.email,
        user.role,
        token_version=user.token_version,
        session_id=session.id,
        branch_id=branch_id,
    )
    return token, session


def get_confirmed_authenticator(db: Session, user_id: int) -> AuthenticatorCredential | None:
    return db.scalar(
        select(AuthenticatorCredential).where(
            AuthenticatorCredential.user_id == user_id,
            AuthenticatorCredential.is_confirmed.is_(True),
        )
    )


def create_or_replace_authenticator(db: Session, user: User) -> tuple[AuthenticatorCredential, str, str]:
    secret = generate_totp_secret()
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if credential is None:
        credential = AuthenticatorCredential(user_id=user.id, encrypted_secret=encrypt_totp_secret(secret))
        db.add(credential)
    else:
        credential.encrypted_secret = encrypt_totp_secret(secret)
        credential.is_confirmed = False
        credential.enrolled_at = None
        credential.last_used_at = None
    uri = provisioning_uri(secret, user.email)
    db.commit()
    return credential, uri, build_qr_data_uri(uri)


def verify_totp_for_user(db: Session, user: User, code: str) -> bool:
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if not credential:
        return False
    secret = decrypt_totp_secret(credential.encrypted_secret)
    valid = verify_totp_code(secret, code, valid_window=settings.totp_valid_window)
    if valid:
        credential.last_used_at = utc_now()
        db.commit()
    return bool(valid)


def confirm_totp_for_user(db: Session, user: User, code: str) -> bool:
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if not credential:
        return False
    secret = decrypt_totp_secret(credential.encrypted_secret)
    valid = verify_totp_code(secret, code, valid_window=settings.totp_valid_window)
    if valid:
        credential.is_confirmed = True
        credential.enrolled_at = utc_now()
        credential.last_used_at = utc_now()
        user.is_active = True
        user.account_status = "active"
        user.email_verified = True
        db.commit()
    return bool(valid)


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip()
    if len(clean) <= 4:
        return "*" * len(clean)
    return f"{'*' * max(len(clean) - 4, 4)}{clean[-4:]}"


def end_session(db: Session, user: User, session_id: int | None, request: Request) -> None:
    if session_id:
        session = db.get(UserSession, session_id)
        if session and session.user_id == user.id and session.ended_at is None:
            session.ended_at = utc_now()
    user.last_logout_at = utc_now()
    record_audit(db, event_type="LOGOUT", request=request, user=user, module="authentication")
    db.commit()


def invalidate_all_sessions(db: Session, user: User) -> None:
    now = utc_now()
    user.token_version = (user.token_version or 0) + 1
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.ended_at.is_(None))
        .values(ended_at=now)
    )


def selected_branch_id_from_claims(claims: dict[str, Any]) -> int | None:
    value = claims.get("branch_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def ticket_department_for_role(role: str) -> str | None:
    return role if role in VALID_TICKET_DEPARTMENTS else None


def can_view_ticket(user: User, ticket: SupportTicket) -> bool:
    if user.id == ticket.requester_id:
        return True
    if user.role == SOFTWARE_TEAM_ROLE:
        return True
    return ticket_department_for_role(user.role) == ticket.department


def can_handle_ticket(user: User, ticket: SupportTicket) -> bool:
    if user.role == SOFTWARE_TEAM_ROLE:
        return ticket.department == SOFTWARE_TEAM_ROLE
    return ticket_department_for_role(user.role) == ticket.department


def _ticket_requester_and_assignee(db: Session, ticket: SupportTicket) -> tuple[User, User | None]:
    requester = db.get(User, ticket.requester_id)
    if not requester:
        raise HTTPException(status_code=500, detail="Ticket requester record is missing")
    assignee = db.get(User, ticket.assigned_to_id) if ticket.assigned_to_id else None
    return requester, assignee


def serialize_ticket_summary(db: Session, ticket: SupportTicket, viewer: User) -> dict[str, Any]:
    requester, assignee = _ticket_requester_and_assignee(db, ticket)
    branch = db.get(Branch, ticket.branch_id)
    return {
        "id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "requester_name": requester.full_name,
        "requester_email": requester.email,
        "branch_id": ticket.branch_id,
        "branch_name": branch.name if branch else "Unknown branch",
        "department": ticket.department,
        "category": ticket.category,
        "title": ticket.title,
        "priority": ticket.priority,
        "status": ticket.status,
        "assigned_to_name": assignee.full_name if assignee else None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "can_handle": can_handle_ticket(viewer, ticket),
    }


def serialize_ticket_detail(db: Session, ticket: SupportTicket, viewer: User) -> dict[str, Any]:
    payload = serialize_ticket_summary(db, ticket, viewer)
    messages = list(
        db.scalars(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at)).all()
    )
    authors = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_({message.author_id for message in messages}))).all()
    } if messages else {}
    payload.update(
        {
            "description": ticket.description,
            "location": ticket.location,
            "asset_number": ticket.asset_number,
            "resolution": ticket.resolution,
            "messages": [
                {
                    "id": message.id,
                    "author_id": message.author_id,
                    "author_name": authors[message.author_id].full_name,
                    "author_email": authors[message.author_id].email,
                    "author_role": authors[message.author_id].role,
                    "message": message.message,
                    "created_at": message.created_at,
                }
                for message in messages
            ],
        }
    )
    return payload


def create_ticket_notifications(db: Session, ticket: SupportTicket, requester: User) -> None:
    selected_title = f"New {ticket.department.replace('_', ' ').title()} ticket {ticket.ticket_code}"
    selected_message = f"{requester.full_name} raised: {ticket.title}"
    db.add(
        TicketNotification(
            ticket_id=ticket.id,
            recipient_role=ticket.department,
            notification_type="ticket_created",
            title=selected_title,
            message=selected_message,
        )
    )
    if ticket.department != SOFTWARE_TEAM_ROLE:
        db.add(
            TicketNotification(
                ticket_id=ticket.id,
                recipient_role=SOFTWARE_TEAM_ROLE,
                notification_type="ticket_monitoring",
                title=f"Ticket routed to {ticket.department.replace('_', ' ').title()}",
                message=f"{ticket.ticket_code}: {ticket.title}",
            )
        )


def notify_requester(db: Session, ticket: SupportTicket, *, notification_type: str, title: str, message: str) -> None:
    db.add(
        TicketNotification(
            ticket_id=ticket.id,
            recipient_user_id=ticket.requester_id,
            notification_type=notification_type,
            title=title,
            message=message,
        )
    )


def decode_temporary_subject(token: str, expected_type: str) -> tuple[str, dict[str, Any]]:
    try:
        payload = decode_typed_token(token, expected_type)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="The verification session is invalid or has expired") from exc
    subject = normalize_email(str(payload.get("sub") or ""))
    if not subject:
        raise HTTPException(status_code=401, detail="The verification session is invalid or has expired")
    return subject, payload
