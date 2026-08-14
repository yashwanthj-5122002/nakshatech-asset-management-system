from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import secrets
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.employee_portal.service import ensure_allowed_email, send_email
from app.modules.it_activity.approval_email_models import (
    ITPurchaseApprovalChannel,
    ITPurchaseApprovalEmailLog,
)
from app.modules.it_activity.models import ITPurchaseRecord, ITPurchaseRequest


@dataclass(frozen=True)
class IssuedApprovalEmail:
    channel: ITPurchaseApprovalChannel
    raw_token: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _uat_prefix() -> str:
    return "" if settings.is_production else "[UAT] "


def _subject(text: str) -> str:
    return f"{_uat_prefix()}{text}"


def _safe(value: Any) -> str:
    return escape("" if value is None else str(value))


def _money(value: float | None) -> str:
    if value is None:
        return "Not specified"
    return f"INR {float(value):,.2f}"


def _date(value: Any) -> str:
    if value is None:
        return "Not specified"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _datetime(value: datetime | None) -> str:
    if value is None:
        return "Not recorded"
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    try:
        from zoneinfo import ZoneInfo

        aware = aware.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        pass
    return aware.strftime("%d %b %Y, %I:%M %p")


def normalize_approval_email(email: str, *, requester_email: str | None = None) -> str:
    normalized = ensure_allowed_email(email)
    if requester_email and normalized == requester_email.strip().lower():
        raise HTTPException(
            status_code=400,
            detail="Approval email must be different from the Purchase Request submitter email",
        )
    return normalized


def channel_for_request(db: Session, request_id: int) -> ITPurchaseApprovalChannel | None:
    return db.scalar(
        select(ITPurchaseApprovalChannel).where(ITPurchaseApprovalChannel.request_id == request_id)
    )


def email_logs_for_request(db: Session, request_id: int) -> list[ITPurchaseApprovalEmailLog]:
    return list(db.scalars(
        select(ITPurchaseApprovalEmailLog)
        .where(ITPurchaseApprovalEmailLog.request_id == request_id)
        .order_by(ITPurchaseApprovalEmailLog.created_at.asc(), ITPurchaseApprovalEmailLog.id.asc())
    ).all())


def _record_email_log(
    db: Session,
    *,
    request_id: int,
    event_type: str,
    recipient_name: str | None,
    recipient_email: str,
    subject: str,
    delivery_status: str,
    error_message: str | None = None,
) -> ITPurchaseApprovalEmailLog:
    log = ITPurchaseApprovalEmailLog(
        request_id=request_id,
        event_type=event_type,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        subject=subject,
        delivery_status=delivery_status,
        error_message=(error_message or "")[:4000] or None,
    )
    db.add(log)
    return log


def _send_and_log(
    db: Session,
    *,
    request: ITPurchaseRequest,
    event_type: str,
    recipient_name: str | None,
    recipient_email: str,
    subject: str,
    body: str,
    html_body: str,
) -> tuple[str, str | None]:
    status = "failed"
    error: str | None = None
    try:
        send_email(
            recipient=recipient_email,
            subject=subject,
            body=body,
            html_body=html_body,
            from_name=settings.purchase_approval_email_heading,
        )
        mode = settings.email_delivery_mode.strip().lower()
        status = "logged" if mode in {"console", "log"} else "sent"
    except HTTPException as exc:
        error = str(exc.detail)
    except Exception as exc:  # Email failure must never roll back purchase governance.
        error = str(exc) or exc.__class__.__name__
    _record_email_log(
        db,
        request_id=request.id,
        event_type=event_type,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        subject=subject,
        delivery_status=status,
        error_message=error,
    )
    db.commit()
    return status, error


def _email_shell(*, title: str, intro: str, content: str, actions: str = "", footer_note: str = "") -> str:
    uat_badge = "" if settings.is_production else (
        '<div style="margin:0 0 14px;padding:8px 10px;border-radius:6px;background:#fff3cd;'
        'color:#6b5200;font-size:12px;font-weight:700;text-align:center;">UAT / TEST APPROVAL</div>'
    )
    return f"""
<!doctype html>
<html>
<body style="margin:0;padding:24px;background:#eef4f8;font-family:Arial,Helvetica,sans-serif;color:#183b56;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #dbe5ef;border-radius:10px;overflow:hidden;box-shadow:0 4px 18px rgba(15,39,68,.08);">
    <div style="padding:20px 26px;background:#0b6f8f;color:#ffffff;">
      <div style="font-size:18px;font-weight:800;letter-spacing:.08em;">NAKSHATECH</div>
      <div style="margin-top:4px;font-size:13px;font-weight:700;">{_safe(settings.purchase_approval_email_heading)}</div>
      <div style="margin-top:2px;font-size:11px;opacity:.9;">Asset Management System</div>
    </div>
    <div style="padding:24px 26px;">
      {uat_badge}
      <h2 style="margin:0 0 8px;color:#0f2744;font-size:21px;">{_safe(title)}</h2>
      <p style="margin:0 0 18px;line-height:1.6;color:#526579;">{intro}</p>
      {content}
      {actions}
    </div>
    <div style="padding:18px 26px;background:#f7fafc;border-top:1px solid #dbe5ef;font-size:12px;line-height:1.6;color:#526579;">
      <strong style="color:#183b56;">Best regards,<br>{_safe(settings.purchase_approval_email_heading)}</strong><br>
      NakshaTech Asset Management System<br>
      {footer_note or "This message contains an auditable purchase-approval action. Do not forward approval links."}
    </div>
  </div>
</body>
</html>
""".strip()


def _detail_rows(request: ITPurchaseRequest, *, include_decision: bool = False) -> str:
    rows: list[tuple[str, str]] = [
        ("Purchase Request", request.request_code),
        ("Requested By", f"{request.requested_by_name} ({request.requested_by_email})"),
        ("Department", request.requesting_department),
        ("Requested Employee", request.requested_employee),
        ("Item", request.item_name),
        ("Item Type", request.item_type.title()),
        ("Quantity", str(request.quantity)),
        ("Estimated Amount", _money(request.estimated_total_amount)),
        ("Priority", request.priority.title()),
        ("Required By", _date(request.required_by_date)),
    ]
    if include_decision:
        rows.extend([
            ("Status", request.status.replace("_", " ").title()),
            ("Approved Amount", _money(request.approved_amount)),
            ("Decision By", request.decided_by_name or "Not recorded"),
            ("Decision Email", request.decided_by_email or "Not recorded"),
            ("Decision At", _datetime(request.decided_at)),
        ])
    rendered = []
    for label, value in rows:
        rendered.append(
            '<tr>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #e4edf3;color:#617487;width:34%;font-size:12px;">{_safe(label)}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #e4edf3;color:#183b56;font-size:12px;font-weight:700;">{_safe(value)}</td>'
            '</tr>'
        )
    return '<table role="presentation" style="width:100%;border-collapse:collapse;border:1px solid #dbe5ef;border-radius:8px;overflow:hidden;">' + "".join(rendered) + "</table>"


def _notes(request: ITPurchaseRequest, *, include_management: bool = False) -> str:
    blocks = [
        ("BUSINESS REQUIREMENT", request.business_reason),
        ("ITEM DESCRIPTION", request.item_description),
        ("IT REMARKS", request.it_remarks),
    ]
    if include_management:
        blocks.append(("MANAGEMENT REMARKS", request.management_remarks))
    html: list[str] = []
    for label, value in blocks:
        if not value:
            continue
        html.append(
            '<div style="margin-top:14px;padding:12px 14px;border:1px solid #dbe5ef;border-radius:8px;background:#f8fbfd;">'
            f'<div style="font-size:11px;font-weight:800;letter-spacing:.08em;color:#526579;">{_safe(label)}</div>'
            f'<div style="margin-top:6px;line-height:1.55;font-size:13px;color:#183b56;white-space:pre-wrap;">{_safe(value)}</div>'
            '</div>'
        )
    return "".join(html)


def _action_url(raw_token: str, action: str) -> str:
    token = quote(raw_token, safe="")
    return f"{settings.purchase_approval_base_url}/api/it-activity/purchase-approval-email/{token}?action={quote(action, safe='')}"


def _app_request_url(request: ITPurchaseRequest) -> str:
    month = quote(request.reporting_month or "", safe="")
    suffix = f"?month={month}" if month else ""
    return f"{settings.purchase_approval_base_url}/it/purchase-requests{suffix}"


def build_approval_request_email(
    request: ITPurchaseRequest,
    channel: ITPurchaseApprovalChannel,
    raw_token: str,
    *,
    resubmitted: bool = False,
) -> tuple[str, str, str]:
    subject = _subject(
        f"Purchase Approval {'Resubmitted' if resubmitted else 'Required'} - {request.request_code}"
    )
    intro = (
        f"Dear {_safe(channel.approver_name)}, a Purchase Request has been "
        f"{'resubmitted and requires' if resubmitted else 'submitted for'} your decision. "
        "The same request is visible in NakshaTech Asset Management."
    )
    approve_url = _action_url(raw_token, "approve")
    send_back_url = _action_url(raw_token, "send_back")
    reject_url = _action_url(raw_token, "reject")
    app_url = _app_request_url(request)
    actions = f"""
<div style="margin-top:22px;text-align:center;">
  <a href="{_safe(approve_url)}" style="display:inline-block;margin:4px;padding:11px 16px;border-radius:7px;background:#059669;color:#fff;text-decoration:none;font-weight:700;">Approve Purchase</a>
  <a href="{_safe(send_back_url)}" style="display:inline-block;margin:4px;padding:11px 16px;border-radius:7px;background:#d97706;color:#fff;text-decoration:none;font-weight:700;">Send Back</a>
  <a href="{_safe(reject_url)}" style="display:inline-block;margin:4px;padding:11px 16px;border-radius:7px;background:#dc2626;color:#fff;text-decoration:none;font-weight:700;">Reject</a>
</div>
<div style="margin-top:10px;text-align:center;">
  <a href="{_safe(app_url)}" style="display:inline-block;padding:9px 14px;border:1px solid #0b6f8f;border-radius:7px;color:#0b6f8f;text-decoration:none;font-weight:700;">Open Asset Management</a>
</div>
<p style="margin:14px 0 0;color:#7a8793;font-size:11px;line-height:1.5;text-align:center;">For safety, an email button opens a confirmation page. Merely opening this email does not approve or reject anything.</p>
""".strip()
    html = _email_shell(
        title="Purchase Approval Required",
        intro=intro,
        content=_detail_rows(request) + _notes(request),
        actions=actions,
    )
    body = (
        f"Purchase approval required: {request.request_code}\n"
        f"Item: {request.item_name}\nDepartment: {request.requesting_department}\n"
        f"Requested employee: {request.requested_employee}\nQuantity: {request.quantity}\n"
        f"Estimated amount: {_money(request.estimated_total_amount)}\n\n"
        f"Approve: {approve_url}\nSend Back: {send_back_url}\nReject: {reject_url}\n"
        f"Open Asset Management: {app_url}\n"
    )
    return subject, body, html


def issue_purchase_approval_email(
    db: Session,
    request: ITPurchaseRequest,
    approver_name: str,
    approver_email: str,
    *,
    resubmitted: bool = False,
) -> IssuedApprovalEmail:
    if request.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Approval email can be issued only for a pending Purchase Request")
    clean_name = (approver_name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Approval recipient name is required")
    clean_email = normalize_approval_email(approver_email, requester_email=request.requested_by_email)

    raw_token = secrets.token_urlsafe(32)
    now = _utc_now()
    expires = now + timedelta(hours=max(settings.purchase_approval_email_token_hours, 1))
    channel = channel_for_request(db, request.id)
    if channel is None:
        channel = ITPurchaseApprovalChannel(
            request_id=request.id,
            approver_name=clean_name,
            approver_email=clean_email,
            token_hash=_token_hash(raw_token),
            token_expires_at=expires,
        )
        db.add(channel)
    else:
        channel.approver_name = clean_name
        channel.approver_email = clean_email
        channel.token_hash = _token_hash(raw_token)
        channel.token_expires_at = expires
        channel.token_consumed_at = None
        channel.decision_source = None
        channel.updated_at = now
    channel.email_status = "pending"
    channel.email_sent_at = None
    channel.email_last_error = None
    db.commit()
    db.refresh(channel)

    subject, body, html = build_approval_request_email(
        request,
        channel,
        raw_token,
        resubmitted=resubmitted,
    )
    status, error = _send_and_log(
        db,
        request=request,
        event_type="approval_resubmitted" if resubmitted else "approval_requested",
        recipient_name=channel.approver_name,
        recipient_email=channel.approver_email,
        subject=subject,
        body=body,
        html_body=html,
    )
    channel = channel_for_request(db, request.id)
    if channel is not None:
        channel.email_status = status
        channel.email_sent_at = _utc_now() if status in {"sent", "logged"} else None
        channel.email_last_error = error
        channel.updated_at = _utc_now()
        db.commit()
        db.refresh(channel)
    return IssuedApprovalEmail(channel=channel, raw_token=raw_token)  # type: ignore[arg-type]


def resolve_approval_token(
    db: Session,
    raw_token: str,
) -> tuple[ITPurchaseApprovalChannel, ITPurchaseRequest]:
    token = (raw_token or "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Approval link is invalid")
    channel = db.scalar(
        select(ITPurchaseApprovalChannel).where(ITPurchaseApprovalChannel.token_hash == _token_hash(token))
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Approval link is invalid or has been replaced")
    request = db.get(ITPurchaseRequest, channel.request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Purchase Request no longer exists")
    return channel, request


def consume_channel_for_application_decision(db: Session, request: ITPurchaseRequest) -> None:
    channel = channel_for_request(db, request.id)
    if channel is None:
        return
    now = _utc_now()
    if channel.token_consumed_at is None:
        channel.token_consumed_at = now
    if not channel.decision_source:
        channel.decision_source = "asset_management"
    channel.updated_at = now
    db.commit()


def mark_channel_for_email_decision(db: Session, channel: ITPurchaseApprovalChannel) -> None:
    now = _utc_now()
    channel.token_consumed_at = now
    channel.decision_source = "email"
    channel.updated_at = now
    # Deliberately do not commit here. The Purchase Request decision service
    # commits the channel mutation and business decision atomically.


def _decision_result_email(request: ITPurchaseRequest, *, source: str) -> tuple[str, str, str]:
    status_label = request.status.replace("_", " ").title()
    subject = _subject(f"Purchase Request {status_label} - {request.request_code}")
    next_action = {
        "approved": "IT may proceed with procurement against this approved Purchase Request.",
        "sent_back": "IT must review the Management remarks, update the request and resubmit it.",
        "rejected": "This Purchase Request is rejected and cannot be used for procurement.",
    }.get(request.status, "Review the Purchase Request in Asset Management.")
    app_url = _app_request_url(request)
    content = _detail_rows(request, include_decision=True) + _notes(request, include_management=True)
    content += (
        '<div style="margin-top:14px;padding:12px 14px;border-radius:8px;background:#e8f6f2;border:1px solid #b7e4d5;">'
        '<div style="font-size:11px;font-weight:800;letter-spacing:.08em;color:#25715a;">NEXT ACTION</div>'
        f'<div style="margin-top:6px;line-height:1.5;font-size:13px;color:#183b56;">{_safe(next_action)}</div>'
        '</div>'
    )
    actions = (
        '<div style="margin-top:20px;text-align:center;">'
        f'<a href="{_safe(app_url)}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#008fb3;color:#fff;text-decoration:none;font-weight:700;">Open Purchase Request</a>'
        '</div>'
    )
    html = _email_shell(
        title=f"Purchase Request {status_label}",
        intro=f"Decision source: {_safe(source)}. The Asset Management record has been updated.",
        content=content,
        actions=actions,
    )
    body = (
        f"Purchase Request {request.request_code} is now {status_label}.\n"
        f"Decision by: {request.decided_by_name or 'Not recorded'} ({request.decided_by_email or 'Not recorded'})\n"
        f"Decision at: {_datetime(request.decided_at)}\nApproved amount: {_money(request.approved_amount)}\n"
        f"Management remarks: {request.management_remarks or 'None'}\n\n{next_action}\n{app_url}\n"
    )
    return subject, body, html


def notify_requester_of_decision(
    db: Session,
    request: ITPurchaseRequest,
    *,
    source: str,
) -> tuple[str, str | None]:
    subject, body, html = _decision_result_email(request, source=source)
    return _send_and_log(
        db,
        request=request,
        event_type=f"decision_{request.status}",
        recipient_name=request.requested_by_name,
        recipient_email=request.requested_by_email,
        subject=subject,
        body=body,
        html_body=html,
    )


def build_purchase_completed_email(
    request: ITPurchaseRequest,
    purchase: ITPurchaseRecord,
) -> tuple[str, str, str]:
    subject = _subject(f"Purchase Completed - {request.request_code}")
    content = _detail_rows(request, include_decision=True)
    content += (
        '<div style="margin-top:14px;padding:12px 14px;border:1px solid #b7e4d5;border-radius:8px;background:#e8f6f2;">'
        '<div style="font-size:11px;font-weight:800;letter-spacing:.08em;color:#25715a;">PURCHASE COMPLETION</div>'
        f'<div style="margin-top:7px;font-size:13px;line-height:1.65;">Purchase Record: <strong>{_safe(purchase.purchase_code)}</strong><br>'
        f'Purchase Date: <strong>{_safe(_date(purchase.purchase_date))}</strong><br>'
        f'Actual Amount: <strong>{_safe(_money(purchase.total_price))}</strong><br>'
        f'Supplier: <strong>{_safe(purchase.supplier_name)}</strong><br>'
        f'Completed By: <strong>{_safe(purchase.created_by or "IT Department")}</strong></div>'
        '</div>'
    )
    app_url = _app_request_url(request)
    actions = (
        '<div style="margin-top:20px;text-align:center;">'
        f'<a href="{_safe(app_url)}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#008fb3;color:#fff;text-decoration:none;font-weight:700;">Open Purchase Request</a>'
        '</div>'
    )
    html = _email_shell(
        title="Purchase Completed",
        intro="The approved Purchase Request has been completed and linked to a Purchase Record.",
        content=content,
        actions=actions,
    )
    body = (
        f"Purchase completed for {request.request_code}.\nPurchase Record: {purchase.purchase_code}\n"
        f"Purchase Date: {_date(purchase.purchase_date)}\nActual Amount: {_money(purchase.total_price)}\n"
        f"Supplier: {purchase.supplier_name}\nCompleted By: {purchase.created_by or 'IT Department'}\n{app_url}\n"
    )
    return subject, body, html


def notify_purchase_completed(
    db: Session,
    request: ITPurchaseRequest,
    purchase: ITPurchaseRecord,
) -> None:
    subject, body, html = build_purchase_completed_email(request, purchase)
    channel = channel_for_request(db, request.id)
    recipients: list[tuple[str | None, str]] = [(request.requested_by_name, request.requested_by_email)]
    if channel is not None and channel.approver_email.strip().lower() != request.requested_by_email.strip().lower():
        recipients.append((channel.approver_name, channel.approver_email))
    seen: set[str] = set()
    for name, email in recipients:
        normalized = email.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        _send_and_log(
            db,
            request=request,
            event_type="purchase_completed",
            recipient_name=name,
            recipient_email=normalized,
            subject=subject,
            body=body,
            html_body=html,
        )


def email_activity_payload(db: Session, request_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "recipient_name": row.recipient_name,
            "recipient_email": row.recipient_email,
            "subject": row.subject,
            "delivery_status": row.delivery_status,
            "error_message": row.error_message,
            "created_at": row.created_at,
        }
        for row in email_logs_for_request(db, request_id)
    ]


def enrich_purchase_request_payload(
    db: Session,
    request: ITPurchaseRequest,
    payload: dict[str, Any],
    *,
    include_email_activity: bool = False,
) -> dict[str, Any]:
    channel = channel_for_request(db, request.id)
    payload.update({
        "approval_recipient_name": channel.approver_name if channel else None,
        "approval_recipient_email": channel.approver_email if channel else None,
        "approval_email_status": channel.email_status if channel else None,
        "approval_email_sent_at": channel.email_sent_at if channel else None,
        "approval_email_last_error": channel.email_last_error if channel else None,
        "approval_token_expires_at": channel.token_expires_at if channel else None,
        "approval_token_consumed_at": channel.token_consumed_at if channel else None,
        "decision_source": channel.decision_source if channel else None,
        "email_activity": email_activity_payload(db, request.id) if include_email_activity else [],
    })
    return payload


def approval_review_html(
    request: ITPurchaseRequest,
    channel: ITPurchaseApprovalChannel,
    raw_token: str,
    action: str,
) -> str:
    requested_action = action if action in {"approve", "send_back", "reject"} else "approve"
    if request.status != "pending_approval":
        return approval_result_html(
            request,
            channel,
            title="Decision already completed",
            message=f"This Purchase Request is already {request.status.replace('_', ' ')}. No further action is permitted.",
        )
    now = _utc_now()
    if channel.token_consumed_at is not None:
        return approval_result_html(request, channel, title="Approval link already used", message="This approval link has already been consumed.")
    if channel.token_expires_at < now:
        return approval_result_html(request, channel, title="Approval link expired", message="This approval link has expired. IT must resend the approval email.")

    amount_field = ""
    if requested_action == "approve":
        amount = request.estimated_total_amount if request.estimated_total_amount is not None else ""
        amount_field = (
            '<label style="display:block;margin-top:16px;font-size:12px;font-weight:700;color:#526579;">Approved Amount (INR)'
            f'<input name="approved_amount" type="number" min="0" step="0.01" value="{_safe(amount)}" style="box-sizing:border-box;width:100%;margin-top:6px;padding:10px;border:1px solid #cbd8e3;border-radius:7px;"></label>'
        )
    remarks_required = requested_action in {"send_back", "reject"}
    action_label = {"approve": "Approve Purchase", "send_back": "Send Back", "reject": "Reject"}[requested_action]
    action_color = {"approve": "#059669", "send_back": "#d97706", "reject": "#dc2626"}[requested_action]
    post_url = f"{settings.purchase_approval_base_url}/api/it-activity/purchase-approval-email/{quote(raw_token, safe='')}"
    content = _detail_rows(request) + _notes(request)
    form = f"""
<form method="post" action="{_safe(post_url)}" style="margin-top:18px;">
  <input type="hidden" name="action" value="{_safe(requested_action)}">
  {amount_field}
  <label style="display:block;margin-top:14px;font-size:12px;font-weight:700;color:#526579;">Management Remarks{' *' if remarks_required else ''}
    <textarea name="management_remarks" {'required' if remarks_required else ''} rows="4" style="box-sizing:border-box;width:100%;margin-top:6px;padding:10px;border:1px solid #cbd8e3;border-radius:7px;resize:vertical;"></textarea>
  </label>
  <button type="submit" style="width:100%;margin-top:16px;padding:12px;border:0;border-radius:8px;background:{action_color};color:#fff;font-size:14px;font-weight:800;cursor:pointer;">Confirm {_safe(action_label)}</button>
</form>
<p style="margin:12px 0 0;color:#7a8793;font-size:11px;line-height:1.5;">This confirmation is auditable and can be submitted only while the Purchase Request is still pending.</p>
""".strip()
    return _email_shell(
        title=f"Confirm {action_label}",
        intro=f"Approval recipient: <strong>{_safe(channel.approver_name)}</strong> ({_safe(channel.approver_email)}). Review the request before confirming.",
        content=content,
        actions=form,
        footer_note="This secure approval page was opened from an email link. Closing the page without confirming makes no change.",
    )


def approval_result_html(
    request: ITPurchaseRequest,
    channel: ITPurchaseApprovalChannel,
    *,
    title: str,
    message: str,
) -> str:
    content = _detail_rows(request, include_decision=request.status != "pending_approval") + _notes(
        request,
        include_management=request.status != "pending_approval",
    )
    app_url = _app_request_url(request)
    actions = (
        '<div style="margin-top:20px;text-align:center;">'
        f'<a href="{_safe(app_url)}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#008fb3;color:#fff;text-decoration:none;font-weight:700;">Open Asset Management</a>'
        '</div>'
    )
    return _email_shell(
        title=title,
        intro=_safe(message),
        content=content,
        actions=actions,
        footer_note=f"Approval recipient: {_safe(channel.approver_name)} ({_safe(channel.approver_email)}).",
    )
