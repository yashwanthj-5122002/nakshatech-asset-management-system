from __future__ import annotations

from email.message import EmailMessage
from html import escape
import json
import logging
import smtplib
import ssl

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.travel_km.models import TravelKmClaim, TravelKmEmailDelivery

logger = logging.getLogger(__name__)


def _email_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in decoded:
        email = str(item or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        result.append(email)
    return result


def _send_message(*, to_emails: list[str], cc_emails: list[str], subject: str, body: str, html_body: str) -> str:
    mode = settings.email_delivery_mode.strip().lower()
    if mode in {"console", "log"}:
        logger.warning(
            "Travel/KM development email | TO=%s | CC=%s | SUBJECT=%s | BODY=%s",
            ", ".join(to_emails),
            ", ".join(cc_emails),
            subject,
            body,
        )
        return "console"
    if mode != "smtp":
        raise RuntimeError("Email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"NakshaTech Travel & KM <{settings.smtp_from_email}>"
    message["To"] = ", ".join(to_emails)
    if cc_emails:
        message["Cc"] = ", ".join(cc_emails)
    message.set_content(body)
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    try:
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
        raise RuntimeError("Travel/KM submission email could not be sent") from exc
    return "smtp"


def _claim_email_content(claim: TravelKmClaim, requester: User, public_base_url: str) -> tuple[str, str, str]:
    configured_base = settings.app_public_url.strip().rstrip("/")
    if configured_base and configured_base not in {"http://localhost:3100", "http://127.0.0.1:3100"}:
        public_base_url = configured_base
    employee_name = requester.full_name or requester.email
    employee_id = getattr(requester, "employee_id", None) or "Not recorded"
    department = getattr(requester, "department", None) or "Not recorded"
    total_km = float(claim.odometer_km or 0)
    allowance = float(claim.calculated_allowance or 0)
    claim_url = f"{public_base_url.rstrip('/')}/travel-km/{claim.id}"
    subject = f"Travel/KM Claim Submitted | {claim.claim_code} | {employee_name} | {claim.project_code_snapshot}"
    body = (
        "NakshaTech Employee Travel / KM Claim\n\n"
        "A Travel/KM claim has been submitted for Admin verification.\n\n"
        f"Claim: {claim.claim_code}\n"
        f"Employee: {employee_name}\n"
        f"Employee ID: {employee_id}\n"
        f"Department: {department}\n"
        f"Project Number: {claim.project_code_snapshot}\n"
        f"Travel Date: {claim.travel_date.isoformat()}\n"
        f"Purpose: {claim.purpose_description}\n"
        f"Start KM: {float(claim.start_km):.2f}\n"
        f"End KM: {float(claim.end_km or 0):.2f}\n"
        f"Total Travel: {total_km:.2f} KM\n"
        f"Rate: INR {float(claim.rate_per_km):.2f} / KM\n"
        f"Calculated Allowance: INR {allowance:.2f}\n"
        "GPS Verification: Available\n"
        "Odometer Proof: Available\n"
        "Current Status: Pending Admin Verification\n\n"
        f"View Travel Claim: {claim_url}\n"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;color:#172033;max-width:720px;margin:0 auto;line-height:1.5">
      <div style="border:1px solid #dfe7f1;border-radius:14px;overflow:hidden">
        <div style="padding:20px 24px;background:#f5f8fc;border-bottom:1px solid #dfe7f1">
          <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#2563eb">NAKSHATECH TRAVEL &amp; KM</div>
          <h2 style="margin:6px 0 0;font-size:22px">Travel/KM Claim Submitted</h2>
        </div>
        <div style="padding:22px 24px">
          <p>A Travel/KM claim has been submitted for Admin verification.</p>
          <table style="border-collapse:collapse;width:100%;font-size:14px">
            <tr><td style="padding:7px 0;color:#65758b">Claim</td><td style="padding:7px 0;font-weight:700">{escape(claim.claim_code)}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Employee</td><td style="padding:7px 0">{escape(employee_name)} ({escape(str(employee_id))})</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Department</td><td style="padding:7px 0">{escape(str(department))}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Project Number</td><td style="padding:7px 0">{escape(claim.project_code_snapshot)}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Travel Date</td><td style="padding:7px 0">{escape(claim.travel_date.isoformat())}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Purpose</td><td style="padding:7px 0">{escape(claim.purpose_description)}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Start / End KM</td><td style="padding:7px 0">{float(claim.start_km):.2f} / {float(claim.end_km or 0):.2f}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Total Travel</td><td style="padding:7px 0;font-weight:700">{total_km:.2f} KM</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Calculated Allowance</td><td style="padding:7px 0;font-weight:700">INR {allowance:.2f}</td></tr>
            <tr><td style="padding:7px 0;color:#65758b">Current Status</td><td style="padding:7px 0">Pending Admin Verification</td></tr>
          </table>
          <div style="margin-top:22px">
            <a href="{escape(claim_url)}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:11px 16px;border-radius:8px;font-weight:700">View Travel Claim</a>
          </div>
          <p style="margin-top:20px;font-size:12px;color:#65758b">GPS coordinates, live route data and odometer evidence remain secured inside the NakshaTech Asset Management System.</p>
        </div>
      </div>
    </div>
    """
    return subject, body, html_body


def send_submission_email(
    db: Session,
    *,
    claim: TravelKmClaim,
    actor: User,
    public_base_url: str,
    event_type: str = "submission",
) -> TravelKmEmailDelivery:
    routing = claim.email_routing
    if routing is None:
        raise ValueError("Travel/KM email routing is not configured")

    to_emails = _email_list(routing.to_emails_json)
    cc_emails = [email for email in _email_list(routing.cc_emails_json) if email not in set(to_emails)]
    if not to_emails:
        raise ValueError("Travel/KM email TO recipients are empty")

    requester = db.get(User, claim.requester_id)
    if requester is None:
        raise ValueError("Travel/KM employee account could not be resolved")
    subject, body, html_body = _claim_email_content(claim, requester, public_base_url)

    delivery = TravelKmEmailDelivery(
        claim_id=claim.id,
        event_type=event_type,
        subject=subject,
        to_emails_json=json.dumps(to_emails),
        cc_emails_json=json.dumps(cc_emails),
        delivery_mode=settings.email_delivery_mode.strip().lower() or "unknown",
        status="pending",
        attempted_by_id=actor.id,
        attempted_at=utc_now(),
    )
    db.add(delivery)
    db.flush()

    try:
        mode = _send_message(
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        delivery.delivery_mode = mode
        delivery.status = "sent" if mode == "smtp" else "console"
        delivery.sent_at = utc_now()
        delivery.error_message = None
    except Exception as exc:  # Claim submission must survive SMTP/configuration outages.
        logger.exception("Travel/KM submission email failed for claim %s", claim.claim_code)
        delivery.status = "failed"
        delivery.error_message = str(exc)[:1000]
    db.flush()
    return delivery
