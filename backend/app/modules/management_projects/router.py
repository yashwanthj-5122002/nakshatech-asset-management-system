"""Finance-only Management Projects, sharing the existing project and invoice engine."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import SUPPORTED_DEPARTMENTS, department_label, normalize_department_code
from app.models.entities import utc_now
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.commercial.service import freeze_baseline_on_finance_approval, upsert_baseline_estimate
from app.modules.employee_portal.service import record_audit
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.schemas import FinanceClientCreateRequest, FinanceClientProjectCreateRequest
from app.modules.finance.service import create_client_project, create_finance_client
from app.modules.management_clients.models import (
    ManagementClientIntake, ManagementAdditionalProjectRequest,
    ManagementProjectClassification,
)
from app.modules.management_projects.models import ManagementProjectLink
from app.modules.notifications.service import create_global_notification
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import (
    OrthoWorkPackage, ProjectWorkflow, ProjectWorkflowEvent,
    WorkPackageItem, WorkPackageItemActivity,
)
from app.modules.operations.production_items import (
    build_item_rows, file_aggregates_for_packages,
)
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.lifecycle_service import management_billing_status, management_source_approval_event
from app.modules.operations.schemas import WorkflowPMAssignment
from app.modules.operations.workflow_service import (
    WORKFLOW_FINANCE_APPROVED, assign_project_manager, email_project_manager_assignment,
    project_manager_options,
)

router = APIRouter(prefix="/finance/management-projects", tags=["Finance Management Projects"])


def _finance_only(auth: CurrentAuth) -> None:
    if (auth.effective_role or "").strip().lower() != "finance":
        raise HTTPException(status_code=403, detail="Finance access required")


 
class ManagementCommercialInput(ProjectCommercialInput):
    """Commercial input for Management Projects only."""

    estimated_amount: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=2
    )

    @model_validator(mode="after")
    def require_initial_commercial_terms(self):
        # Override the inherited mandatory payment-terms check.
        # ManagementProjectCreate validates the terms by project type.
        return self



class ManagementProjectCreate(BaseModel):
    management_client_id: int = Field(gt=0)
    additional_request_id: int | None = Field(default=None, gt=0)
    project_code: str = Field(min_length=2, max_length=80)
    project_name: str = Field(min_length=2, max_length=255)
    start_date: date
    end_date: date
    scope_text: str = Field(min_length=2, max_length=5000)
    performing_department_code: str
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")
    quantity: Decimal | None = Field(default=None, ge=0)
    quantity_unit: str = Field(default="unit", min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=5000)
    commercial: ManagementCommercialInput
    project_manager_id: int | None = Field(default=None, gt=0)
    project_type: str = Field(default="regular", pattern="^(regular|pilot)$")
    pilot_payment_type: str | None = Field(default=None, pattern="^(free|paid)$")

    @field_validator("project_code", mode="before")
    @classmethod
    def normalize_project_code(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        if any(c not in set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/. ") for c in value):
            raise ValueError("Unsupported Project ID characters")
        return value

    @field_validator("performing_department_code")
    @classmethod
    def validate_department(cls, value):
        code = normalize_department_code(value)
        if code is None:
            raise ValueError("Select an existing BD performing department")
        return code

    
   
    @model_validator(mode="after")
    def validate_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError(
                "End date cannot be earlier than start date"
            )

        amount = Decimal(str(self.commercial.estimated_amount))

        if self.project_type == "pilot":
            # Paid Pilots are no longer permitted.
            if self.pilot_payment_type not in (None, "free"):
                raise ValueError(
                    "All Pilot Projects must be Free Pilots"
                )

            # Automatically enforce Free Pilot.
            self.pilot_payment_type = "free"

            if amount != 0:
                raise ValueError(
                    "Pilot Project customer contract value must be zero"
                )

        else:
            # Preserve the existing Regular Project rules.
            if self.pilot_payment_type is not None:
                raise ValueError(
                    "Regular Projects cannot have a pilot payment type"
                )

            if amount <= 0:
                raise ValueError(
                    "Regular Projects require a positive commercial value"
                )
            
            if len((self.commercial.payment_terms or "").strip()) < 2:
                raise ValueError(
                    "Regular Projects require payment terms"
                )


        return self




def _client_payload(row: ManagementClientIntake) -> dict:
    return {
        "id": row.id, "client_code": row.client_code, "client_name": row.client_name,
        "source_person_name": row.source_person_name, "contact_person_name": row.contact_person_name,
        "client_email": row.client_email, "address": row.address, "gst_number": row.gst_number,
        "work_description": row.work_description, "is_active": row.is_active,
    }


def _project_payload(db: Session, link: ManagementProjectLink) -> dict:
    project = db.get(FinanceProject, link.project_id)
    workflow = db.get(ProjectWorkflow, link.project_id)
    if project is None or workflow is None:
        raise RuntimeError("Management project link points to an incomplete project")
    pm = project.master_profile.project_manager if project.master_profile else None
    classification = db.get(ManagementProjectClassification, project.id)
    return {
        "id": project.id, "management_client_id": link.management_client_id,
        "project_code": project.project_code, "project_name": project.project_name,
        "source_person_name": link.source_person_name,
        "project_type": classification.project_type if classification else "regular",
        "pilot_payment_type": classification.pilot_payment_type if classification else None,
        "department_code": workflow.performing_department_code,
        "department_label": department_label(workflow.performing_department_code),
        "workflow_status": management_billing_status(db, workflow),
        "source_approved": management_source_approval_event(db, project.id) is not None,
        "project_manager_id": pm.id if pm else None,
        "project_manager_name": pm.full_name if pm else None,
        "start_date": project.start_date, "end_date": project.end_date,
        "created_at": link.created_at,
        "project_value": float(workflow.commercial_value) if workflow.commercial_value is not None else None,
        "currency": workflow.currency or "INR",
    }


@router.get("")
def list_management_projects(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    clients = db.scalars(select(ManagementClientIntake).order_by(ManagementClientIntake.client_name)).all()
    links = db.scalars(select(ManagementProjectLink).order_by(ManagementProjectLink.created_at.desc())).all()
    return {"clients": [_client_payload(row) for row in clients], "projects": [_project_payload(db, row) for row in links]}



# The existing lifecycle dashboard's progress_percent is DELIVERY progress, not
# Production/QC/QA completion. This Finance-only read model uses the same
# per-file aggregation as the Production Tracking screen, without changing the
# operational engine, project statuses, invoices or permissions.
_TRACKING_STAGES = ("production", "qc", "qa", "delivery")


def _legacy_stage_counts(package: OrthoWorkPackage) -> dict[str, int]:
    """One legacy area = one work unit only when it has no active file children."""
    stage = (package.current_stage or "").lower()
    rework = stage == "production_rework"
    delivered = stage == "delivered" or package.delivered_at is not None
    production = (package.production_state or "").lower() == "completed" or stage in {
        "qc", "qa", "delivery_ready", "delivered",
    }
    qc = (package.qc_state or "").lower() in {"approved", "passed"} or stage in {
        "qa", "delivery_ready", "delivered",
    }
    qa = (package.qa_state or "").lower() in {"approved", "passed"} or stage in {
        "delivery_ready", "delivered",
    }
    return {
        "production": int(bool(production and not rework)),
        "qc": int(bool(qc and not rework)),
        "qa": int(bool(qa and not rework)),
        "delivery": int(bool(delivered)),
    }


def _tracking_rollup(packages: list[OrthoWorkPackage], aggregates: dict[int, dict],
                     last_activity_at=None) -> dict:
    """Stage percentages are per physical file (or legacy area), not km/quantity.

    Rework flags and file-completed counts come from the authoritative shared
    file_aggregates_for_packages function, which ignores inactive files and
    handles repeated attempts without counting the same file twice.
    """
    total = 0
    counts = dict.fromkeys(_TRACKING_STAGES, 0)
    in_progress = dict.fromkeys(_TRACKING_STAGES, 0)
    rework = 0
    active_files = 0
    legacy_areas = 0
    updated = last_activity_at
    for package in packages:
        if package.updated_at is not None and (updated is None or package.updated_at > updated):
            updated = package.updated_at
        agg = aggregates.get(package.id, {})
        expected = int(agg.get("files_expected") or 0)
        if expected:
            active_files += expected
            total += expected
            for stage, field in (("production", "files_production_done"),
                                 ("qc", "files_qc_passed"),
                                 ("qa", "files_qa_passed"),
                                 ("delivery", "files_delivered")):
                counts[stage] += int(agg.get(field) or 0)
            for stage in ("production", "qc", "qa"):
                in_progress[stage] += int(agg.get(f"{stage}_in_progress") or 0)
            # The shared aggregate can flag one rejected file in both
            # production_rework and qc_rework; count that file only once.
            rework += max(int(agg.get("production_rework") or 0),
                          int(agg.get("qc_rework") or 0)) + int(agg.get("qa_rework") or 0)
        elif int(agg.get("files_total") or 0) > 0:
            # Inactive-only file packages must not become fake legacy work units.
            continue
        else:
            legacy_areas += 1
            total += 1
            legacy = _legacy_stage_counts(package)
            for stage in _TRACKING_STAGES:
                counts[stage] += legacy[stage]
            if (package.current_stage or "").lower() == "production_rework":
                rework += 1
            if (package.current_stage or "").lower() == "production":
                in_progress["production"] += 1
    stages = {
        stage: {
            "completed": counts[stage], "total": total,
            "percent": round(100 * counts[stage] / total, 1) if total else 0.0,
            "in_progress": in_progress[stage],
        }
        for stage in _TRACKING_STAGES
    }
    overall = round(100 * sum(counts.values()) / (4 * total), 1) if total else 0.0
    if not total:
        operational_status = "Awaiting work allocation"
    elif rework:
        operational_status = "Rework in progress"
    elif counts["delivery"] == total:
        operational_status = "Delivered"
    elif counts["qa"] == total:
        operational_status = "Ready for delivery"
    elif counts["qa"] or in_progress["qa"]:
        operational_status = "QA in progress"
    elif counts["qc"] == total:
        operational_status = "Ready for QA"
    elif counts["qc"] or in_progress["qc"]:
        operational_status = "QC in progress"
    elif counts["production"] == total:
        operational_status = "Production complete - QC pending"
    elif counts["production"] or in_progress["production"]:
        operational_status = "Production in progress"
    else:
        operational_status = "Assigned - work not started"
    return {
        "overall_percent": overall, "operational_status": operational_status,
        "work_units": total, "active_files": active_files, "legacy_areas": legacy_areas,
        "rework_count": rework, "stages": stages,
        "last_activity_at": updated.isoformat() if updated is not None else None,
    }


def _project_packages(db: Session, project_ids: list[int]) -> dict[int, list[OrthoWorkPackage]]:
    if not project_ids:
        return {}
    rows = db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.project_id.in_(project_ids)
    ).order_by(OrthoWorkPackage.project_id, OrthoWorkPackage.id)).all()
    result: dict[int, list[OrthoWorkPackage]] = {project_id: [] for project_id in project_ids}
    for row in rows:
        result[row.project_id].append(row)
    return result


@router.get("/tracking")
def management_project_tracking(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    """Read-only Finance tracking for management-linked projects, bulk and no BD access."""
    _finance_only(auth)
    project_ids = list(db.scalars(select(ManagementProjectLink.project_id)).all())
    by_project = _project_packages(db, project_ids)
    all_packages = [package for rows in by_project.values() for package in rows]
    aggregates = file_aggregates_for_packages(db, [package.id for package in all_packages])
    last_activities = {}
    if project_ids:
        activity_rows = db.execute(select(
            WorkPackageItemActivity.project_id,
            func.max(WorkPackageItemActivity.updated_at),
        ).where(WorkPackageItemActivity.project_id.in_(project_ids)).group_by(
            WorkPackageItemActivity.project_id,
        )).all()
        last_activities = dict(activity_rows)
    return {
        "as_of": utc_now().isoformat(),
        "projects": {
            str(project_id): _tracking_rollup(
                by_project[project_id], aggregates, last_activities.get(project_id),
            )
            for project_id in project_ids
        },
    }


@router.get("/{project_id}/tracking")
def management_project_tracking_detail(
    project_id: int, db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Per-file tracking, restricted to a real management project link."""
    _finance_only(auth)
    if db.get(ManagementProjectLink, project_id) is None:
        raise HTTPException(status_code=404, detail="Management project not found")
    packages = _project_packages(db, [project_id]).get(project_id, [])
    package_ids = [package.id for package in packages]
    aggregates = file_aggregates_for_packages(db, package_ids)
    rows = build_item_rows(db, package_ids)
    active_packages = {row["work_package_id"] for row in rows if row["is_active"]}
    package_by_id = {package.id: package for package in packages}
    file_rows = []
    for row in rows:
        package = package_by_id[row["work_package_id"]]
        file_rows.append({
            "work_package_item_id": row["work_package_item_id"],
            "package_code": package.package_code,
            "item_number": row["item_number"], "item_name": row.get("item_name"),
            "is_active": row["is_active"], "tracking_basis": "file_activity",
            "production": "rework" if row.get("production_rework_pending") else row["production_status"],
            "qc": row["qc_status"], "qa": row["qa_status"],
            "delivery": row["delivery_status"],
            "production_completed_at": row.get("production_completed_at"),
            "qc_completed_at": row.get("qc_end"),
            "qa_completed_at": row.get("qa_end"),
            "delivered_at": row.get("delivery_at"),
            "production_employee": row.get("production_employee"),
            "qc_employee": row.get("qc_employee"),
            "qa_employee": row.get("qa_employee"),
        })
    for package in packages:
        if package.id in active_packages:
            continue
        # Legacy area-only packages use their existing stage fields. If there
        # are only inactive files, they do not inflate the active file count.
        if any(row["work_package_id"] == package.id for row in rows):
            continue
        stage = (package.current_stage or "").lower()
        legacy = _legacy_stage_counts(package)
        file_rows.append({
            "work_package_item_id": None,
            "package_code": package.package_code,
            "item_number": package.package_code,
            "item_name": package.package_name,
            "is_active": True, "tracking_basis": "legacy_area",
            "production": "rework" if stage == "production_rework" else ("completed" if legacy["production"] else package.production_state),
            "qc": "passed" if legacy["qc"] else package.qc_state,
            "qa": "passed" if legacy["qa"] else package.qa_state,
            "delivery": "delivered" if legacy["delivery"] else "pending",
            "production_completed_at": package.production_completed_at.isoformat() if package.production_completed_at else None,
            "qc_completed_at": package.qc_submitted_at.isoformat() if package.qc_submitted_at else None,
            "qa_completed_at": package.qa_submitted_at.isoformat() if package.qa_submitted_at else None,
            "delivered_at": package.delivered_at.isoformat() if package.delivered_at else None,
            "production_employee": None, "qc_employee": None, "qa_employee": None,
        })
    return {
        "project_id": project_id, "as_of": utc_now().isoformat(),
        "summary": _tracking_rollup(packages, aggregates),
        "files": file_rows,
    }

def _amount_inr(amount: Decimal, currency: str | None, stored_inr: Decimal | None, rate: Decimal | None) -> Decimal | None:
    """Use the recorded accounting/realization FX, never a guessed live rate."""
    if stored_inr is not None:
        return Decimal(stored_inr)
    if (currency or "INR").upper() == "INR":
        return Decimal(amount)
    if rate is not None and Decimal(rate) > 0:
        return Decimal(amount) * Decimal(rate)
    return None


@router.get("/summary")
def management_project_summary(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    """Management-only invoice/payment aggregates in INR, sourced from existing ledgers.

    Draft/cancelled invoices are not treated as issued revenue. Unconverted foreign
    currency rows are reported, not silently converted using an invented rate.
    """
    _finance_only(auth)
    project_ids = list(db.scalars(select(ManagementProjectLink.project_id)).all())
    zero = {"invoice_count": 0, "invoiced_inr": 0.0, "received_inr": 0.0,
            "outstanding_inr": 0.0, "missing_fx_rows": 0}
    if not project_ids:
        return {"projects": {}, "totals": {**zero, "collection_rate": 0.0}}

    invoices = list(db.scalars(select(ProjectInvoice).where(ProjectInvoice.project_id.in_(project_ids))).all())
    invoice_ids = [row.id for row in invoices]
    payments = list(db.scalars(select(ProjectInvoicePayment).where(
        ProjectInvoicePayment.invoice_id.in_(invoice_ids)
    )).all()) if invoice_ids else []
    by_invoice: dict[int, list[ProjectInvoicePayment]] = {}
    for payment in payments:
        by_invoice.setdefault(payment.invoice_id, []).append(payment)
    stats: dict[int, dict] = {pid: {**zero, "settled_inr": 0.0} for pid in project_ids}
    for invoice in invoices:
        target = stats[invoice.project_id]
        target["invoice_count"] += 1
        if invoice.status in {"INVOICE_DRAFT", "CANCELLED", "CANCELED"}:
            continue
        currency = (invoice.currency or "INR").upper()
        total = Decimal(invoice.amount or 0) + Decimal(invoice.tax_amount or 0)
        invoice_total_inr = _amount_inr(total, currency, invoice.total_inr, invoice.fx_rate_to_inr)
        if invoice_total_inr is None:
            target["missing_fx_rows"] += 1
        else:
            target["invoiced_inr"] += float(invoice_total_inr)
        paid_at_invoice_rate = Decimal("0")
        paid_is_complete = True
        for payment in by_invoice.get(invoice.id, []):
            paid_inr = _amount_inr(
                Decimal(payment.amount), payment.payment_currency or currency,
                payment.inr_equivalent, payment.fx_rate_to_inr,
            )
            if paid_inr is None:
                target["missing_fx_rows"] += 1
            else:
                target["received_inr"] += float(paid_inr)
            applied_inr = _amount_inr(
                Decimal(payment.amount), currency,
                payment.invoice_inr_equivalent, invoice.fx_rate_to_inr,
            )
            if applied_inr is None:
                paid_is_complete = False
            else:
                paid_at_invoice_rate += applied_inr
        if invoice_total_inr is not None and paid_is_complete:
            applied = min(invoice_total_inr, paid_at_invoice_rate)
            target["settled_inr"] += float(applied)
            target["outstanding_inr"] += float(max(Decimal("0"), invoice_total_inr - applied))
        elif invoice_total_inr is not None:
            target["missing_fx_rows"] += 1

    totals = {key: sum(item[key] for item in stats.values()) for key in
              ("invoice_count", "invoiced_inr", "received_inr", "outstanding_inr", "missing_fx_rows", "settled_inr")}
    totals["collection_rate"] = round(
        100 * totals["settled_inr"] / totals["invoiced_inr"], 1
    ) if totals["invoiced_inr"] else 0.0
    for item in stats.values():
        item.pop("settled_inr")
    totals.pop("settled_inr")
    return {"projects": {str(key): value for key, value in stats.items()}, "totals": totals}


@router.get("/assignment-options")
def assignment_options(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    return {
        "departments": [{"code": code, "label": department_label(code)} for code in SUPPORTED_DEPARTMENTS],
        "project_managers_by_department": {code: project_manager_options(db, department_code=code) for code in SUPPORTED_DEPARTMENTS},
    }


def _finance_client_for_intake(db: Session, intake: ManagementClientIntake, auth: CurrentAuth) -> FinanceClient:
    # The intake is the sole authority for client/source data. No user-supplied source is trusted.
    client = db.scalar(select(FinanceClient).where(FinanceClient.client_code == intake.client_code).with_for_update())
    if client is not None:
        if client.source_team != "management":
            raise ValueError("Client code is already owned by a non-management Finance client")
        if not client.is_active:
            raise ValueError("Finance client is inactive")
        return client
    return create_finance_client(db, actor=auth.user, payload=FinanceClientCreateRequest(
        client_code=intake.client_code, client_name=intake.client_name,
        client_email=intake.client_email, organization_email=intake.organization_email,
        contact_person_name=intake.contact_person_name,
        contact_person_phone=intake.contact_person_phone,
        contact_person_email=intake.contact_person_email,
        task=intake.work_description, address=intake.address,
        description=intake.work_description, country=intake.country,
        gst_number=intake.gst_number, source_team="management",
        source_person_name=intake.source_person_name, bd_name=None,
    ))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_management_project(
    payload: ManagementProjectCreate, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    try:
        intake = db.get(ManagementClientIntake, payload.management_client_id)
        if intake is None or not intake.is_active:
            raise ValueError("Select an active management-registered client")
        request_row = None
        if payload.additional_request_id is not None:
            request_row = db.scalar(select(ManagementAdditionalProjectRequest).where(
                ManagementAdditionalProjectRequest.id == payload.additional_request_id,
            ).with_for_update())
            if request_row is None or request_row.management_client_id != intake.id:
                raise HTTPException(status_code=409, detail="Project request does not belong to this client")
            if request_row.status != "PENDING" or request_row.created_project_id is not None:
                raise HTTPException(status_code=409, detail="Project request was already processed")
        if request_row is not None:
            if (
                (request_row.project_type or "regular") != payload.project_type
                or request_row.pilot_payment_type != payload.pilot_payment_type
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Project classification must match the Management request",
                )

        client = _finance_client_for_intake(db, intake, auth)
        project = create_client_project(db, client=client, actor=auth.user, payload=FinanceClientProjectCreateRequest(
            project_code=payload.project_code, project_name=payload.project_name,
            task=payload.scope_text, project_status="active", is_active=True,
            project_source_team="management", project_source_person_name=intake.source_person_name,
            start_date=payload.start_date, end_date=payload.end_date,
            description=payload.description,
        ))
        now = utc_now()
        workflow = ProjectWorkflow(
            project_id=project.id, bd_owner_user_id=auth.user.id,
            status=WORKFLOW_FINANCE_APPROVED,
            performing_department_code=payload.performing_department_code,
            scope_text=payload.scope_text, quantity=payload.quantity,
            quantity_unit=payload.quantity_unit, priority=payload.priority,
            commercial_value=payload.commercial.estimated_amount,
            currency=payload.commercial.currency_code,
            po_wo_number=payload.commercial.po_wo_reference,
            attachment_references="[]", finance_reviewer_id=auth.user.id,
            finance_reviewed_at=now, approved_at=now,
            created_by_id=auth.user.id, updated_by_id=auth.user.id,
        )
        db.add(workflow)
        db.add(ManagementProjectLink(
            project_id=project.id, management_client_id=intake.id,
            finance_client_id=client.id, source_person_name=intake.source_person_name,
            created_by_id=auth.user.id,
        ))
        db.add(ManagementProjectClassification(
            project_id=project.id,
            project_type=payload.project_type,
            pilot_payment_type=payload.pilot_payment_type,
        ))
        db.flush()
        db.add(ProjectWorkflowEvent(
            project_id=project.id, event_type="management_finance_project_created",
            from_status=None, to_status=WORKFLOW_FINANCE_APPROVED,
            comments="Finance created and approved a management-sourced project",
            actor_user_id=auth.user.id,
        ))
        upsert_baseline_estimate(db, actor=auth.user, project_id=project.id, payload=payload.commercial)
        freeze_baseline_on_finance_approval(db, actor=auth.user, project_id=project.id)
        if payload.project_manager_id is not None:
            assign_project_manager(
                db, actor=auth.user, project_id=project.id,
                payload=WorkflowPMAssignment(project_manager_id=payload.project_manager_id),
                allow_management_finance=True,
            )
        record_audit(db, event_type="MANAGEMENT_PROJECT_CREATED_BY_FINANCE", request=request,
                     user=auth.user, module="finance", target_type="finance_project",
                     target_id=str(project.id), details={
                         "management_client_id": intake.id, "source_person_name": intake.source_person_name,
                         "department": payload.performing_department_code,
                         "project_manager_id": payload.project_manager_id,
                         "additional_request_id": request_row.id if request_row else None,
                          "project_type": payload.project_type,
                          "pilot_payment_type": payload.pilot_payment_type,
                     })
        if request_row is not None:
            request_row.status = "CREATED"
            request_row.created_project_id = project.id
            request_row.completed_by_id = auth.user.id
            request_row.completed_at = utc_now()
            # Resolve the specific Finance action prompt when its request is fulfilled.
            for note in db.scalars(select(GlobalNotification).where(
                GlobalNotification.dedupe_key == f"mgmt_add_project_request_{request_row.id}",
                GlobalNotification.resolved_at.is_(None),
            )).all():
                note.resolved_at = utc_now()
                note.resolved_by_id = auth.user.id
                note.resolution_note = "Project created"
                note.requires_action = False
            record_audit(db, event_type="MANAGEMENT_ADDITIONAL_PROJECT_CREATED", request=request,
                user=auth.user, module="finance", target_type="management_additional_project_request",
                target_id=str(request_row.id), details={"project_id": project.id, "client_id": intake.id})
            create_global_notification(db,
                event_type="management.additional_project.created", category="system",
                title="Requested Management project has been created",
                message=f"Finance created {project.project_code} for {intake.client_code} ({request_row.project_name}).",
                target_url="/management/project-management", recipient_user_ids=[request_row.requested_by_id],
                dedupe_key=f"mgmt_add_project_created_{request_row.id}", severity="success",
                metadata={"request_id": request_row.id, "project_id": project.id})
        db.commit()
        if payload.project_manager_id is not None:
            email_project_manager_assignment(db, project_id=project.id, pm_id=payload.project_manager_id)
        return {"project_id": project.id, "project_code": project.project_code,
                "workflow_status": workflow.status}
    except HTTPException:
        db.rollback()
        raise
    except (ValueError, PermissionError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Client or Project ID already exists") from exc
    except Exception:
        db.rollback()
        raise


@router.post("/{project_id}/assign-pm")
def assign_management_pm(
    project_id: int, payload: WorkflowPMAssignment, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    if db.get(ManagementProjectLink, project_id) is None:
        raise HTTPException(status_code=404, detail="Management project not found")
    try:
        workflow, pm = assign_project_manager(
            db, actor=auth.user, project_id=project_id, payload=payload,
            allow_management_finance=True,
        )
        record_audit(db, event_type="MANAGEMENT_PROJECT_PM_ASSIGNED_BY_FINANCE", request=request,
                     user=auth.user, module="finance", target_type="finance_project",
                     target_id=str(project_id), details={"project_manager_id": pm.id})
        db.commit()
        email_project_manager_assignment(db, project_id=project_id, pm_id=pm.id)
        return {"project_id": project_id, "project_manager_id": pm.id, "workflow_status": workflow.status}
    except (ValueError, PermissionError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


# NAKSHA_MGMT_NEW_PROJECT_REQUEST_V1 - Finance-only pending queue.
@router.get("/additional-project-requests")
def list_finance_additional_project_requests(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    rows = db.scalars(select(ManagementAdditionalProjectRequest).order_by(
        ManagementAdditionalProjectRequest.created_at.desc(),
        ManagementAdditionalProjectRequest.id.desc(),
    )).all()
    result = []
    for row in rows:
        intake = db.get(ManagementClientIntake, row.management_client_id)
        project = db.get(FinanceProject, row.created_project_id) if row.created_project_id else None
        result.append({
            "id": row.id, "management_client_id": row.management_client_id,
            "client_code": intake.client_code if intake else "",
            "client_name": intake.client_name if intake else "",
            "source_person_name": intake.source_person_name if intake else "",
            "project_name": row.project_name, "scope_text": row.scope_text,
            "expected_start_date": row.expected_start_date.date().isoformat() if row.expected_start_date else None,
            "remarks": row.remarks, "status": row.status,
            "project_type": row.project_type or "regular",
            "pilot_payment_type": row.pilot_payment_type,
            "created_project_id": row.created_project_id,
            "created_project_code": project.project_code if project else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        })
    return result
