from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
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
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
import qrcode
import qrcode.image.svg
from fastapi import HTTPException, Request, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.roles import EMPLOYEE_ROLE, SOFTWARE_TEAM_ROLE
from app.core.management_access import MANAGEMENT_ROLE
from app.core.security import (
    create_access_token,
    create_temporary_token,
    decode_typed_token,
    hash_password,
    verify_password,
)
from app.models.entities import Asset, User, utc_now
from app.modules.employee_portal.models import (
    AuditEvent,
    AuthenticatorCredential,
    Branch,
    EmailOTPChallenge,
    SupportTicket,
    TicketAttachment,
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

PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
PRIORITY_SLA_MINUTES = {"low": 1440, "medium": 480, "high": 120, "critical": 30}

TICKET_COMPONENT_CATALOG: dict[str, dict[str, Any]] = {
    "system": {
        "label": "CPU / System Unit",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "not_powering_on": ("System not turning on", "high"),
            "frequent_restart": ("Frequent restart", "medium"),
            "blue_screen": ("Blue screen", "high"),
            "overheating": ("System overheating", "high"),
            "very_slow": ("Very slow performance", "medium"),
            "storage_full": ("Storage full", "medium"),
            "unexpected_shutdown": ("Unexpected shutdown", "high"),
            "unusual_noise": ("Unusual noise", "medium"),
            "other_system_issue": ("Other system issue", "low"),
        },
    },
    "monitor": {
        "label": "Monitor",
        "tag_source": "monitor_asset_tags",
        "problems": {
            "no_display": ("No display", "high"),
            "flickering_display": ("Flickering display", "medium"),
            "screen_damaged": ("Screen damaged", "high"),
            "incorrect_resolution": ("Incorrect resolution", "low"),
            "monitor_cable_issue": ("Cable issue", "medium"),
            "colour_issue": ("Colour issue", "low"),
            "monitor_not_powering_on": ("Monitor not turning on", "high"),
            "multiple_monitor_issue": ("Multiple-monitor issue", "medium"),
            "other_monitor_issue": ("Other monitor issue", "low"),
        },
    },
    "mouse": {
        "label": "Mouse",
        "tag_source": "mouse_asset_tag",
        "problems": {
            "mouse_not_detected": ("Mouse not detected", "medium"),
            "pointer_not_moving": ("Pointer not moving", "medium"),
            "pointer_incorrect": ("Pointer moving incorrectly", "low"),
            "left_click_not_working": ("Left click not working", "low"),
            "right_click_not_working": ("Right click not working", "low"),
            "scroll_not_working": ("Scroll wheel not working", "low"),
            "mouse_cable_damaged": ("Cable damaged", "medium"),
            "mouse_intermittent": ("Intermittent connection", "medium"),
            "mouse_unusable": ("Mouse completely unusable", "medium"),
            "other_mouse_issue": ("Other mouse problem", "low"),
        },
    },
    "keyboard": {
        "label": "Keyboard",
        "tag_source": "keyboard_asset_tag",
        "problems": {
            "keyboard_not_detected": ("Keyboard not detected", "medium"),
            "keys_not_working": ("Some keys not working", "medium"),
            "keyboard_unusable": ("Keyboard completely unusable", "medium"),
            "keyboard_cable_damaged": ("Cable damaged", "medium"),
            "keyboard_intermittent": ("Intermittent connection", "medium"),
            "other_keyboard_issue": ("Other keyboard problem", "low"),
        },
    },
    "memory": {
        "label": "RAM / Memory",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "ram_not_detected": ("RAM not detected", "high"),
            "memory_error": ("Memory error", "high"),
            "frequent_crash": ("Frequent crash", "high"),
            "insufficient_memory": ("Insufficient memory", "medium"),
            "memory_upgrade_request": ("Memory upgrade request", "low"),
            "other_memory_issue": ("Other memory issue", "low"),
        },
    },
    "storage": {
        "label": "SSD / Hard Disk",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "drive_not_detected": ("Drive not detected", "high"),
            "disk_full": ("Storage full", "medium"),
            "slow_disk": ("Disk is very slow", "medium"),
            "data_access_error": ("Cannot access files", "high"),
            "suspected_drive_failure": ("Suspected drive failure", "high"),
            "storage_upgrade_request": ("Storage upgrade request", "low"),
            "other_storage_issue": ("Other storage issue", "low"),
        },
    },
    "network": {
        "label": "Network / Internet",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "no_internet": ("No internet", "high"),
            "slow_internet": ("Slow internet", "medium"),
            "lan_disconnected": ("LAN disconnected", "medium"),
            "wifi_not_connecting": ("Wi-Fi not connecting", "medium"),
            "vpn_not_working": ("VPN not working", "medium"),
            "internal_server_inaccessible": ("Internal server inaccessible", "high"),
            "network_intermittent": ("Intermittent connection", "medium"),
            "other_network_issue": ("Other network issue", "low"),
        },
    },
    "operating_system": {
        "label": "Operating System",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "os_not_booting": ("Operating system not booting", "high"),
            "os_blue_screen": ("Blue screen", "high"),
            "os_update_failure": ("Update failure", "medium"),
            "login_loop": ("Login loop", "high"),
            "driver_error": ("Driver error", "medium"),
            "os_corruption": ("Suspected operating system corruption", "high"),
            "other_os_issue": ("Other operating system issue", "low"),
        },
    },
    "software": {
        "label": "Software / Application",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "application_not_opening": ("Application not opening", "medium"),
            "application_crashing": ("Application crashing", "medium"),
            "license_issue": ("License issue", "medium"),
            "installation_required": ("Installation required", "low"),
            "permission_denied": ("Permission denied", "medium"),
            "application_data_not_loading": ("Data not loading", "high"),
            "application_update_failure": ("Update failure", "medium"),
            "application_performance": ("Application performance issue", "low"),
            "other_software_issue": ("Other software issue", "low"),
        },
    },
    "printer": {
        "label": "Printer / Scanner",
        "tag_source": None,
        "problems": {
            "printer_not_printing": ("Printer not printing", "medium"),
            "printer_offline": ("Printer offline", "medium"),
            "paper_jam": ("Paper jam", "low"),
            "poor_print_quality": ("Poor print quality", "low"),
            "network_printer_unavailable": ("Network printer unavailable", "medium"),
            "printer_driver_issue": ("Printer driver issue", "medium"),
            "scanner_not_working": ("Scanner not working", "medium"),
            "other_printer_issue": ("Other printer or scanner issue", "low"),
        },
    },
    "power_ups": {
        "label": "UPS / Power",
        "tag_source": None,
        "problems": {
            "no_power": ("No power", "high"),
            "ups_alarm": ("UPS alarm", "high"),
            "ups_battery_failure": ("UPS battery failure", "medium"),
            "power_fluctuation": ("Power fluctuation", "high"),
            "other_power_issue": ("Other power issue", "low"),
        },
    },
    "login_account": {
        "label": "Login / Account Access",
        "tag_source": "cpu_asset_tag",
        "problems": {
            "cannot_login": ("Cannot log in", "high"),
            "account_locked": ("Account locked", "medium"),
            "password_reset_required": ("Password reset required", "low"),
            "email_inaccessible": ("Email inaccessible", "medium"),
            "access_permission_issue": ("Access permission issue", "medium"),
            "suspected_account_compromise": ("Suspected account compromise", "critical"),
            "other_account_issue": ("Other login or account issue", "low"),
        },
    },
    "other": {
        "label": "Other Issue",
        "tag_source": None,
        "problems": {
            "other_it_issue": ("Other IT issue", "low"),
        },
    },
}


def ticket_catalog_payload() -> dict[str, Any]:
    return {
        "components": [
            {
                "code": code,
                "label": item["label"],
                "problems": [
                    {"code": problem_code, "label": problem[0]}
                    for problem_code, problem in item["problems"].items()
                ],
            }
            for code, item in TICKET_COMPONENT_CATALOG.items()
        ]
    }


def ticket_component_asset_tag(asset: Asset, component: str) -> str | None:
    item = TICKET_COMPONENT_CATALOG.get(component)
    if not item:
        return None
    field_name = item.get("tag_source")
    if not field_name:
        return None
    value = getattr(asset, field_name, None)
    return str(value).strip() if value is not None and str(value).strip() else None


def calculate_it_ticket_priority(
    component: str,
    problem_code: str,
    impact: dict[str, Any],
) -> tuple[str, str, int, str]:
    component_item = TICKET_COMPONENT_CATALOG.get(component)
    if not component_item:
        raise HTTPException(status_code=422, detail="Select a valid affected component")
    problem = component_item["problems"].get(problem_code)
    if not problem:
        raise HTTPException(status_code=422, detail="Select a valid problem for the affected component")

    problem_label, base_priority = problem
    selected_priority = base_priority
    reasons: list[str] = [f"{component_item['label']}: {problem_label}"]

    if bool(impact.get("security_risk")):
        selected_priority = "critical"
        reasons.append("a security risk was reported")
    if bool(impact.get("data_loss_risk")):
        selected_priority = "critical"
        reasons.append("a possible data-loss risk was reported")
    if bool(impact.get("multiple_users_affected")) and bool(impact.get("work_stopped")):
        selected_priority = "critical"
        reasons.append("multiple employees are blocked from working")
    elif bool(impact.get("multiple_users_affected")) and PRIORITY_RANK[selected_priority] < PRIORITY_RANK["high"]:
        selected_priority = "high"
        reasons.append("multiple employees are affected")

    if bool(impact.get("work_stopped")) and not bool(impact.get("alternative_available")):
        if PRIORITY_RANK[selected_priority] < PRIORITY_RANK["high"]:
            selected_priority = "high"
        reasons.append("work is completely stopped and no alternative is available")
    elif bool(impact.get("work_stopped")):
        if PRIORITY_RANK[selected_priority] < PRIORITY_RANK["medium"]:
            selected_priority = "medium"
        reasons.append("work is stopped but an alternative is available")

    if bool(impact.get("client_delivery_affected")):
        minimum = "high" if bool(impact.get("work_stopped")) else "medium"
        if PRIORITY_RANK[selected_priority] < PRIORITY_RANK[minimum]:
            selected_priority = minimum
        reasons.append("a project or client delivery is affected")

    if bool(impact.get("recurring_issue")) and PRIORITY_RANK[selected_priority] < PRIORITY_RANK["medium"]:
        selected_priority = "medium"
        reasons.append("the issue has occurred before")

    reason = "; ".join(dict.fromkeys(reasons)) + "."
    return selected_priority, reason, PRIORITY_SLA_MINUTES[selected_priority], problem_label


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


def send_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    from_name: str | None = None,
) -> None:
    mode = settings.email_delivery_mode.strip().lower()
    if mode in {"console", "log"}:
        logger.warning("Development email to %s | %s | %s", recipient, subject, body)
        return
    if mode != "smtp":
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name or settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
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
        raise HTTPException(status_code=503, detail="The email could not be sent. Please try again later.") from exc


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
    access_role: str | None = None,
) -> tuple[str, UserSession]:
    session = existing_session or create_user_session(db, user, request, branch_id)
    if existing_session is not None and branch_id is not None:
        session.selected_branch_id = branch_id
        session.last_seen_at = utc_now()
        db.commit()
    token = create_access_token(
        user.email,
        access_role or user.role,
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


def confirm_totp_for_user(
    db: Session,
    user: User,
    code: str,
    *,
    activate_user: bool = True,
) -> bool:
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if not credential:
        return False
    secret = decrypt_totp_secret(credential.encrypted_secret)
    valid = verify_totp_code(secret, code, valid_window=settings.totp_valid_window)
    if valid:
        credential.is_confirmed = True
        credential.enrolled_at = utc_now()
        credential.last_used_at = utc_now()
        user.email_verified = True
        user.mfa_required = False
        if activate_user:
            user.is_active = True
            user.account_status = "active"
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


def can_view_ticket(user: User, ticket: SupportTicket, role_override: str | None = None) -> bool:
    role = role_override or user.role
    if user.id == ticket.requester_id:
        return True
    if role in {SOFTWARE_TEAM_ROLE, MANAGEMENT_ROLE}:
        return True
    return ticket_department_for_role(role) == ticket.department


def can_handle_ticket(user: User, ticket: SupportTicket, role_override: str | None = None) -> bool:
    role = role_override or user.role
    if role == SOFTWARE_TEAM_ROLE:
        return ticket.department == SOFTWARE_TEAM_ROLE
    return ticket_department_for_role(role) == ticket.department


def serialize_ticket_asset(asset: Asset) -> dict[str, Any]:
    """Create the immutable asset snapshot stored with a support ticket."""
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "cpu_asset_tag": asset.cpu_asset_tag,
        "workstation_no": asset.workstation_no,
        "used_by": asset.used_by,
        "department": asset.department,
        "system_name": asset.system_name,
        "device_type": asset.device_type,
        "processor": asset.processor,
        "memory_gb": asset.memory_gb,
        "ssd": asset.ssd,
        "hdd": asset.hdd,
        "operating_system": asset.operating_system,
        "location": asset.location,
        "work_mode": asset.work_mode,
        "status": asset.status,
        "monitor_asset_tags": asset.monitor_asset_tags,
        "mouse_asset_tag": asset.mouse_asset_tag,
        "keyboard_asset_tag": asset.keyboard_asset_tag,
    }


def deserialize_ticket_asset(ticket: SupportTicket) -> dict[str, Any] | None:
    if not ticket.asset_snapshot:
        return None
    try:
        payload = json.loads(ticket.asset_snapshot)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Ticket %s contains an invalid asset snapshot", ticket.id)
        return None
    return payload if isinstance(payload, dict) else None


def deserialize_ticket_impact(ticket: SupportTicket) -> dict[str, Any] | None:
    if not ticket.impact_assessment:
        return None
    try:
        payload = json.loads(ticket.impact_assessment)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Ticket %s contains an invalid impact assessment", ticket.id)
        return None
    return payload if isinstance(payload, dict) else None


def _ticket_requester_and_assignee(db: Session, ticket: SupportTicket) -> tuple[User, User | None]:
    requester = db.get(User, ticket.requester_id)
    if not requester:
        raise HTTPException(status_code=500, detail="Ticket requester record is missing")
    assignee = db.get(User, ticket.assigned_to_id) if ticket.assigned_to_id else None
    return requester, assignee


def serialize_ticket_summary(db: Session, ticket: SupportTicket, viewer: User, viewer_role: str | None = None) -> dict[str, Any]:
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
        "asset_number": ticket.asset_number,
        "component": ticket.component,
        "component_asset_tag": ticket.component_asset_tag,
        "problem_code": ticket.problem_code,
        "problem_label": ticket.problem_label,
        "priority_reason": ticket.priority_reason,
        "sla_target_minutes": ticket.sla_target_minutes,
        "sla_status": "not_applicable",
        "sla_due_at": None,
        "sla_warning_at": None,
        "sla_first_response_at": None,
        "sla_remaining_seconds": None,
        "sla_warning": False,
        "sla_breached": False,
        "sla_escalation_level": "none",
        "assigned_to_name": assignee.full_name if assignee else None,
        "queue_position": None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "resolved_at": ticket.resolved_at,
        "closed_at": ticket.closed_at,
        "can_handle": can_handle_ticket(viewer, ticket, viewer_role),
    }


def serialize_ticket_detail(db: Session, ticket: SupportTicket, viewer: User, viewer_role: str | None = None) -> dict[str, Any]:
    payload = serialize_ticket_summary(db, ticket, viewer, viewer_role)
    messages = list(
        db.scalars(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at)).all()
    )
    attachments = list(
        db.scalars(
            select(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket.id)
            .order_by(TicketAttachment.created_at, TicketAttachment.id)
        ).all()
    )
    user_ids = {message.author_id for message in messages} | {attachment.uploaded_by_id for attachment in attachments}
    authors = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    payload.update(
        {
            "description": ticket.description,
            "reporting_manager_email": ticket.reporting_manager_email,
            "location": ticket.location,
            "asset_number": ticket.asset_number,
            "asset_id": ticket.asset_id,
            "asset_snapshot": deserialize_ticket_asset(ticket),
            "impact_assessment": deserialize_ticket_impact(ticket),
            "resolution": ticket.resolution,
            "attachments": [
                {
                    "id": attachment.id,
                    "ticket_id": attachment.ticket_id,
                    "message_id": attachment.message_id,
                    "uploaded_by_id": attachment.uploaded_by_id,
                    "uploaded_by_name": authors.get(attachment.uploaded_by_id).full_name if authors.get(attachment.uploaded_by_id) else "Unknown user",
                    "original_filename": attachment.original_filename,
                    "mime_type": attachment.mime_type,
                    "file_size": attachment.file_size,
                    "created_at": attachment.created_at,
                }
                for attachment in attachments
            ],
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
    classification = f" · {ticket.problem_label}" if ticket.problem_label else ""
    selected_message = f"{requester.full_name} raised: {ticket.title}{classification}"
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


def _ticket_datetime_label(value: datetime | None) -> str:
    if value is None:
        return "Not recorded"
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M %p IST")


def _ticket_public_url(ticket: SupportTicket) -> str:
    base_url = settings.app_public_url.strip().rstrip("/") or "http://localhost:3100"
    return f"{base_url}/tickets/{ticket.id}"


def _ticket_email_content(
    *,
    ticket: SupportTicket,
    requester: User,
    branch: Branch | None,
    audience: str,
    event: str,
    resolved_by: User | None,
) -> tuple[str, str, str]:
    department_label = ticket.department.replace("_", " ").title()
    priority_label = ticket.priority.title()
    status_label = ticket.status.replace("_", " ").title()
    branch_label = branch.name if branch else "Unknown branch"
    ticket_url = _ticket_public_url(ticket)
    manager_email = ticket.reporting_manager_email or "Not recorded"
    category = ticket.problem_label or ticket.category or ticket.component or "Not specified"
    employee_department = requester.department or "Not recorded"
    employee_designation = requester.designation or "Not recorded"
    asset_number = ticket.asset_number or "Not linked"
    location = ticket.location or "Not recorded"
    resolution = ticket.resolution or "No resolution notes were provided."
    resolved_by_label = resolved_by.full_name if resolved_by else "Assigned support team"

    if event == "created":
        if audience == "requester":
            greeting = f"Dear {requester.full_name},"
            intro = (
                "Your support ticket has been successfully submitted to "
                f"{settings.ticket_email_heading}."
            )
            subject = f"Your Support Ticket Has Been Raised - {ticket.ticket_code}"
        elif audience == "manager":
            greeting = "Dear Reporting Manager,"
            intro = f"{requester.full_name} has raised a support ticket that has been routed to the {department_label}."
            subject = f"Support Ticket Raised by {requester.full_name} - {ticket.ticket_code}"
        else:
            greeting = "Dear IT Support Team,"
            intro = f"A new support ticket has been raised by {requester.full_name}."
            subject = f"New {department_label} Support Ticket - {ticket.ticket_code} - {priority_label} Priority"
        event_heading = "New Support Ticket"
        event_time_label = "Raised At"
        event_time_value = _ticket_datetime_label(ticket.created_at)
    else:
        if audience == "manager":
            greeting = "Dear Reporting Manager,"
        elif audience == "requester":
            greeting = f"Dear {requester.full_name},"
        else:
            greeting = "Dear IT Support Team,"
        intro = f"Support ticket {ticket.ticket_code} has been marked as {status_label}."
        subject = f"Support Ticket {status_label} - {ticket.ticket_code} - {ticket.title}"
        event_heading = f"Ticket {status_label}"
        event_time_label = "Resolved At" if ticket.status == "resolved" else "Closed At"
        event_time_value = _ticket_datetime_label(ticket.resolved_at or ticket.closed_at or ticket.updated_at)

    common_lines = [
        greeting,
        "",
        intro,
        "",
        f"Ticket Number: {ticket.ticket_code}",
        f"Employee Name: {requester.full_name}",
        f"Employee Email: {requester.email}",
        f"Employee Department: {employee_department}",
        f"Employee Designation: {employee_designation}",
        f"Reporting Manager: {manager_email}",
        f"Branch: {branch_label}",
        f"Responsible Department: {department_label}",
        f"Category / Problem: {category}",
        f"Priority: {priority_label}",
        f"Status: {status_label}",
        f"Asset Number: {asset_number}",
        f"Issue Location: {location}",
        f"{event_time_label}: {event_time_value}",
        "",
        "Issue Title:",
        ticket.title,
        "",
        "Issue Description:",
        ticket.description,
    ]
    if event != "created":
        common_lines.extend(
            [
                "",
                "Resolution:",
                resolution,
                "",
                f"Resolved By: {resolved_by_label}",
            ]
        )
    common_lines.extend(
        [
            "",
            f"View Ticket: {ticket_url}",
            "",
            "Best regards,",
            settings.ticket_email_heading,
            "NakshaTech Asset Management System",
            "Office: +91 8197870646",
            "Email: software.team@nakshatech.com",
            "Website: https://nakshatech.com",
            "#73/1A, RK Chambers, 5th Main, Chamarajpet, Bangalore, India - 560018",
            "",
            "This message may contain privileged or confidential information and is intended only for the addressed recipient. If received in error, please notify the sender and delete all copies.",
        ]
    )
    text_body = "\n".join(common_lines)

    def safe(value: object) -> str:
        return escape(str(value), quote=True)

    def safe_multiline(value: str) -> str:
        return safe(value).replace("\n", "<br>")

    rows = [
        ("Ticket Number", ticket.ticket_code),
        ("Employee Name", requester.full_name),
        ("Employee Email", requester.email),
        ("Employee Department", employee_department),
        ("Employee Designation", employee_designation),
        ("Reporting Manager", manager_email),
        ("Branch", branch_label),
        ("Responsible Department", department_label),
        ("Category / Problem", category),
        ("Priority", priority_label),
        ("Status", status_label),
        ("Asset Number", asset_number),
        ("Issue Location", location),
        (event_time_label, event_time_value),
    ]
    if event != "created":
        rows.append(("Resolved By", resolved_by_label))
    rows_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #dbe5ef;color:#526579;width:38%;">{safe(label)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #dbe5ef;color:#102a43;font-weight:600;">{safe(value)}</td></tr>'
        for label, value in rows
    )
    resolution_html = ""
    if event != "created":
        resolution_html = (
            '<div style="margin-top:18px;padding:16px;border-radius:10px;background:#eef9f5;border:1px solid #bde8d8;">'
            '<div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#087f5b;">RESOLUTION</div>'
            f'<div style="margin-top:8px;color:#183b56;line-height:1.6;">{safe_multiline(resolution)}</div></div>'
        )
    html_body = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f7fa;font-family:Arial,Helvetica,sans-serif;color:#183b56;">
    <div style="max-width:760px;margin:0 auto;padding:24px 12px;">
      <div style="background:#ffffff;border:1px solid #dbe5ef;border-radius:14px;overflow:hidden;box-shadow:0 8px 26px rgba(15,42,67,.08);">
        <div style="padding:22px 26px;background:linear-gradient(135deg,#083b66,#006d8f);color:#ffffff;">
          <div style="font-size:20px;font-weight:800;letter-spacing:.08em;">NAKSHA<span style="color:#53d6e7;">TECH</span></div>
          <div style="margin-top:7px;font-size:15px;font-weight:700;">{safe(settings.ticket_email_heading)}</div>
          <div style="margin-top:4px;font-size:12px;color:#cbeef4;">{safe(event_heading)}</div>
        </div>
        <div style="padding:24px 26px;">
          <p style="margin:0 0 12px;font-weight:700;">{safe(greeting)}</p>
          <p style="margin:0 0 20px;line-height:1.6;">{safe(intro)}</p>
          <table role="presentation" style="width:100%;border-collapse:collapse;border:1px solid #dbe5ef;border-radius:10px;overflow:hidden;">{rows_html}</table>
          <div style="margin-top:18px;padding:16px;border-radius:10px;background:#f7fafc;border:1px solid #dbe5ef;">
            <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#526579;">ISSUE TITLE</div>
            <div style="margin-top:7px;font-weight:700;color:#102a43;">{safe(ticket.title)}</div>
            <div style="margin-top:16px;font-size:12px;font-weight:700;letter-spacing:.08em;color:#526579;">ISSUE DESCRIPTION</div>
            <div style="margin-top:7px;line-height:1.6;">{safe_multiline(ticket.description)}</div>
          </div>
          {resolution_html}
          <div style="margin-top:22px;text-align:center;">
            <a href="{safe(ticket_url)}" style="display:inline-block;padding:11px 20px;border-radius:8px;background:#008fb3;color:#ffffff;text-decoration:none;font-weight:700;">View Support Ticket</a>
          </div>
        </div>
        <div style="padding:18px 26px;background:#f7fafc;border-top:1px solid #dbe5ef;font-size:12px;line-height:1.6;color:#526579;">
          <strong style="color:#183b56;">Best regards,<br>{safe(settings.ticket_email_heading)}</strong><br>
          NakshaTech Asset Management System<br>
          Office: +91 8197870646<br>
          Email: <a href="mailto:software.team@nakshatech.com" style="color:#007c9f;">software.team@nakshatech.com</a><br>
          Website: <a href="https://nakshatech.com" style="color:#007c9f;">https://nakshatech.com</a><br>
          #73/1A, RK Chambers, 5th Main, Chamarajpet, Bangalore, India - 560018
          <div style="margin-top:14px;padding-top:12px;border-top:1px solid #dbe5ef;font-size:11px;color:#718096;">
            This message may contain privileged or confidential information and is intended only for the addressed recipient. If received in error, please notify the sender and delete all copies.
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
""".strip()
    return subject, text_body, html_body


def deliver_ticket_lifecycle_emails(ticket_id: int, event: str, actor_user_id: int | None = None) -> None:
    """Send ticket email notifications after the ticket transaction has committed.

    Delivery failures are written to the audit table and never roll back or remove
    the support ticket itself.
    """
    if event not in {"created", "resolved"}:
        logger.warning("Ignoring unsupported ticket email event %s", event)
        return

    with SessionLocal() as db:
        ticket = db.get(SupportTicket, ticket_id)
        if ticket is None:
            logger.warning("Ticket email skipped because ticket %s was not found", ticket_id)
            return
        requester = db.get(User, ticket.requester_id)
        if requester is None:
            logger.warning("Ticket email skipped because requester %s was not found", ticket.requester_id)
            return
        branch = db.get(Branch, ticket.branch_id)
        actor = db.get(User, actor_user_id) if actor_user_id else None

        it_recipient = (
            settings.it_support_email.strip().lower()
            or settings.smtp_username.strip().lower()
            or settings.smtp_from_email.strip().lower()
        )
        # The requester always receives a lifecycle email. Keep the requester
        # first so that, when an employee and manager address are identical,
        # the employee confirmation/update is preserved and duplicates are skipped.
        candidates: list[tuple[str, str]] = [
            (requester.email.strip().lower(), "requester"),
        ]
        if ticket.reporting_manager_email:
            candidates.append((ticket.reporting_manager_email.strip().lower(), "manager"))
        if it_recipient:
            candidates.append((it_recipient, "it"))

        seen: set[str] = set()
        for recipient, audience in candidates:
            if not recipient or recipient in seen:
                continue
            seen.add(recipient)
            result = "success"
            error_text: str | None = None
            try:
                subject, text_body, html_body = _ticket_email_content(
                    ticket=ticket,
                    requester=requester,
                    branch=branch,
                    audience=audience,
                    event=event,
                    resolved_by=actor,
                )
                send_email(
                    recipient=recipient,
                    subject=subject,
                    body=text_body,
                    html_body=html_body,
                    from_name=settings.ticket_email_heading,
                )
            except Exception as exc:  # Ticket creation/update must survive SMTP or configuration failures.
                result = "failed"
                error_text = str(exc)[:500]
                logger.exception("Ticket email delivery failed for ticket %s to %s", ticket.ticket_code, recipient)

            record_audit(
                db,
                event_type="TICKET_EMAIL_SENT" if result == "success" else "TICKET_EMAIL_FAILED",
                user=actor,
                actor_email=(actor.email if actor else requester.email),
                result=result,
                branch_id=ticket.branch_id,
                module="tickets",
                target_type="ticket",
                target_id=ticket.id,
                details={
                    "ticket_code": ticket.ticket_code,
                    "email_event": event,
                    "recipient": recipient,
                    "audience": audience,
                    "error": error_text,
                },
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Could not persist ticket email audit for ticket %s", ticket.ticket_code)


def decode_temporary_subject(token: str, expected_type: str) -> tuple[str, dict[str, Any]]:
    try:
        payload = decode_typed_token(token, expected_type)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="The verification session is invalid or has expired") from exc
    subject = normalize_email(str(payload.get("sub") or ""))
    if not subject:
        raise HTTPException(status_code=401, detail="The verification session is invalid or has expired")
    return subject, payload
