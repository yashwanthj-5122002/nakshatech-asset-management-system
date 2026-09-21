from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.roles import (
    ADMIN_ROLE,
    BD_ROLE,
    FINANCE_ROLE,
    MANAGEMENT_ROLE,
    role_is_allowed,
)
from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import User, utc_now
from app.modules.business.models import BusinessRecord, BusinessRecordHistory
from app.modules.business.schemas import (
    BusinessBillingSuggestion,
    BusinessBreakdownRow,
    BusinessHistoryEntry,
    BusinessMonthPoint,
    BusinessOverview,
    BusinessRecordRow,
    BusinessRecordUpsertRequest,
    BusinessTotals,
)
from app.modules.finance.models import FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkstream
from app.modules.operations.service import TECHNICAL_DEPARTMENT_LABELS, TECHNICAL_ROLE_DEPARTMENT_MAP

ENTER_ROLES = {FINANCE_ROLE, ADMIN_ROLE}
TOTALS_ROLES = {FINANCE_ROLE, BD_ROLE, MANAGEMENT_ROLE, ADMIN_ROLE}
DEFAULT_DEPARTMENT = "ortho"
TRACKED_AMOUNT_FIELDS = ("amount_total", "amount_released", "amount_pending")
HISTORY_MONTHS = 12


def _month_label(month: str) -> str:
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return month


def _month_bounds(month: str) -> tuple[date, date]:
    year, month_number = (int(part) for part in month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    return date(year, month_number, 1), date(year, month_number, last_day)


def _department_label(code: str | None) -> str:
    if not code:
        return "Unassigned"
    return TECHNICAL_DEPARTMENT_LABELS.get(code, code.replace("_", " ").title())


def _is_project_manager(db: Session, user_id: int) -> bool:
    workstream = db.scalar(
        select(ProjectWorkstream.id).where(
            ProjectWorkstream.project_manager_user_id == user_id,
            ProjectWorkstream.is_active.is_(True),
        ).limit(1)
    )
    if workstream is not None:
        return True
    profile = db.scalar(
        select(FinanceProjectMasterProfile.project_id).where(
            FinanceProjectMasterProfile.project_manager_id == user_id
        ).limit(1)
    )
    return profile is not None


def _available_months(db: Session) -> list[str]:
    return list(db.scalars(select(BusinessRecord.reporting_month).distinct().order_by(BusinessRecord.reporting_month.desc())))


def _billing_suggestions(db: Session, *, project_ids: list[int], month: str) -> dict[int, BusinessBillingSuggestion]:
    """Month-dated figures straight from Billing & Invoices.

    Total    = invoices dated inside the month (amount + tax)
    Released = payments dated inside the month
    Pending  = total - released (never negative)
    """
    if not project_ids:
        return {}
    start, end = _month_bounds(month)

    invoice_rows = db.execute(
        select(
            ProjectInvoice.project_id,
            func.coalesce(func.sum(ProjectInvoice.amount + func.coalesce(ProjectInvoice.tax_amount, 0)), 0),
            func.count(ProjectInvoice.id),
            func.min(ProjectInvoice.currency),
        ).where(
            ProjectInvoice.project_id.in_(project_ids),
            ProjectInvoice.invoice_date >= start,
            ProjectInvoice.invoice_date <= end,
        ).group_by(ProjectInvoice.project_id)
    ).all()
    payment_rows = db.execute(
        select(
            ProjectInvoicePayment.project_id,
            func.coalesce(func.sum(ProjectInvoicePayment.amount), 0),
            func.count(ProjectInvoicePayment.id),
        ).where(
            ProjectInvoicePayment.project_id.in_(project_ids),
            ProjectInvoicePayment.payment_date >= start,
            ProjectInvoicePayment.payment_date <= end,
        ).group_by(ProjectInvoicePayment.project_id)
    ).all()

    payments = {int(project_id): (int(count), Decimal(amount)) for project_id, amount, count in payment_rows}
    suggestions: dict[int, BusinessBillingSuggestion] = {}
    for project_id, invoiced, invoice_count, currency in invoice_rows:
        payment_count, paid = payments.get(int(project_id), (0, Decimal("0.00")))
        total = Decimal(invoiced)
        currency = currency or "INR"
        suggestions[int(project_id)] = BusinessBillingSuggestion(
            total=float(total),
            released=float(paid),
            pending=float(max(Decimal("0.00"), total - paid)),
            currency=currency,
            invoice_count=int(invoice_count),
            payment_count=payment_count,
        )
    # Projects that only received a payment in the month (no invoice dated that month).
    for project_id, (payment_count, paid) in payments.items():
        if project_id not in suggestions:
            suggestions[project_id] = BusinessBillingSuggestion(
                total=0.0, released=float(paid), pending=0.0, currency="INR", invoice_count=0, payment_count=payment_count
            )
    return suggestions


def _project_attribution(db: Session, projects: list[FinanceProject]) -> dict[int, dict]:
    """Resolve each project's PM + department once, avoiding per-project queries."""
    project_ids = [project.id for project in projects]
    if not project_ids:
        return {}

    workstreams = list(db.scalars(
        select(ProjectWorkstream).where(
            ProjectWorkstream.project_id.in_(project_ids),
            ProjectWorkstream.is_active.is_(True),
        ).order_by(ProjectWorkstream.department_code, ProjectWorkstream.sequence_order)
    ).all())
    workstream_map: dict[int, ProjectWorkstream] = {}
    for row in workstreams:
        if row.project_manager_user_id is None:
            continue
        current = workstream_map.get(row.project_id)
        # Prefer the Ortho workstream, otherwise the earliest sequence with a PM set.
        if current is None or (row.department_code == DEFAULT_DEPARTMENT and current.department_code != DEFAULT_DEPARTMENT):
            workstream_map[row.project_id] = row

    user_ids: set[int] = set()
    for project in projects:
        profile = project.master_profile
        if profile is not None and profile.project_manager_id is not None:
            user_ids.add(profile.project_manager_id)
    for row in workstream_map.values():
        if row.project_manager_user_id is not None:
            user_ids.add(row.project_manager_user_id)
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}

    attribution: dict[int, dict] = {}
    for project in projects:
        profile = project.master_profile
        pm_id: int | None = None
        department_code = DEFAULT_DEPARTMENT
        if profile is not None and profile.project_manager_id is not None:
            pm_id = profile.project_manager_id
        elif project.id in workstream_map:
            pm_id = workstream_map[project.id].project_manager_user_id
            department_code = workstream_map[project.id].department_code
        manager = users.get(pm_id) if pm_id is not None else None
        if manager is not None and manager.role:
            department_code = TECHNICAL_ROLE_DEPARTMENT_MAP.get(manager.role.strip().lower(), department_code)
        attribution[project.id] = {
            "project_manager_user_id": pm_id,
            "project_manager_name": manager.full_name if manager else None,
            "department_code": department_code,
        }
    return attribution


def _project_rows(
    db: Session,
    *,
    month: str,
    only_pm_user_id: int | None = None,
) -> list[BusinessRecordRow]:
    records = {
        record.project_id: record
        for record in db.scalars(select(BusinessRecord).where(BusinessRecord.reporting_month == month)).all()
    }

    # Always include active projects for entry, plus any project that already has a
    # recorded month so historic business never disappears when a project is closed.
    statement = (
        select(FinanceProject)
        .options(selectinload(FinanceProject.master_profile), selectinload(FinanceProject.client))
        .order_by(FinanceProject.project_code, FinanceProject.id)
    )
    if records:
        statement = statement.where(
            or_(FinanceProject.is_active.is_(True), FinanceProject.id.in_(list(records)))
        )
    else:
        statement = statement.where(FinanceProject.is_active.is_(True))
    projects = list(db.scalars(statement).all())

    attribution = _project_attribution(db, projects)
    suggestions = _billing_suggestions(db, project_ids=[project.id for project in projects], month=month)

    rows: list[BusinessRecordRow] = []
    for project in projects:
        info = attribution.get(project.id, {})
        record = records.get(project.id)
        pm_id = info.get("project_manager_user_id")
        if only_pm_user_id is not None:
            if pm_id != only_pm_user_id and (record is None or record.project_manager_user_id != only_pm_user_id):
                continue
        rows.append(_row_payload(
            project,
            info,
            record,
            suggestions.get(project.id, BusinessBillingSuggestion()),
        ))
    return rows


def _row_payload(
    project: FinanceProject,
    info: dict,
    record: BusinessRecord | None,
    billing: BusinessBillingSuggestion,
) -> BusinessRecordRow:
    client = project.client
    department_code = record.department_code if record is not None else info.get("department_code", DEFAULT_DEPARTMENT)
    return BusinessRecordRow(
        record_id=record.id if record is not None else None,
        project_id=project.id,
        project_code=project.project_code,
        project_name=project.project_name,
        client_id=(record.client_id if record is not None and record.client_id is not None else (client.id if client else None)),
        client_code=client.client_code if client else None,
        client_name=client.client_name if client else project.client_name,
        project_manager_user_id=(record.project_manager_user_id if record is not None and record.project_manager_user_id is not None else info.get("project_manager_user_id")),
        project_manager_name=(record.project_manager_name if record is not None and record.project_manager_name else info.get("project_manager_name")),
        department_code=department_code,
        department_label=_department_label(department_code),
        amount_total=float(record.amount_total) if record is not None else 0.0,
        amount_released=float(record.amount_released) if record is not None else 0.0,
        amount_pending=float(record.amount_pending) if record is not None else 0.0,
        currency=record.currency if record is not None else billing.currency,
        notes=record.notes if record is not None else None,
        status=record.status if record is not None else "submitted",
        verified_at=record.verified_at if record is not None else None,
        updated_at=record.updated_at if record is not None else None,
        billing=billing,
    )


def _totals(rows: list[BusinessRecordRow]) -> BusinessTotals:
    currency = rows[0].currency if rows else "INR"
    return BusinessTotals(
        total=sum(row.amount_total for row in rows),
        released=sum(row.amount_released for row in rows),
        pending=sum(row.amount_pending for row in rows),
        currency=currency,
    )


def _breakdown(rows: list[BusinessRecordRow], dimension: str) -> list[BusinessBreakdownRow]:
    entered = [row for row in rows if row.record_id is not None]
    buckets: dict[str, BusinessBreakdownRow] = {}
    for row in entered:
        if dimension == "department":
            key, label = row.department_code, row.department_label
        elif dimension == "project_manager":
            key = str(row.project_manager_user_id) if row.project_manager_user_id is not None else "unassigned"
            label = row.project_manager_name or "Unassigned"
        else:
            key = str(row.client_id) if row.client_id is not None else "unknown"
            label = row.client_name or "Unknown client"
        bucket = buckets.get(key)
        if bucket is None:
            bucket = BusinessBreakdownRow(key=key, label=label)
            buckets[key] = bucket
        bucket.total += row.amount_total
        bucket.released += row.amount_released
        bucket.pending += row.amount_pending
        bucket.project_count += 1
    return sorted(buckets.values(), key=lambda item: (item.total, item.label), reverse=True)


def _my_monthly_history(db: Session, user_id: int) -> list[BusinessMonthPoint]:
    records = list(db.scalars(
        select(BusinessRecord).where(BusinessRecord.project_manager_user_id == user_id)
    ).all())
    buckets: dict[str, BusinessMonthPoint] = {}
    for record in records:
        point = buckets.get(record.reporting_month)
        if point is None:
            point = BusinessMonthPoint(month=record.reporting_month, label=_month_label(record.reporting_month))
            buckets[record.reporting_month] = point
        point.total += float(record.amount_total)
        point.released += float(record.amount_released)
        point.pending += float(record.amount_pending)
    ordered = sorted(buckets.values(), key=lambda item: item.month)
    return ordered[-HISTORY_MONTHS:]


def business_overview(db: Session, *, actor: User, role: str, month: str | None) -> BusinessOverview:
    normalized_month = normalize_reporting_month(month)
    effective = (role or "").strip().lower()
    can_enter = role_is_allowed(effective, ENTER_ROLES)

    if role_is_allowed(effective, TOTALS_ROLES):
        if role_is_allowed(effective, ENTER_ROLES):
            viewer = "finance"
        elif effective == MANAGEMENT_ROLE:
            viewer = "management"
        else:
            viewer = "bd"
        rows = _project_rows(db, month=normalized_month)
        return BusinessOverview(
            month=normalized_month,
            viewer=viewer,
            can_enter=can_enter,
            totals=_totals(rows),
            by_department=_breakdown(rows, "department"),
            by_project_manager=_breakdown(rows, "project_manager"),
            by_client=_breakdown(rows, "client"),
            rows=rows,
            months=_available_months(db),
        )

    if _is_project_manager(db, actor.id):
        rows = _project_rows(db, month=normalized_month, only_pm_user_id=actor.id)
        return BusinessOverview(
            month=normalized_month,
            viewer="project_manager",
            can_enter=False,
            totals=_totals(rows),
            rows=rows,
            months=_available_months(db),
            my_monthly_history=_my_monthly_history(db, actor.id),
        )

    return BusinessOverview(month=normalized_month, viewer="unavailable", can_enter=False)


def _write_history(
    db: Session,
    *,
    record: BusinessRecord,
    action: str,
    actor: User,
    role: str,
    changes: dict | None,
) -> None:
    db.add(BusinessRecordHistory(
        record_id=record.id,
        reporting_month=record.reporting_month,
        project_id=record.project_id,
        client_id=record.client_id,
        project_manager_user_id=record.project_manager_user_id,
        action=action,
        actor_user_id=actor.id,
        actor_name=actor.full_name,
        actor_role=(role or "").strip().lower() or None,
        changes=json.dumps(changes, ensure_ascii=True, separators=(",", ":")) if changes else None,
    ))


def _amount_value(value: float) -> Decimal:
    return Decimal(str(round(float(value), 2)))


def upsert_business_record(
    db: Session,
    *,
    actor: User,
    role: str,
    payload: BusinessRecordUpsertRequest,
) -> BusinessRecord:
    if not role_is_allowed((role or "").strip().lower(), ENTER_ROLES):
        raise HTTPException(status_code=403, detail="Only Finance can record monthly business figures")

    month = normalize_reporting_month(payload.reporting_month)
    project = db.get(FinanceProject, payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    attribution = _project_attribution(db, [project]).get(project.id, {})
    requested_department = (payload.department_code or "").strip().lower()
    department_code = requested_department or attribution.get("department_code") or DEFAULT_DEPARTMENT

    record = db.scalar(
        select(BusinessRecord).where(
            BusinessRecord.project_id == project.id,
            BusinessRecord.reporting_month == month,
        )
    )

    if record is None:
        record = BusinessRecord(
            project_id=project.id,
            reporting_month=month,
            client_id=project.client_id,
            project_manager_user_id=attribution.get("project_manager_user_id"),
            project_manager_name=attribution.get("project_manager_name"),
            department_code=department_code,
            currency=payload.currency,
            notes=payload.notes,
            entered_by_id=actor.id,
            status="submitted",
        )
        db.add(record)
        db.flush()
        changes: dict = {}
        for field in TRACKED_AMOUNT_FIELDS:
            value = _amount_value(getattr(payload, field))
            setattr(record, field, value)
            if value != Decimal("0.00"):
                changes[field] = {"from": None, "to": str(value)}
        if payload.notes:
            changes["notes"] = {"from": None, "to": payload.notes}
        if payload.currency != "INR":
            changes["currency"] = {"from": "INR", "to": payload.currency}
        _write_history(db, record=record, action="created", actor=actor, role=role, changes=changes or None)
    else:
        if record.client_id is None:
            record.client_id = project.client_id
        if record.project_manager_user_id is None:
            record.project_manager_user_id = attribution.get("project_manager_user_id")
            record.project_manager_name = attribution.get("project_manager_name")
        if requested_department:
            record.department_code = requested_department
        changes = {}
        for field in TRACKED_AMOUNT_FIELDS:
            previous = getattr(record, field)
            value = _amount_value(getattr(payload, field))
            if previous != value:
                changes[field] = {"from": str(previous), "to": str(value)}
                setattr(record, field, value)
        if (record.notes or None) != (payload.notes or None):
            changes["notes"] = {"from": record.notes, "to": payload.notes}
            record.notes = payload.notes
        if record.currency != payload.currency:
            changes["currency"] = {"from": record.currency, "to": payload.currency}
            record.currency = payload.currency
        record.entered_by_id = actor.id
        if changes and record.status == "verified":
            # An edit invalidates a previous verification until it is re-verified.
            record.status = "submitted"
            record.verified_by_id = None
            record.verified_at = None
            changes["status"] = {"from": "verified", "to": "submitted"}
        if changes:
            _write_history(db, record=record, action="updated", actor=actor, role=role, changes=changes)

    db.commit()
    db.refresh(record)
    return record


def set_month_verified(
    db: Session,
    *,
    actor: User,
    role: str,
    month: str,
    verified: bool,
) -> int:
    if not role_is_allowed((role or "").strip().lower(), {ADMIN_ROLE, MANAGEMENT_ROLE}):
        raise HTTPException(status_code=403, detail="Only Management or Admin can verify a business month")

    normalized_month = normalize_reporting_month(month)
    records = list(db.scalars(select(BusinessRecord).where(BusinessRecord.reporting_month == normalized_month)).all())

    for record in records:
        if verified:
            if record.status != "verified":
                record.status = "verified"
                record.verified_by_id = actor.id
                record.verified_at = utc_now()
                _write_history(db, record=record, action="verified", actor=actor, role=role,
                               changes={"status": {"from": "submitted", "to": "verified"}})
        else:
            if record.status != "submitted":
                record.status = "submitted"
                record.verified_by_id = None
                record.verified_at = None
                _write_history(db, record=record, action="updated", actor=actor, role=role,
                               changes={"status": {"from": "verified", "to": "submitted"}})
    if records:
        db.commit()
    return len(records)


def record_row(db: Session, record: BusinessRecord) -> BusinessRecordRow:
    project = db.get(FinanceProject, record.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    attribution = _project_attribution(db, [project]).get(project.id, {})
    billing = _billing_suggestions(db, project_ids=[project.id], month=record.reporting_month).get(
        project.id, BusinessBillingSuggestion()
    )
    return _row_payload(project, attribution, record, billing)


def record_history(db: Session, *, record_id: int) -> list[BusinessHistoryEntry]:
    record = db.get(BusinessRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Business record not found")
    entries = list(db.scalars(
        select(BusinessRecordHistory)
        .where(BusinessRecordHistory.record_id == record_id)
        .order_by(BusinessRecordHistory.id.desc())
    ).all())
    return [
        BusinessHistoryEntry(
            id=entry.id,
            action=entry.action,
            actor_name=entry.actor_name,
            actor_role=entry.actor_role,
            reporting_month=entry.reporting_month,
            changes=json.loads(entry.changes) if entry.changes else None,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
