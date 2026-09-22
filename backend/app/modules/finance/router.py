from __future__ import annotations

from urllib.parse import quote
from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import utc_now
from app.modules.employee_portal.service import record_audit
from app.modules.finance.attachments import (
    FINANCE_ATTACHMENT_MAX_BYTES,
    FINANCE_ATTACHMENT_MAX_FILES,
    FINANCE_SETTLEMENT_ATTACHMENT_MAX_FILES,
    FinanceAttachmentStorageError,
    FinanceAttachmentValidationError,
    delete_finance_attachment_object,
    store_finance_attachment,
    stream_finance_attachment,
    validate_finance_attachment_bytes,
)
from app.modules.finance.models import ExpenseClaimAttachment, ExpenseSettlement, ExpenseSettlementAttachment, FinanceClient, FinanceProject
from app.modules.finance.schemas import (
    ExpenseClaimAttachmentResponse,
    ExpenseClaimCreateRequest,
    ExpenseClaimDecisionRequest,
    ExpenseClaimResponse,
    ExpenseClaimUpdateRequest,
    ExpensePaymentRequest,
    FinanceClientCreateRequest,
    FinanceClientProjectCreateRequest,
    FinanceClientProjectUpdateRequest,
    FinanceClientResponse,
    FinanceClientUpdateRequest,
    FinanceDashboardResponse,
    FinanceProjectResponse,
    FinanceProjectUserResponse,
    FinanceProjectStatusUpdate,
    FinanceProjectScheduleUpdate,
    FinanceReportResponse,
    SettlementAttachmentResponse,
    SettlementDecisionRequest,
    SettlementResponse,
    SettlementUpsertRequest,
)
from app.modules.finance.service import (
    ADMIN_ROLE,
    EMPLOYEE_ROLE,
    FINANCE_ROLE,
    MANAGEMENT_ROLE,
    VISIBLE_STAFF_ROLES,
    active_projects,
    all_projects,
    assigned_projects_for_user,
    client_payload,
    client_projects,
    create_client_project,
    create_finance_client,
    admin_decision,
    claim_payload,
    create_claim,
    dashboard_payload,
    deliver_finance_lifecycle_emails,
    finance_decision,
    get_visible_claim,
    list_visible_claims,
    list_finance_clients,
    mark_paid,
    project_payload,
    employee_project_payload,
    project_master_users,
    set_project_status,
    submit_claim,
    update_claim,
    update_client_project,
    update_finance_client,
)

from app.modules.finance.reporting import (
    build_finance_report_workbook,
    finance_report_filename,
    finance_report_payload,
)

from app.modules.finance.settlement_service import (
    EDITABLE_SETTLEMENT_STATUSES,
    admin_settlement_decision,
    finance_settlement_decision,
    deliver_finance_settlement_emails,
    get_visible_settlement,
    settlement_payload,
    submit_settlement,
    upsert_settlement,
)
from app.modules.finance.documents import build_all_bills_zip, build_claim_a4_pdf, build_complete_a4_pack
from app.modules.finance.client_master_io import (
    build_crm_workbook,
    client_tracking,
    import_client_master_workbook,
    project_tracking,
)
from app.modules.finance.sales_revenue_service import sales_revenue_overview

router = APIRouter(prefix="/finance", tags=["Finance CRM"])


def _role(auth: CurrentAuth) -> str:
    return auth.effective_role.strip().lower()


def _require_role(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=403, detail="Insufficient permission for this Finance action")


def _visible_claim_or_404(db: Session, auth: CurrentAuth, claim_id: int):
    claim = get_visible_claim(db, claim_id=claim_id, viewer=auth.user, effective_role=_role(auth))
    if claim is None:
        raise HTTPException(status_code=404, detail="Expense claim not found")
    return claim


def _xlsx_stream(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sales-revenue")
def get_sales_revenue_overview(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    """Read-only Sales/Revenue intelligence backed by the existing commercial and billing lifecycle."""
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return sales_revenue_overview(db)


@router.post("/client-master/import.xlsx")
async def import_client_master_excel(
    request: Request,
    file: UploadFile = File(...),
    overwrite_existing: bool = Query(default=False),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    filename = (file.filename or "client-master.xlsx").strip()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Upload an .xlsx Client Master workbook")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Client Master Excel must be 15 MB or smaller")
    try:
        result = import_client_master_workbook(
            db, raw=raw, actor=auth.user, source_name=filename, overwrite_existing=overwrite_existing
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Client Master import failed: {exc}") from exc
    record_audit(
        db, event_type="FINANCE_CLIENT_MASTER_EXCEL_IMPORTED", request=request, user=auth.user, module="finance",
        target_type="finance_client_master", details={
            "filename": filename, "created": result["created"], "updated": result["updated"],
            "skipped_existing": result["skipped_existing"], "skipped_incomplete": result["skipped_incomplete"],
            "overwrite_existing": overwrite_existing,
        },
    )
    db.commit()
    return result


@router.get("/client-master/export.xlsx")
def export_client_master_excel(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    data = build_crm_workbook(db)
    record_audit(db, event_type="FINANCE_CLIENT_MASTER_EXCEL_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="finance_client_master")
    db.commit()
    return _xlsx_stream(data, "Naksha_Client_Project_CRM_Master.xlsx")


@router.get("/project-master/export.xlsx")
def export_project_master_excel(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    data = build_crm_workbook(db)
    record_audit(db, event_type="FINANCE_PROJECT_MASTER_EXCEL_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="finance_project_master")
    db.commit()
    return _xlsx_stream(data, "Naksha_Project_Tracking_Master.xlsx")


@router.get("/clients", response_model=list[FinanceClientResponse])
def list_clients(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    rows = [client_payload(client) for client in list_finance_clients(db)]

    # Imported Client Master records may legitimately contain blank optional
    # values. Keep the database unchanged while honoring the existing API
    # string response contract used by the frontend.
    for row in rows:
        row["client_name"] = row.get("client_name") or ""
        row["contact_person_name"] = row.get("contact_person_name") or ""
        row["country"] = row.get("country") or ""

    return rows


@router.post("/clients", response_model=FinanceClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: FinanceClientCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    try:
        client = create_finance_client(db, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(
        db, event_type="FINANCE_CLIENT_CREATED", request=request, user=auth.user, module="finance",
        target_type="finance_client", target_id=client.id,
        details={"client_code": client.client_code, "client_name": client.client_name, "task": payload.task, "bd_name": payload.bd_name, "contact_person_email": payload.contact_person_email, "country": client.country, "source_team": client.source_team, "source_person_name": client.source_person_name},
    )
    db.commit(); db.refresh(client)
    return client_payload(client)


@router.put("/clients/{client_id}", response_model=FinanceClientResponse)
def update_client(
    client_id: int,
    payload: FinanceClientUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    client = update_finance_client(db, client=client, actor=auth.user, payload=payload)
    record_audit(
        db, event_type="FINANCE_CLIENT_UPDATED", request=request, user=auth.user, module="finance",
        target_type="finance_client", target_id=client.id,
        details={"client_code": client.client_code, "task": payload.task, "bd_name": payload.bd_name, "contact_person_email": payload.contact_person_email, "is_active": client.is_active},
    )
    db.commit(); db.refresh(client)
    return client_payload(client)


@router.get("/clients/{client_id}/tracking")
def get_client_tracking(
    client_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    return client_tracking(db, client)


@router.get("/clients/{client_id}/report.xlsx")
def export_client_detail_excel(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    data = build_crm_workbook(db, client_id=client.id)
    safe = client.client_code.replace("/", "-").replace("\\", "-")
    record_audit(db, event_type="FINANCE_CLIENT_DETAIL_EXCEL_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="finance_client", target_id=client.id, details={"client_code": client.client_code})
    db.commit()
    return _xlsx_stream(data, f"Client_{safe}_Detailed_Tracking.xlsx")


@router.get("/clients/{client_id}/projects", response_model=list[FinanceProjectResponse])
def list_client_projects(
    client_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    return [project_payload(project) for project in client_projects(db, client_id)]


@router.post("/clients/{client_id}/projects", response_model=FinanceProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project_for_client(
    client_id: int,
    payload: FinanceClientProjectCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    try:
        project = create_client_project(db, client=client, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(
        db, event_type="FINANCE_CLIENT_PROJECT_CREATED", request=request, user=auth.user, module="finance",
        target_type="finance_project", target_id=project.id,
        details={"client_code": client.client_code, "project_code": project.project_code, "project_name": project.project_name, "task": payload.task, "project_status": payload.project_status or ("active" if payload.is_active else "inactive"), "project_manager_id": project.master_profile.project_manager_id if project.master_profile else None, "project_manager_control": "bd_owned_read_only", "reporting_manager_id": payload.reporting_manager_id, "assigned_employee_ids": payload.assigned_employee_ids, "project_source_team": project.project_source_team, "project_source_person_name": project.project_source_person_name},
    )
    db.commit(); db.refresh(project)
    return project_payload(project)


@router.put("/clients/{client_id}/projects/{project_id}", response_model=FinanceProjectResponse)
def update_project_for_client(
    client_id: int,
    project_id: int,
    payload: FinanceClientProjectUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    project = db.get(FinanceProject, project_id)
    if project is None or project.client_id != client_id:
        raise HTTPException(status_code=404, detail="Finance project not found for this client")
    project = update_client_project(db, project=project, actor=auth.user, payload=payload)
    record_audit(
        db, event_type="FINANCE_CLIENT_PROJECT_UPDATED", request=request, user=auth.user, module="finance",
        target_type="finance_project", target_id=project.id,
        details={"project_code": project.project_code, "task": payload.task, "project_status": payload.project_status or ("active" if payload.is_active else "inactive"), "project_manager_id": project.master_profile.project_manager_id if project.master_profile else None, "project_manager_control": "bd_owned_read_only", "reporting_manager_id": payload.reporting_manager_id, "assigned_employee_ids": payload.assigned_employee_ids, "is_active": project.is_active},
    )
    db.commit(); db.refresh(project)
    return project_payload(project)


@router.get("/project-master/users", response_model=list[FinanceProjectUserResponse])
def list_project_master_users(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "employee_id": user.employee_id,
            "department": user.department,
            "designation": user.designation,
            "role": user.role,
        }
        for user in project_master_users(db)
    ]


@router.get("/projects", response_model=list[FinanceProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    role = _role(auth)
    if role not in {EMPLOYEE_ROLE, *VISIBLE_STAFF_ROLES}:
        raise HTTPException(status_code=403, detail="Finance project access is not available for this role")
    if role == EMPLOYEE_ROLE:
        # Least-privilege project selection: an employee can raise a project
        # expense only against projects to which the PM has assigned them.
        return [employee_project_payload(project) for project in assigned_projects_for_user(db, user_id=auth.user.id)]
    return [project_payload(project) for project in active_projects(db)]


@router.get("/report-projects", response_model=list[FinanceProjectResponse])
def list_report_projects(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return [project_payload(project) for project in all_projects(db)]




@router.patch("/projects/{project_id}/status", response_model=FinanceProjectResponse)
def update_project_status(
    project_id: int,
    payload: FinanceProjectStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Finance project not found")
    previous = project_payload(project)
    try:
        project = set_project_status(
            db, project=project, actor=auth.user, project_status=payload.project_status
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        event_type="FINANCE_PROJECT_STATUS_UPDATED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="finance_project",
        target_id=project.id,
        details={
            "project_code": project.project_code,
            "from_status": previous.get("project_status"),
            "to_status": payload.project_status,
            "client_id": project.client_id,
            "client_name": project.client.client_name if project.client else project.client_name,
        },
    )
    db.commit()
    db.refresh(project)
    return project_payload(project)


@router.get("/projects/{project_id}/tracking")
def get_project_tracking(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Finance project not found")
    return project_tracking(db, project)


@router.get("/projects/{project_id}/report.xlsx")
def export_project_detail_excel(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Finance project not found")
    data = build_crm_workbook(db, project_id=project.id)
    safe = project.project_code.replace("/", "-").replace("\\", "-")
    record_audit(db, event_type="FINANCE_PROJECT_DETAIL_EXCEL_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="finance_project", target_id=project.id, details={"project_code": project.project_code})
    db.commit()
    return _xlsx_stream(data, f"Project_{safe}_Detailed_Tracking.xlsx")


@router.put("/projects/{project_id}/schedule", response_model=FinanceProjectResponse)
def update_project_schedule(
    project_id: int,
    payload: FinanceProjectScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Finance project not found")
    project.start_date = payload.start_date
    project.end_date = payload.end_date
    project.is_active = payload.is_active
    project.updated_at = utc_now()
    record_audit(
        db, event_type="FINANCE_PROJECT_SCHEDULE_UPDATED", request=request, user=auth.user, module="finance",
        target_type="finance_project", target_id=project.id,
        details={"project_code": project.project_code, "start_date": payload.start_date.isoformat(), "end_date": payload.end_date.isoformat(), "is_active": payload.is_active},
    )
    db.commit(); db.refresh(project)
    return project_payload(project)


@router.get("/claims", response_model=list[ExpenseClaimResponse])
def list_claims(
    claim_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    role = _role(auth)
    if role not in {EMPLOYEE_ROLE, *VISIBLE_STAFF_ROLES}:
        raise HTTPException(status_code=403, detail="Finance claim access is not available for this role")
    claims = list_visible_claims(db, viewer=auth.user, effective_role=role, status=claim_status)
    return [claim_payload(db, claim, auth.user, role) for claim in claims]


@router.post("/claims", response_model=ExpenseClaimResponse, status_code=status.HTTP_201_CREATED)
def create_expense_claim(
    payload: ExpenseClaimCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, EMPLOYEE_ROLE)
    # V8: employees may raise expenses only against Project IDs assigned to them.
    # The existing Admin -> Finance -> Payment -> Settlement workflow remains unchanged.
    try:
        claim = create_claim(db, requester=auth.user, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        event_type="FINANCE_CLAIM_DRAFT_CREATED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={"claim_code": claim.claim_code},
    )
    db.commit()
    return claim_payload(db, claim, auth.user, _role(auth))


@router.put("/claims/{claim_id}", response_model=ExpenseClaimResponse)
def update_expense_claim(
    claim_id: int,
    payload: ExpenseClaimUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, EMPLOYEE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        claim = update_claim(db, claim=claim, requester=auth.user, payload=payload)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        event_type="FINANCE_CLAIM_UPDATED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
    )
    db.commit()
    return claim_payload(db, claim, auth.user, _role(auth))


@router.post("/claims/{claim_id}/submit", response_model=ExpenseClaimResponse)
def submit_expense_claim(
    claim_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, EMPLOYEE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        claim = submit_claim(db, claim=claim, requester=auth.user, request=request)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(deliver_finance_lifecycle_emails, claim.id, "submitted", auth.user.id)
    return claim_payload(db, claim, auth.user, _role(auth))


@router.get("/claims/{claim_id}", response_model=ExpenseClaimResponse)
def get_expense_claim(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    claim = _visible_claim_or_404(db, auth, claim_id)
    record_audit(
        db,
        event_type="FINANCE_CLAIM_VIEWED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
    )
    db.commit()
    return claim_payload(db, claim, auth.user, _role(auth))


@router.post("/claims/{claim_id}/admin-decision", response_model=ExpenseClaimResponse)
def decide_claim_as_admin(
    claim_id: int,
    payload: ExpenseClaimDecisionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    # Strict on purpose: Software Team's normal Admin-equivalent behavior does
    # not grant financial verification authority.
    _require_role(auth, ADMIN_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        claim = admin_decision(
            db, claim=claim, actor=auth.user, action=payload.action, comments=payload.comments,
            approved_work_start_date=payload.approved_work_start_date,
            approved_work_end_date=payload.approved_work_end_date,
            settlement_due_date=payload.settlement_due_date,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = "admin_approved" if payload.action == "approve" else "admin_sent_back" if payload.action == "send_back" else "admin_rejected"
    background_tasks.add_task(deliver_finance_lifecycle_emails, claim.id, event, auth.user.id)
    return claim_payload(db, claim, auth.user, _role(auth))


@router.post("/claims/{claim_id}/finance-decision", response_model=ExpenseClaimResponse)
def decide_claim_as_finance(
    claim_id: int,
    payload: ExpenseClaimDecisionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        claim = finance_decision(
            db, claim=claim, actor=auth.user, action=payload.action, comments=payload.comments,
            approved_value=payload.approved_amount,
            approved_work_start_date=payload.approved_work_start_date,
            approved_work_end_date=payload.approved_work_end_date,
            settlement_due_date=payload.settlement_due_date,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = "finance_approved" if payload.action == "approve" else "finance_sent_back" if payload.action == "send_back" else "finance_rejected"
    background_tasks.add_task(deliver_finance_lifecycle_emails, claim.id, event, auth.user.id)
    return claim_payload(db, claim, auth.user, _role(auth))


@router.post("/claims/{claim_id}/mark-paid", response_model=ExpenseClaimResponse)
def record_claim_payment(
    claim_id: int,
    payload: ExpensePaymentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        claim = mark_paid(
            db,
            claim=claim,
            actor=auth.user,
            payment_reference=payload.payment_reference,
            paid_amount=payload.paid_amount,
            payment_mode=payload.payment_mode,
            payment_date=payload.payment_date,
            comments=payload.comments,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(deliver_finance_lifecycle_emails, claim.id, "paid" if claim.status == "paid" else "partially_paid", auth.user.id)
    return claim_payload(db, claim, auth.user, _role(auth))


@router.get("/dashboard", response_model=FinanceDashboardResponse)
def finance_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    role = _role(auth)
    if role not in {EMPLOYEE_ROLE, *VISIBLE_STAFF_ROLES}:
        raise HTTPException(status_code=403, detail="Finance dashboard is not available for this role")
    return dashboard_payload(db, viewer=auth.user, effective_role=role)


@router.get("/reports", response_model=FinanceReportResponse)
def finance_reports(
    request: Request,
    period: str = Query(default="month"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    quarter: int | None = Query(default=None, ge=1, le=4),
    project_id: int | None = Query(default=None, ge=1),
    claim_type: str | None = Query(default=None),
    claim_status: str | None = Query(default=None, alias="status"),
    employee: str | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    try:
        payload = finance_report_payload(
            db,
            period=period,
            year=year,
            month=month,
            quarter=quarter,
            project_id=project_id,
            claim_type=claim_type,
            status=claim_status,
            employee_query=employee,
            category=category,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        event_type="FINANCE_REPORT_VIEWED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="finance_report",
        details={
            "period": payload["period"],
            "period_label": payload["period_label"],
            "project_id": project_id,
            "claim_type": claim_type,
            "status": claim_status,
            "category": category,
            "total_records": payload["total_records"],
        },
    )
    db.commit()
    return payload


@router.get("/reports/export.xlsx")
def export_finance_report(
    request: Request,
    period: str = Query(default="month"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    quarter: int | None = Query(default=None, ge=1, le=4),
    project_id: int | None = Query(default=None, ge=1),
    claim_type: str | None = Query(default=None),
    claim_status: str | None = Query(default=None, alias="status"),
    employee: str | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _require_role(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    try:
        output, resolved, record_count = build_finance_report_workbook(
            db,
            period=period,
            year=year,
            month=month,
            quarter=quarter,
            project_id=project_id,
            claim_type=claim_type,
            status=claim_status,
            employee_query=employee,
            category=category,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = finance_report_filename(resolved)
    record_audit(
        db,
        event_type="FINANCE_REPORT_EXPORTED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="finance_report",
        details={"period": resolved.period, "period_label": resolved.label, "filename": filename, "record_count": record_count},
    )
    db.commit()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/claims/{claim_id}/attachments",
    response_model=list[ExpenseClaimAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_claim_attachments(
    claim_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, EMPLOYEE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    if claim.requester_id != auth.user.id or claim.status not in {"draft", "admin_sent_back", "finance_sent_back"}:
        raise HTTPException(status_code=409, detail="Attachments can be changed only while the claim is editable")
    if not files:
        raise HTTPException(status_code=422, detail="Select at least one attachment")
    existing_count = len(claim.attachments)
    if existing_count + len(files) > FINANCE_ATTACHMENT_MAX_FILES:
        raise HTTPException(status_code=422, detail=f"A claim can contain at most {FINANCE_ATTACHMENT_MAX_FILES} attachments")

    validated = []
    for upload in files:
        try:
            data = await upload.read(FINANCE_ATTACHMENT_MAX_BYTES + 1)
            validated.append(
                validate_finance_attachment_bytes(
                    filename=upload.filename,
                    declared_mime_type=upload.content_type,
                    data=data,
                )
            )
        except FinanceAttachmentValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        finally:
            upload.file.close()

    stored_keys: list[str] = []
    created_rows: list[ExpenseClaimAttachment] = []
    try:
        for item in validated:
            storage_key = store_finance_attachment(claim.id, item)
            stored_keys.append(storage_key)
            row = ExpenseClaimAttachment(
                claim_id=claim.id,
                uploaded_by_id=auth.user.id,
                original_filename=item.original_filename,
                storage_key=storage_key,
                mime_type=item.mime_type,
                file_size=item.file_size,
                content_sha256=item.content_sha256,
            )
            db.add(row)
            created_rows.append(row)
        claim.updated_at = utc_now()
        record_audit(
            db,
            event_type="FINANCE_CLAIM_ATTACHMENT_ADDED",
            request=request,
            user=auth.user,
            module="finance",
            target_type="expense_claim",
            target_id=claim.id,
            details={"attachment_count": len(created_rows)},
        )
        db.commit()
        for row in created_rows:
            db.refresh(row)
    except FinanceAttachmentStorageError as exc:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise HTTPException(status_code=503, detail="Expense proof storage is temporarily unavailable") from exc
    except Exception:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise

    return [
        {
            "id": row.id,
            "original_filename": row.original_filename,
            "mime_type": row.mime_type,
            "file_size": row.file_size,
            "content_sha256": row.content_sha256,
            "uploaded_by_id": row.uploaded_by_id,
            "uploaded_by_name": auth.user.full_name,
            "created_at": row.created_at,
        }
        for row in created_rows
    ]


@router.delete("/claims/{claim_id}/attachments/{attachment_id}", status_code=204)
def delete_claim_attachment(
    claim_id: int,
    attachment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> None:
    _require_role(auth, EMPLOYEE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    if claim.requester_id != auth.user.id:
        raise HTTPException(status_code=403, detail="You can remove only your own draft expense proof")
    if claim.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Submitted expense proof is immutable for audit. Add corrected proof instead of deleting historical evidence.",
        )
    attachment = db.get(ExpenseClaimAttachment, attachment_id)
    if not attachment or attachment.claim_id != claim.id:
        raise HTTPException(status_code=404, detail="Expense attachment not found")
    storage_key = attachment.storage_key
    db.delete(attachment)
    record_audit(
        db,
        event_type="FINANCE_CLAIM_ATTACHMENT_REMOVED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={"attachment_id": attachment_id},
    )
    db.commit()
    delete_finance_attachment_object(storage_key)


@router.get("/claims/{claim_id}/attachments/{attachment_id}/content")
def get_claim_attachment_content(
    claim_id: int,
    attachment_id: int,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    claim = _visible_claim_or_404(db, auth, claim_id)
    attachment = db.get(ExpenseClaimAttachment, attachment_id)
    if not attachment or attachment.claim_id != claim.id:
        raise HTTPException(status_code=404, detail="Expense attachment not found")
    try:
        stream = stream_finance_attachment(attachment.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Expense attachment file not found") from exc
    except FinanceAttachmentStorageError as exc:
        raise HTTPException(status_code=503, detail="Expense proof storage is temporarily unavailable") from exc

    encoded_name = quote(attachment.original_filename, safe="")
    return StreamingResponse(
        stream,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f"{'attachment' if download else 'inline'}; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _visible_settlement_or_404(db: Session, auth: CurrentAuth, settlement_id: int):
    settlement = get_visible_settlement(db, settlement_id=settlement_id, viewer=auth.user, effective_role=_role(auth))
    if settlement is None:
        raise HTTPException(status_code=404, detail="Expense settlement not found")
    return settlement


@router.get("/claims/{claim_id}/settlement", response_model=SettlementResponse)
def get_claim_settlement(
    claim_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    claim = _visible_claim_or_404(db, auth, claim_id)
    if claim.claim_type != "advance":
        raise HTTPException(status_code=409, detail="Only an original Advance Request has a settlement")
    settlement = get_visible_settlement(db, root_claim_id=claim.id, viewer=auth.user, effective_role=_role(auth))
    if settlement is None:
        raise HTTPException(status_code=404, detail="Settlement has not been created yet")
    return settlement_payload(db, settlement, viewer=auth.user, effective_role=_role(auth))


@router.put("/claims/{claim_id}/settlement", response_model=SettlementResponse)
def save_claim_settlement(
    claim_id: int,
    payload: SettlementUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, EMPLOYEE_ROLE)
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        settlement = upsert_settlement(db, root_claim=claim, requester=auth.user, payload=payload, request=request)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return settlement_payload(db, settlement, viewer=auth.user, effective_role=_role(auth))


@router.post(
    "/settlements/{settlement_id}/attachments",
    response_model=list[SettlementAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_settlement_attachments(
    settlement_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    _require_role(auth, EMPLOYEE_ROLE)
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    if settlement.requester_id != auth.user.id or settlement.status not in EDITABLE_SETTLEMENT_STATUSES:
        raise HTTPException(status_code=409, detail="Settlement bills can be added only while the settlement is editable")
    if not files:
        raise HTTPException(status_code=422, detail="Select at least one bill or proof")
    if len(settlement.attachments) + len(files) > FINANCE_SETTLEMENT_ATTACHMENT_MAX_FILES:
        raise HTTPException(status_code=422, detail=f"A settlement can contain at most {FINANCE_SETTLEMENT_ATTACHMENT_MAX_FILES} bill/proof files")

    validated = []
    for upload in files:
        try:
            data = await upload.read(FINANCE_ATTACHMENT_MAX_BYTES + 1)
            validated.append(validate_finance_attachment_bytes(filename=upload.filename, declared_mime_type=upload.content_type, data=data))
        except FinanceAttachmentValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        finally:
            upload.file.close()

    stored_keys: list[str] = []
    rows: list[ExpenseSettlementAttachment] = []
    try:
        for item in validated:
            storage_key = store_finance_attachment(settlement.id, item, namespace="settlements")
            stored_keys.append(storage_key)
            row = ExpenseSettlementAttachment(
                settlement_id=settlement.id,
                uploaded_by_id=auth.user.id,
                original_filename=item.original_filename,
                storage_key=storage_key,
                mime_type=item.mime_type,
                file_size=item.file_size,
                content_sha256=item.content_sha256,
            )
            db.add(row)
            rows.append(row)
        settlement.updated_at = utc_now()
        record_audit(
            db,
            event_type="FINANCE_SETTLEMENT_ATTACHMENT_ADDED",
            request=request,
            user=auth.user,
            module="finance",
            target_type="expense_settlement",
            target_id=settlement.id,
            details={"attachment_count": len(rows)},
        )
        db.commit()
        for row in rows:
            db.refresh(row)
    except FinanceAttachmentStorageError as exc:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise HTTPException(status_code=503, detail="Settlement bill storage is temporarily unavailable") from exc
    except Exception:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise

    return [
        {
            "id": row.id,
            "original_filename": row.original_filename,
            "mime_type": row.mime_type,
            "file_size": row.file_size,
            "content_sha256": row.content_sha256,
            "uploaded_by_id": row.uploaded_by_id,
            "uploaded_by_name": auth.user.full_name,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.delete("/settlements/{settlement_id}/attachments/{attachment_id}", status_code=204)
def delete_settlement_attachment(
    settlement_id: int,
    attachment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> None:
    _require_role(auth, EMPLOYEE_ROLE)
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    if settlement.requester_id != auth.user.id or settlement.status not in EDITABLE_SETTLEMENT_STATUSES:
        raise HTTPException(status_code=409, detail="Submitted settlement proof is immutable for audit")
    attachment = db.get(ExpenseSettlementAttachment, attachment_id)
    if not attachment or attachment.settlement_id != settlement.id:
        raise HTTPException(status_code=404, detail="Settlement attachment not found")
    storage_key = attachment.storage_key
    db.delete(attachment)
    record_audit(db, event_type="FINANCE_SETTLEMENT_ATTACHMENT_REMOVED", request=request, user=auth.user, module="finance", target_type="expense_settlement", target_id=settlement.id, details={"attachment_id": attachment_id})
    db.commit()
    delete_finance_attachment_object(storage_key)


@router.get("/settlements/{settlement_id}/attachments/{attachment_id}/content")
def get_settlement_attachment_content(
    settlement_id: int,
    attachment_id: int,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    attachment = db.get(ExpenseSettlementAttachment, attachment_id)
    if not attachment or attachment.settlement_id != settlement.id:
        raise HTTPException(status_code=404, detail="Settlement attachment not found")
    try:
        stream = stream_finance_attachment(attachment.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Settlement attachment file not found") from exc
    except FinanceAttachmentStorageError as exc:
        raise HTTPException(status_code=503, detail="Settlement proof storage is temporarily unavailable") from exc
    encoded_name = quote(attachment.original_filename, safe="")
    return StreamingResponse(
        stream,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f"{'attachment' if download else 'inline'}; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/settlements/{settlement_id}/submit", response_model=SettlementResponse)
def submit_claim_settlement(
    settlement_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, EMPLOYEE_ROLE)
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    try:
        settlement = submit_settlement(db, settlement=settlement, requester=auth.user, request=request)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(deliver_finance_settlement_emails, settlement.id, "submitted", auth.user.id)
    return settlement_payload(db, settlement, viewer=auth.user, effective_role=_role(auth))


@router.post("/settlements/{settlement_id}/admin-decision", response_model=SettlementResponse)
def decide_settlement_as_admin(
    settlement_id: int,
    payload: SettlementDecisionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, ADMIN_ROLE)
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    try:
        settlement = admin_settlement_decision(db, settlement=settlement, actor=auth.user, action=payload.action, comments=payload.comments, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(deliver_finance_settlement_emails, settlement.id, f"admin_{'approved' if payload.action == 'approve' else 'sent_back' if payload.action == 'send_back' else 'rejected'}", auth.user.id)
    return settlement_payload(db, settlement, viewer=auth.user, effective_role=_role(auth))


@router.post("/settlements/{settlement_id}/finance-decision", response_model=SettlementResponse)
def decide_settlement_as_finance(
    settlement_id: int,
    payload: SettlementDecisionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require_role(auth, FINANCE_ROLE)
    settlement = _visible_settlement_or_404(db, auth, settlement_id)
    try:
        settlement = finance_settlement_decision(db, settlement=settlement, actor=auth.user, action=payload.action, comments=payload.comments, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(deliver_finance_settlement_emails, settlement.id, "finance_finalized" if payload.action == "approve" else "finance_sent_back" if payload.action == "send_back" else "finance_rejected", auth.user.id)
    return settlement_payload(db, settlement, viewer=auth.user, effective_role=_role(auth))


def _document_response(output, *, filename: str, media_type: str):
    return StreamingResponse(
        output,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/claims/{claim_id}/documents/report.pdf")
def download_claim_a4_report(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        output = build_claim_a4_pdf(db, claim)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The A4 Finance report could not be generated") from exc
    record_audit(db, event_type="FINANCE_A4_REPORT_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="expense_claim", target_id=claim.id, details={"claim_code": claim.claim_code})
    db.commit()
    return _document_response(output, filename=f"{claim.claim_code}_A4_Report.pdf", media_type="application/pdf")


@router.get("/claims/{claim_id}/documents/all-bills.zip")
def download_all_claim_bills(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        output = build_all_bills_zip(claim)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Supporting bills could not be packaged") from exc
    record_audit(db, event_type="FINANCE_ALL_BILLS_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="expense_claim", target_id=claim.id, details={"claim_code": claim.claim_code})
    db.commit()
    return _document_response(output, filename=f"{claim.claim_code}_All_Bills.zip", media_type="application/zip")


@router.get("/claims/{claim_id}/documents/a4-pack.pdf")
def download_complete_a4_pack(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    claim = _visible_claim_or_404(db, auth, claim_id)
    try:
        output = build_complete_a4_pack(db, claim)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The complete A4 bill pack could not be generated") from exc
    record_audit(db, event_type="FINANCE_A4_PACK_DOWNLOADED", request=request, user=auth.user, module="finance", target_type="expense_claim", target_id=claim.id, details={"claim_code": claim.claim_code})
    db.commit()
    return _document_response(output, filename=f"{claim.claim_code}_Complete_A4_Pack.pdf", media_type="application/pdf")
