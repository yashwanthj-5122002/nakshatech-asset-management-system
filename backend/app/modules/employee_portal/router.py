from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth, get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.roles import EMPLOYEE_ROLE, SOFTWARE_TEAM_ROLE
from app.core.security import create_temporary_token, hash_password
from app.models.entities import User, utc_now
from app.modules.employee_portal.models import (
    AuditEvent,
    AuthenticatorCredential,
    Branch,
    SupportTicket,
    TicketMessage,
    TicketNotification,
    UserBranchAccess,
    UserSession,
)
from app.modules.employee_portal.schemas import (
    AuditEventResponse,
    AuditPageViewRequest,
    BranchResponse,
    BranchSelectionRequest,
    ForgotPasswordVerifyResponse,
    MFAConfirmRequest,
    MFALoginVerifyRequest,
    MFASetupResponse,
    NotificationResponse,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    PasswordResetRequest,
    RegistrationCompleteRequest,
    RegistrationOTPVerifyResponse,
    SoftwareUserResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketMessageCreate,
    TicketSummaryResponse,
    TicketUpdateRequest,
)
from app.modules.employee_portal.service import (
    PASSWORD_RESET_PURPOSE,
    REGISTRATION_PURPOSE,
    DEPARTMENT_CODES,
    VALID_TICKET_DEPARTMENTS,
    VALID_TICKET_PRIORITIES,
    VALID_TICKET_STATUSES,
    active_branches,
    can_handle_ticket,
    can_view_ticket,
    confirm_totp_for_user,
    create_or_replace_authenticator,
    create_ticket_notifications,
    decode_temporary_subject,
    ensure_allowed_email,
    get_branch,
    get_confirmed_authenticator,
    get_user_branches,
    invalidate_all_sessions,
    issue_access_for_user,
    issue_email_otp,
    mask_phone,
    normalize_email,
    notify_requester,
    record_audit,
    selected_branch_id_from_claims,
    serialize_ticket_detail,
    serialize_ticket_summary,
    ticket_department_for_role,
    user_can_select_branch,
    validate_password_strength,
    verify_email_otp,
    verify_totp_for_user,
)
from app.schemas.auth import LoginResponse, UserResponse

router = APIRouter(tags=["Employee Portal"])


def _user_response(db: Session, user: User, branch_id: int | None = None) -> UserResponse:
    branch = db.get(Branch, branch_id) if branch_id else None
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        branch=branch.name if branch else user.branch,
        employee_id=user.employee_id,
        department=user.department,
        designation=user.designation,
        selected_branch_id=branch.id if branch else None,
        selected_branch_name=branch.name if branch else None,
        email_verified=bool(user.email_verified),
        mfa_enabled=get_confirmed_authenticator(db, user.id) is not None,
    )


@router.get("/auth/capabilities")
def auth_capabilities() -> dict:
    return {
        "employee_portal_enabled": settings.employee_portal_enabled,
        "allowed_email_domains": settings.allowed_email_domain_list,
        "email_otp_enabled": settings.email_delivery_mode.strip().lower() in {"smtp", "console", "log"},
        "authenticator_enabled": True,
        "ticket_departments": sorted(VALID_TICKET_DEPARTMENTS),
    }


@router.get("/auth/branches", response_model=list[BranchResponse])
def public_branches(db: Session = Depends(get_db)) -> list[BranchResponse]:
    return [BranchResponse(id=item.id, code=item.code, name=item.name, address=item.address) for item in active_branches(db)]


@router.post("/auth/register/request-otp", response_model=OTPRequestResponse)
def request_registration_otp(payload: OTPRequest, request: Request, db: Session = Depends(get_db)) -> OTPRequestResponse:
    if not settings.employee_portal_enabled:
        raise HTTPException(status_code=503, detail="Employee registration is not enabled")
    email = ensure_allowed_email(str(payload.email))
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account already exists for this organization email. Use Login or Forgot Password.")
    code = issue_email_otp(db, email=email, purpose=REGISTRATION_PURPOSE, request=request)
    return OTPRequestResponse(
        message="A verification code has been sent to your organization email.",
        expires_in_seconds=settings.email_otp_expiry_minutes * 60,
        development_otp=code if not settings.is_production and settings.email_delivery_mode != "smtp" else None,
    )


@router.post("/auth/register/verify-otp", response_model=RegistrationOTPVerifyResponse)
def verify_registration_otp(payload: OTPVerifyRequest, request: Request, db: Session = Depends(get_db)) -> RegistrationOTPVerifyResponse:
    email = ensure_allowed_email(str(payload.email))
    verify_email_otp(db, email=email, purpose=REGISTRATION_PURPOSE, code=payload.otp, request=request)
    return RegistrationOTPVerifyResponse(
        registration_token=create_temporary_token(email, "registration_verified", extra={"email_verified": True})
    )


@router.post("/auth/register/complete", response_model=MFASetupResponse)
def complete_registration(
    payload: RegistrationCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MFASetupResponse:
    email, _claims = decode_temporary_subject(payload.registration_token, "registration_verified")
    ensure_allowed_email(email)
    validate_password_strength(payload.password)
    branch = get_branch(db, payload.branch_id)

    duplicate_employee = db.scalar(
        select(User).where(User.employee_id == payload.employee_id, func.lower(User.email) != email)
    )
    if duplicate_employee:
        raise HTTPException(status_code=409, detail="This employee ID is already registered")

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user:
        raise HTTPException(status_code=409, detail="An account already exists for this organization email. Use Login or Forgot Password.")
    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=EMPLOYEE_ROLE,
        branch=branch.name,
        employee_id=payload.employee_id,
        department=payload.department,
        designation=payload.designation,
        phone_number=payload.phone_number,
        email_verified=True,
        account_status="pending_mfa",
        mfa_required=True,
        is_active=False,
    )
    db.add(user)
    db.flush()

    access = db.scalar(
        select(UserBranchAccess).where(UserBranchAccess.user_id == user.id, UserBranchAccess.branch_id == branch.id)
    )
    if access is None:
        db.add(UserBranchAccess(user_id=user.id, branch_id=branch.id, is_default=True))
    else:
        access.is_default = True

    _credential, uri, qr = create_or_replace_authenticator(db, user)
    record_audit(
        db,
        event_type="ACCOUNT_REGISTRATION_COMPLETED",
        request=request,
        user=user,
        branch_id=branch.id,
        module="authentication",
        details={"status": "pending_mfa", "department": user.department},
    )
    db.commit()
    setup_token = create_temporary_token(email, "mfa_setup", role=user.role, extra={"uid": user.id})
    return MFASetupResponse(
        mfa_setup_token=setup_token,
        otpauth_uri=uri,
        qr_code_data_uri=qr,
        issuer=settings.totp_issuer,
        account_name=user.email,
    )


@router.post("/auth/mfa/confirm", response_model=LoginResponse)
def confirm_registration_mfa(
    payload: MFAConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    email, claims = decode_temporary_subject(payload.mfa_setup_token, "mfa_setup")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or int(claims.get("uid", 0)) != user.id:
        raise HTTPException(status_code=401, detail="The authenticator setup session is invalid")
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if not credential or credential.is_confirmed:
        raise HTTPException(status_code=401, detail="The authenticator setup session is no longer valid")
    if not confirm_totp_for_user(db, user, payload.code):
        record_audit(
            db,
            event_type="AUTHENTICATOR_SETUP_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    token, _session = issue_access_for_user(db, user=user, request=request)
    record_audit(db, event_type="AUTHENTICATOR_ENABLED", request=request, user=user, module="authentication")
    db.commit()
    return LoginResponse(
        access_token=token,
        user=_user_response(db, user),
        branch_selection_required=True,
    )


@router.post("/auth/mfa/verify-login", response_model=LoginResponse)
def verify_login_mfa(
    payload: MFALoginVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    email, claims = decode_temporary_subject(payload.pre_auth_token, "pre_auth")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not user.is_active or int(claims.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="The login verification session is invalid")
    if not verify_totp_for_user(db, user, payload.code):
        record_audit(
            db,
            event_type="MFA_LOGIN_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid authenticator code")
    token, _session = issue_access_for_user(db, user=user, request=request)
    return LoginResponse(
        access_token=token,
        user=_user_response(db, user),
        branch_selection_required=user.role == EMPLOYEE_ROLE,
    )


@router.post("/auth/forgot-password/request-otp", response_model=OTPRequestResponse)
def request_password_reset_otp(payload: OTPRequest, request: Request, db: Session = Depends(get_db)) -> OTPRequestResponse:
    email = normalize_email(str(payload.email))
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    development_otp = None
    if user and user.is_active and email.rsplit("@", 1)[-1] in settings.allowed_email_domain_list:
        code = issue_email_otp(db, email=email, purpose=PASSWORD_RESET_PURPOSE, request=request)
        if not settings.is_production and settings.email_delivery_mode != "smtp":
            development_otp = code
    else:
        record_audit(
            db,
            event_type="PASSWORD_RESET_REQUESTED",
            request=request,
            actor_email=email,
            result="accepted",
            module="authentication",
            details={"eligible": False},
        )
        db.commit()
    return OTPRequestResponse(
        message="If an eligible account exists, a verification code has been sent to the organization email.",
        expires_in_seconds=settings.email_otp_expiry_minutes * 60,
        development_otp=development_otp,
    )


@router.post("/auth/forgot-password/verify-otp", response_model=ForgotPasswordVerifyResponse)
def verify_password_reset_otp(
    payload: OTPVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ForgotPasswordVerifyResponse:
    email = ensure_allowed_email(str(payload.email))
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=400, detail="The OTP is invalid or has expired")
    verify_email_otp(db, email=email, purpose=PASSWORD_RESET_PURPOSE, code=payload.otp, request=request)
    return ForgotPasswordVerifyResponse(
        reset_token=create_temporary_token(email, "password_reset_verified", extra={"uid": user.id, "ver": user.token_version})
    )


@router.post("/auth/forgot-password/reset")
def reset_password(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email, claims = decode_temporary_subject(payload.reset_token, "password_reset_verified")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or int(claims.get("uid", 0)) != user.id or int(claims.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="The password reset session is invalid or has expired")
    validate_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    invalidate_all_sessions(db, user)
    record_audit(
        db,
        event_type="PASSWORD_RESET_COMPLETED",
        request=request,
        user=user,
        module="authentication",
    )
    db.commit()
    return {"message": "Password reset successfully. Sign in using your new password."}


@router.get("/auth/my-branches", response_model=list[BranchResponse])
def my_branches(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[BranchResponse]:
    return [BranchResponse(id=item.id, code=item.code, name=item.name, address=item.address) for item in get_user_branches(db, user)]


@router.post("/auth/select-branch", response_model=LoginResponse)
def select_branch(
    payload: BranchSelectionRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> LoginResponse:
    if not user_can_select_branch(db, auth.user, payload.branch_id):
        raise HTTPException(status_code=403, detail="You are not authorized to use this branch")
    branch = get_branch(db, payload.branch_id)
    token, _session = issue_access_for_user(
        db,
        user=auth.user,
        request=request,
        branch_id=branch.id,
        existing_session=auth.session,
    )
    record_audit(
        db,
        event_type="BRANCH_SELECTED",
        request=request,
        user=auth.user,
        branch_id=branch.id,
        module="authentication",
    )
    db.commit()
    return LoginResponse(
        access_token=token,
        user=_user_response(db, auth.user, branch.id),
        branch_selection_required=False,
    )


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    if auth.session and auth.session.ended_at is None:
        auth.session.ended_at = utc_now()
    auth.user.last_logout_at = utc_now()
    record_audit(db, event_type="LOGOUT", request=request, user=auth.user, module="authentication")
    db.commit()
    return {"message": "Logged out"}


@router.post("/audit/page-view", status_code=204)
def record_page_view(
    payload: AuditPageViewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> None:
    record_audit(
        db,
        event_type="MODULE_VISITED",
        request=request,
        user=auth.user,
        branch_id=selected_branch_id_from_claims(auth.claims),
        module=payload.path,
        details={"title": payload.title} if payload.title else None,
    )
    db.commit()


@router.post("/tickets", response_model=TicketDetailResponse)
def create_ticket(
    payload: TicketCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    department = payload.department.strip().lower()
    priority = payload.priority.strip().lower()
    if department not in VALID_TICKET_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Invalid ticket department")
    if priority not in VALID_TICKET_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid ticket priority")
    branch_id = selected_branch_id_from_claims(auth.claims)
    if branch_id is None:
        raise HTTPException(status_code=409, detail="Select a branch before raising a ticket")
    branch = get_branch(db, branch_id)
    ticket = SupportTicket(
        ticket_code=f"PENDING-{secrets.token_hex(12)}",
        requester_id=auth.user.id,
        branch_id=branch.id,
        department=department,
        category=payload.category.strip() if payload.category else None,
        title=payload.title.strip(),
        description=payload.description.strip(),
        priority=priority,
        location=payload.location.strip() if payload.location else None,
        asset_number=payload.asset_number.strip() if payload.asset_number else None,
    )
    db.add(ticket)
    db.flush()
    ticket.ticket_code = f"NT-{DEPARTMENT_CODES[department]}-{utc_now().year}-{ticket.id:05d}"
    db.add(TicketMessage(ticket_id=ticket.id, author_id=auth.user.id, message=payload.description.strip()))
    create_ticket_notifications(db, ticket, auth.user)
    record_audit(
        db,
        event_type="TICKET_CREATED",
        request=request,
        user=auth.user,
        branch_id=branch.id,
        module="tickets",
        target_type="ticket",
        target_id=ticket.id,
        details={"department": department, "priority": priority, "ticket_code": ticket.ticket_code},
    )
    db.commit()
    db.refresh(ticket)
    return serialize_ticket_detail(db, ticket, auth.user)


@router.get("/tickets", response_model=list[TicketSummaryResponse])
def list_tickets(
    department: str | None = Query(default=None),
    ticket_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    query = select(SupportTicket)
    if user.role == SOFTWARE_TEAM_ROLE:
        pass
    elif user.role == EMPLOYEE_ROLE or ticket_department_for_role(user.role) is None:
        query = query.where(SupportTicket.requester_id == user.id)
    else:
        query = query.where(SupportTicket.department == user.role)
    if department:
        normalized_department = department.strip().lower()
        if normalized_department not in VALID_TICKET_DEPARTMENTS:
            raise HTTPException(status_code=400, detail="Invalid department filter")
        query = query.where(SupportTicket.department == normalized_department)
    if ticket_status:
        normalized_status = ticket_status.strip().lower()
        if normalized_status not in VALID_TICKET_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query = query.where(SupportTicket.status == normalized_status)
    tickets = list(db.scalars(query.order_by(SupportTicket.updated_at.desc()).limit(500)).all())
    return [serialize_ticket_summary(db, ticket, user) for ticket in tickets]


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found")
    record_audit(
        db,
        event_type="TICKET_VIEWED",
        request=request,
        user=user,
        branch_id=ticket.branch_id,
        module="tickets",
        target_type="ticket",
        target_id=ticket.id,
    )
    db.commit()
    return serialize_ticket_detail(db, ticket, user)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketDetailResponse)
def add_ticket_message(
    ticket_id: int,
    payload: TicketMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.role == SOFTWARE_TEAM_ROLE and ticket.department != SOFTWARE_TEAM_ROLE and user.id != ticket.requester_id:
        raise HTTPException(status_code=403, detail="Software Team monitoring access is read-only for this department ticket")
    if user.id != ticket.requester_id and not can_handle_ticket(user, ticket):
        raise HTTPException(status_code=403, detail="You cannot reply to this ticket")
    message = TicketMessage(ticket_id=ticket.id, author_id=user.id, message=payload.message.strip())
    db.add(message)
    ticket.updated_at = utc_now()
    if user.id == ticket.requester_id:
        db.add(
            TicketNotification(
                ticket_id=ticket.id,
                recipient_role=ticket.department,
                notification_type="employee_reply",
                title=f"Employee replied to {ticket.ticket_code}",
                message=payload.message.strip()[:500],
            )
        )
        if ticket.department != SOFTWARE_TEAM_ROLE:
            db.add(
                TicketNotification(
                    ticket_id=ticket.id,
                    recipient_role=SOFTWARE_TEAM_ROLE,
                    notification_type="ticket_monitoring_update",
                    title=f"Update on {ticket.ticket_code}",
                    message="The employee added a reply.",
                )
            )
    else:
        notify_requester(
            db,
            ticket,
            notification_type="department_reply",
            title=f"New reply on {ticket.ticket_code}",
            message=payload.message.strip()[:500],
        )
    record_audit(
        db,
        event_type="TICKET_MESSAGE_ADDED",
        request=request,
        user=user,
        branch_id=ticket.branch_id,
        module="tickets",
        target_type="ticket",
        target_id=ticket.id,
    )
    db.commit()
    return serialize_ticket_detail(db, ticket, user)


@router.patch("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.id == ticket.requester_id and payload.status == "reopened" and ticket.status == "resolved":
        ticket.status = "reopened"
        ticket.resolved_at = None
    elif not can_handle_ticket(user, ticket):
        raise HTTPException(status_code=403, detail="Only the selected department can update this ticket")
    else:
        if payload.status is not None:
            normalized_status = payload.status.strip().lower()
            if normalized_status not in VALID_TICKET_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid ticket status")
            ticket.status = normalized_status
            if normalized_status == "resolved":
                ticket.resolved_at = utc_now()
            if normalized_status == "closed":
                ticket.closed_at = utc_now()
        if payload.priority is not None:
            normalized_priority = payload.priority.strip().lower()
            if normalized_priority not in VALID_TICKET_PRIORITIES:
                raise HTTPException(status_code=400, detail="Invalid ticket priority")
            ticket.priority = normalized_priority
        if payload.assign_to_self:
            ticket.assigned_to_id = user.id
            if ticket.status == "new":
                ticket.status = "assigned"
        if payload.resolution is not None:
            ticket.resolution = payload.resolution.strip() or None
    ticket.updated_at = utc_now()
    notify_requester(
        db,
        ticket,
        notification_type="ticket_updated",
        title=f"Ticket {ticket.ticket_code} updated",
        message=f"Status: {ticket.status.replace('_', ' ').title()}",
    )
    record_audit(
        db,
        event_type="TICKET_UPDATED",
        request=request,
        user=user,
        branch_id=ticket.branch_id,
        module="tickets",
        target_type="ticket",
        target_id=ticket.id,
        details={"status": ticket.status, "priority": ticket.priority},
    )
    db.commit()
    return serialize_ticket_detail(db, ticket, user)


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    conditions = [TicketNotification.recipient_user_id == user.id]
    if user.role == SOFTWARE_TEAM_ROLE:
        conditions.append(TicketNotification.recipient_role == SOFTWARE_TEAM_ROLE)
    elif ticket_department_for_role(user.role):
        conditions.append(TicketNotification.recipient_role == user.role)
    query = (
        select(TicketNotification, SupportTicket.ticket_code)
        .join(SupportTicket, SupportTicket.id == TicketNotification.ticket_id)
        .where(or_(*conditions))
        .order_by(TicketNotification.created_at.desc())
        .limit(200)
    )
    rows = db.execute(query).all()
    return [
        {
            "id": notification.id,
            "ticket_id": notification.ticket_id,
            "ticket_code": ticket_code,
            "notification_type": notification.notification_type,
            "title": notification.title,
            "message": notification.message,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
        }
        for notification, ticket_code in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    notification = db.get(TicketNotification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    allowed = notification.recipient_user_id == user.id or notification.recipient_role == user.role
    if user.role == SOFTWARE_TEAM_ROLE and notification.recipient_role == SOFTWARE_TEAM_ROLE:
        allowed = True
    if not allowed:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.get("/software/users", response_model=list[SoftwareUserResponse])
def software_users(
    db: Session = Depends(get_db),
    _software: User = Depends(require_roles(SOFTWARE_TEAM_ROLE)),
) -> list[SoftwareUserResponse]:
    users = list(db.scalars(select(User).order_by(User.created_at.desc()).limit(1000)).all())
    mfa_user_ids = set(
        db.scalars(
            select(AuthenticatorCredential.user_id).where(AuthenticatorCredential.is_confirmed.is_(True))
        ).all()
    )
    return [
        SoftwareUserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            employee_id=user.employee_id,
            department=user.department,
            designation=user.designation,
            phone_masked=mask_phone(user.phone_number),
            role=user.role,
            branch=user.branch,
            email_verified=bool(user.email_verified),
            account_status=user.account_status,
            mfa_enabled=user.id in mfa_user_ids,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            last_logout_at=user.last_logout_at,
            created_at=user.created_at,
        )
        for user in users
    ]


@router.get("/software/audit", response_model=list[AuditEventResponse])
def software_audit(
    event_type: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
    _software: User = Depends(require_roles(SOFTWARE_TEAM_ROLE)),
) -> list[dict]:
    query = select(AuditEvent, Branch.name).outerjoin(Branch, Branch.id == AuditEvent.branch_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type.strip().upper())
    if user_email:
        query = query.where(func.lower(AuditEvent.actor_email) == user_email.strip().lower())
    rows = db.execute(query.order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": event.id,
            "actor_email": event.actor_email,
            "event_type": event.event_type,
            "result": event.result,
            "branch_name": branch_name,
            "module": event.module,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "details": event.details,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "created_at": event.created_at,
        }
        for event, branch_name in rows
    ]


@router.post("/software/users/{user_id}/reset-authenticator")
def reset_user_authenticator(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    software: User = Depends(require_roles(SOFTWARE_TEAM_ROLE)),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
    if credential:
        db.delete(credential)
    user.mfa_required = True
    invalidate_all_sessions(db, user)
    record_audit(
        db,
        event_type="AUTHENTICATOR_RESET_BY_SOFTWARE_TEAM",
        request=request,
        user=software,
        module="authentication",
        target_type="user",
        target_id=user.id,
        details={"target_email": user.email},
    )
    db.commit()
    return {"message": "Authenticator reset. The user must enroll again at next login."}
