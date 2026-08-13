from __future__ import annotations

import json
import secrets
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth, get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.roles import EMPLOYEE_ROLE, SOFTWARE_TEAM_ROLE
from app.core.management_access import (
    FIRST_LOGIN_PRIVILEGED_ROLES,
    MANAGEMENT_ROLE,
    is_authorized_management_email,
    is_authorized_privileged_email,
)
from app.core.security import create_temporary_token, hash_password, verify_password
from app.models.entities import Asset, User, utc_now
from app.modules.employee_portal.models import (
    AuditEvent,
    AuthenticatorCredential,
    Branch,
    SupportTicket,
    TicketAttachment,
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
    ManagementPasswordChangeRequest,
    ManagementPasswordSetupRequest,
    NotificationResponse,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    PasswordResetRequest,
    RegistrationCompleteRequest,
    RegistrationOTPVerifyResponse,
    SoftwareUserResponse,
    TicketAssetResponse,
    TicketAttachmentResponse,
    TicketCatalogResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketMessageCreate,
    TicketPriorityPreviewRequest,
    TicketPriorityPreviewResponse,
    TicketSummaryResponse,
    TicketUpdateRequest,
)
from app.services.ticket_sla_service import build_ticket_sla_snapshot_map
from app.services.ticket_notification_service import (
    notify_ticket_created as notify_global_ticket_created,
    notify_ticket_department_reply as notify_global_ticket_department_reply,
    notify_ticket_reopened as notify_global_ticket_reopened,
    notify_ticket_requester_reply as notify_global_ticket_requester_reply,
    notify_ticket_status_to_requester as notify_global_ticket_status_to_requester,
)
from app.modules.employee_portal.service import (
    PASSWORD_RESET_PURPOSE,
    REGISTRATION_PURPOSE,
    DEPARTMENT_CODES,
    VALID_TICKET_DEPARTMENTS,
    VALID_TICKET_PRIORITIES,
    VALID_TICKET_STATUSES,
    TICKET_COMPONENT_CATALOG,
    active_branches,
    calculate_it_ticket_priority,
    can_handle_ticket,
    can_view_ticket,
    confirm_totp_for_user,
    create_or_replace_authenticator,
    create_ticket_notifications,
    decode_temporary_subject,
    deliver_ticket_lifecycle_emails,
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
    serialize_ticket_asset,
    serialize_ticket_detail,
    serialize_ticket_summary,
    ticket_catalog_payload,
    ticket_component_asset_tag,
    ticket_department_for_role,
    user_can_select_branch,
    validate_password_strength,
    verify_email_otp,
)
from app.modules.employee_portal.ticket_attachments import (
    TICKET_ATTACHMENT_MAX_BYTES,
    TICKET_ATTACHMENT_MAX_FILES,
    TicketAttachmentStorageError,
    TicketAttachmentValidationError,
    delete_ticket_attachment_object,
    store_ticket_attachment,
    stream_ticket_attachment,
    validate_ticket_attachment_bytes,
)
from app.schemas.auth import LoginResponse, UserResponse

router = APIRouter(tags=["Employee Portal"])


def _user_response(db: Session, user: User, branch_id: int | None = None, role_override: str | None = None) -> UserResponse:
    branch = db.get(Branch, branch_id) if branch_id else None
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role_override or user.role,
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
        details={
            "status": "pending_mfa",
            "department": user.department,
            "authentication": "email_otp_password_and_one_time_authenticator_activation",
        },
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

    privileged_setup = (
        user.role in FIRST_LOGIN_PRIVILEGED_ROLES
        and user.must_change_password
        and is_authorized_privileged_email(user.role, user.email)
    )
    if not confirm_totp_for_user(db, user, payload.code, activate_user=not privileged_setup):
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

    if privileged_setup:
        user.account_status = "pending_password_change"
        user.is_active = False
        user.mfa_required = False
        record_audit(
            db,
            event_type="PRIVILEGED_AUTHENTICATOR_VERIFIED",
            request=request,
            user=user,
            module="authentication",
            details={"role": user.role, "next_step": "create_permanent_password"},
        )
        db.commit()
        return LoginResponse(
            user=_user_response(db, user),
            password_change_required=True,
            password_change_token=create_temporary_token(
                user.email,
                "privileged_password_setup",
                role=user.role,
                extra={"uid": user.id},
            ),
        )

    # Authenticator verification is required once for account activation only.
    # Returning sign-ins use organization email and CRM password without TOTP.
    user.mfa_required = False
    record_audit(
        db,
        event_type="AUTHENTICATOR_REGISTRATION_VERIFIED",
        request=request,
        user=user,
        module="authentication",
        details={"login_requirement": "password_only"},
    )
    db.commit()
    token, _session = issue_access_for_user(db, user=user, request=request)
    return LoginResponse(
        access_token=token,
        user=_user_response(db, user),
        branch_selection_required=True,
    )


def _complete_privileged_setup(
    payload: ManagementPasswordSetupRequest,
    request: Request,
    db: Session,
    *,
    expected_role: str | None = None,
) -> LoginResponse:
    email, claims = decode_temporary_subject(payload.password_change_token, "privileged_password_setup")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    valid = (
        user is not None
        and int(claims.get("uid", 0)) == user.id
        and user.role in FIRST_LOGIN_PRIVILEGED_ROLES
        and is_authorized_privileged_email(user.role, user.email)
        and user.must_change_password
        and user.account_status == "pending_password_change"
        and (expected_role is None or user.role == expected_role)
    )
    if not valid or user is None:
        raise HTTPException(status_code=401, detail="The privileged password setup session is invalid")
    if get_confirmed_authenticator(db, user.id) is None:
        raise HTTPException(status_code=409, detail="Complete Authenticator verification before creating the password")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    validate_password_strength(payload.new_password)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The permanent password must be different from the temporary password")

    invalidate_all_sessions(db, user)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.mfa_required = False
    user.account_status = "active"
    user.is_active = True
    record_audit(
        db,
        event_type="PRIVILEGED_ACCOUNT_ACTIVATED",
        request=request,
        user=user,
        module="authentication",
        details={"role": user.role, "future_login": "email_and_permanent_password"},
    )
    db.commit()
    token, _session = issue_access_for_user(db, user=user, request=request)
    return LoginResponse(
        access_token=token,
        user=_user_response(db, user),
        branch_selection_required=False,
    )


@router.post("/auth/privileged/complete-setup", response_model=LoginResponse)
def complete_privileged_setup(
    payload: ManagementPasswordSetupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    return _complete_privileged_setup(payload, request, db)


@router.post("/auth/management/complete-setup", response_model=LoginResponse)
def complete_management_setup(
    payload: ManagementPasswordSetupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Backward-compatible endpoint for an in-progress Management setup."""
    return _complete_privileged_setup(payload, request, db, expected_role=MANAGEMENT_ROLE)


@router.post("/auth/management/change-password")
def change_management_password(
    payload: ManagementPasswordChangeRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = auth.user
    if user.role != MANAGEMENT_ROLE or not is_authorized_management_email(user.email):
        raise HTTPException(status_code=403, detail="Only an authorized Management account can use this action")
    if not verify_password(payload.current_password, user.password_hash):
        record_audit(
            db,
            event_type="MANAGEMENT_PASSWORD_CHANGE_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
            details={"reason": "invalid_current_password"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    validate_password_strength(payload.new_password)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    invalidate_all_sessions(db, user)
    user.password_hash = hash_password(payload.new_password)
    record_audit(
        db,
        event_type="MANAGEMENT_PASSWORD_CHANGED",
        request=request,
        user=user,
        module="authentication",
        details={"sessions_revoked": True},
    )
    db.commit()
    return {"message": "Password changed successfully. Sign in again using the new password."}


@router.post("/auth/mfa/verify-login", response_model=LoginResponse)
def verify_login_mfa(
    payload: MFALoginVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Authenticator codes are used only for first-time account activation. Sign in using email and password.",
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
        access_role=auth.effective_role,
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
        user=_user_response(db, auth.user, branch.id, auth.effective_role),
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


@router.get("/ticket-catalog", response_model=TicketCatalogResponse)
def get_ticket_catalog(user: User = Depends(get_current_user)) -> dict:
    return ticket_catalog_payload()


@router.post("/ticket-priority-preview", response_model=TicketPriorityPreviewResponse)
def preview_ticket_priority(
    payload: TicketPriorityPreviewRequest,
    user: User = Depends(get_current_user),
) -> dict:
    priority, reason, sla_target_minutes, problem_label = calculate_it_ticket_priority(
        payload.component.strip().lower(),
        payload.problem_code.strip().lower(),
        payload.impact.model_dump(),
    )
    return {
        "priority": priority,
        "priority_label": "Moderate" if priority == "medium" else priority.title(),
        "reason": reason,
        "sla_target_minutes": sla_target_minutes,
        "problem_label": problem_label,
    }


@router.get("/ticket-assets", response_model=list[TicketAssetResponse])
def search_ticket_assets(
    query: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Search active Asset Register records for ticket creation.

    This intentionally searches the current Asset Register rather than employee
    assignment links. The selected asset is validated again during ticket creation.
    """
    search_text = query.strip()
    if not search_text:
        return []
    pattern = f"%{search_text.lower()}%"
    excluded_statuses = {"disposed", "retired", "replaced"}
    rows = list(
        db.scalars(
            select(Asset)
            .where(
                func.lower(Asset.status).notin_(excluded_statuses),
                or_(
                    func.lower(func.coalesce(Asset.cpu_asset_tag, "")).like(pattern),
                    func.lower(Asset.asset_code).like(pattern),
                    func.lower(func.coalesce(Asset.workstation_no, "")).like(pattern),
                    func.lower(func.coalesce(Asset.system_name, "")).like(pattern),
                    func.lower(func.coalesce(Asset.used_by, "")).like(pattern),
                    func.lower(func.coalesce(Asset.monitor_asset_tags, "")).like(pattern),
                    func.lower(func.coalesce(Asset.mouse_asset_tag, "")).like(pattern),
                    func.lower(func.coalesce(Asset.keyboard_asset_tag, "")).like(pattern),
                ),
            )
            .order_by(func.coalesce(Asset.cpu_asset_tag, Asset.asset_code).asc(), Asset.asset_code.asc())
            .limit(limit)
        ).all()
    )
    return [serialize_ticket_asset(asset) for asset in rows]


@router.post("/tickets", response_model=TicketDetailResponse)
def create_ticket(
    payload: TicketCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    department = payload.department.strip().lower()
    if department not in VALID_TICKET_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="Invalid ticket department")

    requested_priority = (payload.priority or "medium").strip().lower()
    if requested_priority not in VALID_TICKET_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid ticket priority")

    branch_id = selected_branch_id_from_claims(auth.claims)
    if branch_id is None:
        raise HTTPException(status_code=409, detail="Select a branch before raising a ticket")
    branch = get_branch(db, branch_id)

    selected_asset = None
    asset_snapshot = None
    asset_number = payload.asset_number.strip() if payload.asset_number else None
    if payload.asset_id is not None:
        selected_asset = db.get(Asset, payload.asset_id)
        if not selected_asset:
            raise HTTPException(status_code=404, detail="The selected asset was not found")
        if selected_asset.status.strip().lower() in {"disposed", "retired", "replaced"}:
            raise HTTPException(status_code=409, detail="The selected asset is no longer active and cannot be used for a new ticket")
        snapshot_payload = serialize_ticket_asset(selected_asset)
        asset_snapshot = json.dumps(snapshot_payload, ensure_ascii=False)
        asset_number = selected_asset.cpu_asset_tag or selected_asset.asset_code
    elif department == "it":
        raise HTTPException(status_code=422, detail="Search and select the affected CPU / asset tag before submitting an IT ticket")

    component = None
    component_asset_tag = None
    problem_code = None
    problem_label = None
    impact_assessment = None
    priority_reason = None
    sla_target_minutes = None
    priority = requested_priority
    category = payload.category.strip() if payload.category else None

    if department == "it":
        component = (payload.component or "").strip().lower()
        problem_code = (payload.problem_code or "").strip().lower()
        if not component:
            raise HTTPException(status_code=422, detail="Select the affected system component")
        if not problem_code:
            raise HTTPException(status_code=422, detail="Select the exact problem")
        if payload.impact is None:
            raise HTTPException(status_code=422, detail="Complete the work-impact assessment")
        impact_payload = payload.impact.model_dump()
        priority, priority_reason, sla_target_minutes, problem_label = calculate_it_ticket_priority(
            component,
            problem_code,
            impact_payload,
        )
        component_asset_tag = ticket_component_asset_tag(selected_asset, component) if selected_asset else None
        impact_assessment = json.dumps(impact_payload, ensure_ascii=False)
        category = str(TICKET_COMPONENT_CATALOG[component]["label"])

    ticket = SupportTicket(
        ticket_code=f"PENDING-{secrets.token_hex(12)}",
        requester_id=auth.user.id,
        branch_id=branch.id,
        department=department,
        category=category,
        title=payload.title.strip(),
        description=payload.description.strip(),
        reporting_manager_email=str(payload.reporting_manager_email).strip().lower(),
        priority=priority,
        location=payload.location.strip() if payload.location else None,
        asset_number=asset_number,
        asset_id=selected_asset.id if selected_asset else None,
        asset_snapshot=asset_snapshot,
        component=component,
        component_asset_tag=component_asset_tag,
        problem_code=problem_code,
        problem_label=problem_label,
        impact_assessment=impact_assessment,
        priority_reason=priority_reason,
        sla_target_minutes=sla_target_minutes,
    )
    db.add(ticket)
    db.flush()
    ticket.ticket_code = f"NT-{DEPARTMENT_CODES[department]}-{utc_now().year}-{ticket.id:05d}"
    db.add(TicketMessage(ticket_id=ticket.id, author_id=auth.user.id, message=payload.description.strip()))
    create_ticket_notifications(db, ticket, auth.user)
    notify_global_ticket_created(
        db,
        ticket_id=ticket.id,
        ticket_code=ticket.ticket_code,
        department=ticket.department,
        priority=ticket.priority,
        title=ticket.title,
        requester_name=auth.user.full_name,
        event_token=ticket.created_at,
    )
    record_audit(
        db,
        event_type="TICKET_CREATED",
        request=request,
        user=auth.user,
        branch_id=branch.id,
        module="tickets",
        target_type="ticket",
        target_id=ticket.id,
        details={
            "department": department,
            "priority": priority,
            "priority_reason": priority_reason,
            "ticket_code": ticket.ticket_code,
            "reporting_manager_email": ticket.reporting_manager_email,
            "asset_id": ticket.asset_id,
            "asset_number": ticket.asset_number,
            "component": component,
            "component_asset_tag": component_asset_tag,
            "problem_code": problem_code,
            "problem_label": problem_label,
            "sla_target_minutes": sla_target_minutes,
        },
    )
    db.commit()
    db.refresh(ticket)
    background_tasks.add_task(deliver_ticket_lifecycle_emails, ticket.id, "created", auth.user.id)
    result = serialize_ticket_detail(db, ticket, auth.user, auth.effective_role)
    result.update(build_ticket_sla_snapshot_map(db, [ticket]).get(ticket.id, {}))
    return result


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=list[TicketAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
def upload_ticket_attachments(
    ticket_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(auth.user, ticket, auth.effective_role):
        raise HTTPException(status_code=404, detail="Ticket not found")
    if auth.user.id != ticket.requester_id:
        raise HTTPException(status_code=403, detail="Only the employee who raised the ticket can add ticket evidence")
    if not files:
        raise HTTPException(status_code=422, detail="Select at least one image to upload")

    existing_count = int(
        db.scalar(select(func.count(TicketAttachment.id)).where(TicketAttachment.ticket_id == ticket.id)) or 0
    )
    if existing_count + len(files) > TICKET_ATTACHMENT_MAX_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"A ticket can contain up to {TICKET_ATTACHMENT_MAX_FILES} images.",
        )

    validated = []
    for upload in files:
        data = upload.file.read(TICKET_ATTACHMENT_MAX_BYTES + 1)
        try:
            validated.append(
                validate_ticket_attachment_bytes(
                    filename=upload.filename,
                    declared_mime_type=upload.content_type,
                    data=data,
                )
            )
        except TicketAttachmentValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        finally:
            upload.file.close()

    stored_keys: list[str] = []
    created_rows: list[TicketAttachment] = []
    try:
        for item in validated:
            storage_key = store_ticket_attachment(ticket.id, item)
            stored_keys.append(storage_key)
            row = TicketAttachment(
                ticket_id=ticket.id,
                message_id=None,
                uploaded_by_id=auth.user.id,
                original_filename=item.original_filename,
                storage_key=storage_key,
                mime_type=item.mime_type,
                file_size=item.file_size,
            )
            db.add(row)
            created_rows.append(row)

        ticket.updated_at = utc_now()
        record_audit(
            db,
            event_type="TICKET_EVIDENCE_ADDED",
            request=request,
            user=auth.user,
            branch_id=ticket.branch_id,
            module="tickets",
            target_type="ticket",
            target_id=ticket.id,
            details={"attachment_count": len(created_rows)},
        )
        db.commit()
        for row in created_rows:
            db.refresh(row)
    except TicketAttachmentStorageError as exc:
        db.rollback()
        for storage_key in stored_keys:
            delete_ticket_attachment_object(storage_key)
        raise HTTPException(status_code=503, detail="Ticket was created, but image storage is temporarily unavailable.") from exc
    except Exception:
        db.rollback()
        for storage_key in stored_keys:
            delete_ticket_attachment_object(storage_key)
        raise

    return [
        {
            "id": row.id,
            "ticket_id": row.ticket_id,
            "message_id": row.message_id,
            "uploaded_by_id": row.uploaded_by_id,
            "uploaded_by_name": auth.user.full_name,
            "original_filename": row.original_filename,
            "mime_type": row.mime_type,
            "file_size": row.file_size,
            "created_at": row.created_at,
        }
        for row in created_rows
    ]


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}/content")
def get_ticket_attachment_content(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(auth.user, ticket, auth.effective_role):
        raise HTTPException(status_code=404, detail="Ticket not found")
    attachment = db.get(TicketAttachment, attachment_id)
    if not attachment or attachment.ticket_id != ticket.id:
        raise HTTPException(status_code=404, detail="Ticket attachment not found")

    try:
        stream = stream_ticket_attachment(attachment.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ticket attachment file not found") from exc
    except TicketAttachmentStorageError as exc:
        raise HTTPException(status_code=503, detail="Ticket evidence storage is temporarily unavailable") from exc

    encoded_name = quote(attachment.original_filename, safe="")
    return StreamingResponse(
        stream,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/tickets", response_model=list[TicketSummaryResponse])
def list_tickets(
    department: str | None = Query(default=None),
    ticket_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    user = auth.user
    role = auth.effective_role
    query = select(SupportTicket)
    if role in {SOFTWARE_TEAM_ROLE, MANAGEMENT_ROLE}:
        pass
    elif role == EMPLOYEE_ROLE or ticket_department_for_role(role) is None:
        query = query.where(SupportTicket.requester_id == user.id)
    else:
        query = query.where(SupportTicket.department == role)
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
    if role == EMPLOYEE_ROLE:
        ordering = (SupportTicket.updated_at.desc(), SupportTicket.id.desc())
    else:
        priority_order = case(
            (SupportTicket.priority == "critical", 0),
            (SupportTicket.priority == "high", 1),
            (SupportTicket.priority == "medium", 2),
            (SupportTicket.priority == "low", 3),
            else_=4,
        )
        ordering = (priority_order.asc(), SupportTicket.created_at.asc(), SupportTicket.id.asc())
    tickets = list(db.scalars(query.order_by(*ordering).limit(500)).all())
    sla_snapshots = build_ticket_sla_snapshot_map(db, tickets)
    payload = []
    for ticket in tickets:
        item = serialize_ticket_summary(db, ticket, user, role)
        item.update(sla_snapshots.get(ticket.id, {}))
        payload.append(item)
    if role != EMPLOYEE_ROLE:
        for queue_position, item in enumerate(payload, start=1):
            item["queue_position"] = queue_position
    return payload


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    user = auth.user
    role = auth.effective_role
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket, role):
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
    result = serialize_ticket_detail(db, ticket, user, role)
    result.update(build_ticket_sla_snapshot_map(db, [ticket]).get(ticket.id, {}))
    return result


@router.post("/tickets/{ticket_id}/messages", response_model=TicketDetailResponse)
def add_ticket_message(
    ticket_id: int,
    payload: TicketMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    user = auth.user
    role = auth.effective_role
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket, role):
        raise HTTPException(status_code=404, detail="Ticket not found")
    if (
        role in {SOFTWARE_TEAM_ROLE, MANAGEMENT_ROLE}
        and ticket.department != role
        and user.id != ticket.requester_id
    ):
        raise HTTPException(status_code=403, detail="Monitoring access is read-only for this department ticket")
    if user.id != ticket.requester_id and not can_handle_ticket(user, ticket, role):
        raise HTTPException(status_code=403, detail="You cannot reply to this ticket")
    message = TicketMessage(ticket_id=ticket.id, author_id=user.id, message=payload.message.strip())
    db.add(message)
    db.flush()
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
        notify_global_ticket_requester_reply(
            db,
            ticket_id=ticket.id,
            ticket_code=ticket.ticket_code,
            department=ticket.department,
            message_id=message.id,
            message_preview=payload.message,
        )
    else:
        notify_requester(
            db,
            ticket,
            notification_type="department_reply",
            title=f"New reply on {ticket.ticket_code}",
            message=payload.message.strip()[:500],
        )
        notify_global_ticket_department_reply(
            db,
            ticket_id=ticket.id,
            ticket_code=ticket.ticket_code,
            requester_user_id=ticket.requester_id,
            message_id=message.id,
            message_preview=payload.message,
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
    result = serialize_ticket_detail(db, ticket, user, role)
    result.update(build_ticket_sla_snapshot_map(db, [ticket]).get(ticket.id, {}))
    return result


@router.patch("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    user = auth.user
    role = auth.effective_role
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket, role):
        raise HTTPException(status_code=404, detail="Ticket not found")
    previous_status = ticket.status
    if user.id == ticket.requester_id and payload.status == "reopened" and ticket.status == "resolved":
        ticket.status = "reopened"
        ticket.resolved_at = None
    elif not can_handle_ticket(user, ticket, role):
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
    if previous_status == "resolved" and ticket.status == "reopened":
        notify_global_ticket_reopened(
            db,
            ticket_id=ticket.id,
            ticket_code=ticket.ticket_code,
            department=ticket.department,
            event_token=ticket.updated_at,
        )
    elif user.id != ticket.requester_id:
        notify_global_ticket_status_to_requester(
            db,
            ticket_id=ticket.id,
            ticket_code=ticket.ticket_code,
            requester_user_id=ticket.requester_id,
            status=ticket.status,
            event_token=ticket.updated_at,
            resolution=ticket.resolution,
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
    entered_terminal_status = previous_status not in {"resolved", "closed"} and ticket.status in {"resolved", "closed"}
    if entered_terminal_status:
        background_tasks.add_task(deliver_ticket_lifecycle_emails, ticket.id, "resolved", user.id)
    result = serialize_ticket_detail(db, ticket, user, role)
    result.update(build_ticket_sla_snapshot_map(db, [ticket]).get(ticket.id, {}))
    return result


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    user = auth.user
    role = auth.effective_role
    conditions = [TicketNotification.recipient_user_id == user.id]
    if role == SOFTWARE_TEAM_ROLE:
        conditions.append(TicketNotification.recipient_role == SOFTWARE_TEAM_ROLE)
    elif ticket_department_for_role(role):
        conditions.append(TicketNotification.recipient_role == role)
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
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    user = auth.user
    role = auth.effective_role
    notification = db.get(TicketNotification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    allowed = notification.recipient_user_id == user.id or notification.recipient_role == role
    if role == SOFTWARE_TEAM_ROLE and notification.recipient_role == SOFTWARE_TEAM_ROLE:
        allowed = True
    if not allowed:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.get("/software/users", response_model=list[SoftwareUserResponse])
def software_users(
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_roles(SOFTWARE_TEAM_ROLE, MANAGEMENT_ROLE)),
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
    _viewer: User = Depends(require_roles(SOFTWARE_TEAM_ROLE, MANAGEMENT_ROLE)),
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
    user.mfa_required = False
    invalidate_all_sessions(db, user)
    record_audit(
        db,
        event_type="AUTHENTICATOR_ENROLLMENT_CLEARED_BY_SOFTWARE_TEAM",
        request=request,
        user=software,
        module="authentication",
        target_type="user",
        target_id=user.id,
        details={"target_email": user.email},
    )
    db.commit()
    return {"message": "Authenticator enrollment record removed. Normal email-and-password sign-in remains available."}
