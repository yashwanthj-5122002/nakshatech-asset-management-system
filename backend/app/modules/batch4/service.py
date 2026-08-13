from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ApprovalDecisionHistory, Asset, ReplacementRecord, WorkRecord
from app.modules.employee_portal.models import SupportTicket
from app.modules.it_activity.models import ITPurchaseRequest
from app.modules.it_activity.service import month_bounds
from app.services.approval_workflow_service import WORKFLOW_PURCHASE_REQUEST
from app.services.asset_lifecycle_service import inventory_summary, is_primary_device_type
from app.services.ticket_sla_service import SLA_TERMINAL_STATUSES, build_ticket_sla_snapshot_map


def _month_filter(reporting_column, timestamp_column, month: str | None):
    if not month:
        return None
    _start, _end, utc_start, utc_end = month_bounds(month)
    return or_(
        reporting_column == month,
        and_(
            reporting_column.is_(None),
            timestamp_column >= utc_start,
            timestamp_column < utc_end,
        ),
    )


def _history_month_filter(month: str | None):
    conditions = [ApprovalDecisionHistory.workflow_type == WORKFLOW_PURCHASE_REQUEST]
    if month:
        _start, _end, utc_start, utc_end = month_bounds(month)
        conditions.extend([
            ApprovalDecisionHistory.created_at >= utc_start,
            ApprovalDecisionHistory.created_at < utc_end,
        ])
    return and_(*conditions)


def _purchase_item(request: ITPurchaseRequest) -> dict[str, Any]:
    purchase = request.purchase_record
    return {
        "workflow": "purchase_request",
        "id": request.id,
        "code": request.request_code,
        "title": request.item_name,
        "submitted_by": request.requested_by_name,
        "submitted_at": request.requested_at,
        "department": request.requesting_department,
        "priority": request.priority,
        "amount": request.estimated_total_amount,
        "reason": request.business_reason,
        "status": request.status,
        "target_url": "/it/purchase-requests",
        "reporting_month": request.reporting_month,
        "approved_amount": request.approved_amount,
        "management_remarks": request.management_remarks,
        "decided_by": request.decided_by_name,
        "decided_at": request.decided_at,
        "purchase_completed_at": request.purchase_completed_at,
        "purchase_record_id": purchase.id if purchase else None,
        "purchase_code": purchase.purchase_code if purchase else None,
        "actual_purchase_amount": purchase.total_price if purchase else None,
        "purchase_date": purchase.purchase_date if purchase else None,
        "metadata": {
            "requested_employee": request.requested_employee,
            "quantity": request.quantity,
            "item_type": request.item_type,
            "required_by_date": request.required_by_date,
            "it_remarks": request.it_remarks,
        },
    }


def management_control_center(db: Session, month: str | None = None) -> dict[str, Any]:
    assets = list(db.scalars(select(Asset)).all())
    primary_assets = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    inventory = inventory_summary(primary_assets)

    work_filter = _month_filter(WorkRecord.reporting_month, WorkRecord.created_at, month)
    replacement_filter = _month_filter(ReplacementRecord.reporting_month, ReplacementRecord.created_at, month)
    purchase_filter = _month_filter(ITPurchaseRequest.reporting_month, ITPurchaseRequest.requested_at, month)

    active_work_query = select(func.count(WorkRecord.id)).where(
        WorkRecord.module == "it",
        WorkRecord.status.not_in(["completed", "closed"]),
    )
    if work_filter is not None:
        active_work_query = active_work_query.where(work_filter)
    active_it_work = int(db.scalar(active_work_query) or 0)

    replacement_query = select(func.count(ReplacementRecord.id)).where(
        ReplacementRecord.final_action.in_(["replacement_pending", "procurement_required"])
    )
    if replacement_filter is not None:
        replacement_query = replacement_query.where(replacement_filter)
    active_replacements = int(db.scalar(replacement_query) or 0)

    purchase_query = select(ITPurchaseRequest)
    if purchase_filter is not None:
        purchase_query = purchase_query.where(purchase_filter)
    purchase_requests = list(db.scalars(
        purchase_query.order_by(ITPurchaseRequest.requested_at.desc(), ITPurchaseRequest.id.desc())
    ).unique().all())
    pending_purchases = [request for request in purchase_requests if request.status == "pending_approval"]
    purchase_items = [_purchase_item(request) for request in purchase_requests]
    approval_items = [_purchase_item(request) for request in pending_purchases]

    status_counts = {
        "pending_approval": sum(request.status == "pending_approval" for request in purchase_requests),
        "approved": sum(request.status == "approved" for request in purchase_requests),
        "sent_back": sum(request.status == "sent_back" for request in purchase_requests),
        "rejected": sum(request.status == "rejected" for request in purchase_requests),
        "purchase_completed": sum(request.status == "purchase_completed" for request in purchase_requests),
    }
    approved_purchase_value = round(sum(
        float(request.approved_amount or 0)
        for request in purchase_requests
        if request.status in {"approved", "purchase_completed"}
    ), 2)

    open_tickets = list(db.scalars(
        select(SupportTicket)
        .where(SupportTicket.status.not_in(SLA_TERMINAL_STATUSES))
        .order_by(SupportTicket.created_at.asc(), SupportTicket.id.asc())
        .limit(1000)
    ).all())
    sla_map = build_ticket_sla_snapshot_map(db, open_tickets)
    critical_tickets = [ticket for ticket in open_tickets if ticket.priority == "critical"]
    breached_tickets = [ticket for ticket in open_tickets if sla_map.get(ticket.id, {}).get("sla_breached")]
    warning_tickets = [ticket for ticket in open_tickets if sla_map.get(ticket.id, {}).get("sla_warning")]

    risk_tickets = sorted(
        open_tickets,
        key=lambda ticket: (
            0 if sla_map.get(ticket.id, {}).get("sla_breached") else 1,
            0 if ticket.priority == "critical" else 1,
            ticket.created_at,
        ),
    )[:12]
    ticket_items = [
        {
            "id": ticket.id,
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "department": ticket.department,
            "priority": ticket.priority,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "sla_status": sla_map.get(ticket.id, {}).get("sla_status"),
            "sla_due_at": sla_map.get(ticket.id, {}).get("sla_due_at"),
            "sla_breached": bool(sla_map.get(ticket.id, {}).get("sla_breached")),
            "sla_warning": bool(sla_map.get(ticket.id, {}).get("sla_warning")),
            "target_url": f"/tickets/{ticket.id}",
        }
        for ticket in risk_tickets
    ]

    history_query = (
        select(ApprovalDecisionHistory)
        .where(_history_month_filter(month))
        .order_by(ApprovalDecisionHistory.created_at.desc(), ApprovalDecisionHistory.id.desc())
        .limit(50)
    )
    recent_history = list(db.scalars(history_query).all())

    return {
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "month": month,
        "authority_model": "purchase_approval_only",
        "executive": {
            "primary_assets": inventory.get("total", 0),
            "assigned_assets": inventory.get("assigned", 0),
            "available_assets": inventory.get("available", 0),
            "repair_assets": inventory.get("repair", 0),
            "replacement_pending_assets": inventory.get("replacement_pending", 0),
            "active_it_work": active_it_work,
            "active_replacements": active_replacements,
            "pending_approvals": len(pending_purchases),
            "pending_purchase_requests": len(pending_purchases),
            "approved_purchase_value": approved_purchase_value,
            "open_critical_tickets": len(critical_tickets),
            "sla_warnings": len(warning_tickets),
            "sla_breaches": len(breached_tickets),
        },
        "purchase_summary": {
            "total": len(purchase_requests),
            **status_counts,
            "approved_purchase_value": approved_purchase_value,
        },
        "purchase_requests": purchase_items,
        "approvals": approval_items,
        "risk_tickets": ticket_items,
        "recent_decisions": [
            {
                "id": history.id,
                "workflow": history.workflow_type,
                "record_id": history.record_id,
                "code": history.record_code,
                "action": history.action,
                "from_status": history.from_status,
                "to_status": history.to_status,
                "remarks": history.remarks,
                "performed_by": history.performed_by_name,
                "performed_by_role": history.performed_by_role,
                "created_at": history.created_at,
            }
            for history in recent_history
        ],
    }


def build_management_control_workbook(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Purchase Summary"
    summary.append(["Metric", "Value"])
    purchase_summary = data.get("purchase_summary", {})
    summary_rows = [
        ("Total Purchase Requests", purchase_summary.get("total", 0)),
        ("Pending", purchase_summary.get("pending_approval", 0)),
        ("Approved", purchase_summary.get("approved", 0)),
        ("Sent Back", purchase_summary.get("sent_back", 0)),
        ("Rejected", purchase_summary.get("rejected", 0)),
        ("Purchase Completed", purchase_summary.get("purchase_completed", 0)),
        ("Approved Purchase Value", purchase_summary.get("approved_purchase_value", 0)),
    ]
    for label, value in summary_rows:
        summary.append([label, value])

    purchases = workbook.create_sheet("Purchase Requests")
    purchases.append([
        "Request", "Item", "Status", "Submitted By", "Submitted At", "Department",
        "Priority", "Estimated Amount", "Approved Amount", "Management Remarks",
        "Decided By", "Decided At", "Purchase Code", "Purchase Date", "Actual Amount",
        "Business Reason", "Reporting Month",
    ])
    for item in data.get("purchase_requests", []):
        purchases.append([
            item["code"], item["title"], item["status"], item["submitted_by"], item["submitted_at"],
            item["department"], item["priority"], item["amount"], item.get("approved_amount"),
            item.get("management_remarks"), item.get("decided_by"), item.get("decided_at"),
            item.get("purchase_code"), item.get("purchase_date"), item.get("actual_purchase_amount"),
            item["reason"], item["reporting_month"],
        ])

    decisions = workbook.create_sheet("Purchase Decisions")
    decisions.append([
        "Request", "Action", "From", "To", "Performed By", "Role", "At", "Remarks",
    ])
    for item in data["recent_decisions"]:
        decisions.append([
            item["code"], item["action"], item["from_status"], item["to_status"],
            item["performed_by"], item["performed_by_role"], item["created_at"], item["remarks"],
        ])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
