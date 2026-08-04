"""Non-destructive route and model verification for the employee portal release."""
from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.main import app  # noqa: E402
from app.modules.employee_portal.models import (  # noqa: E402
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

REQUIRED_ROUTES = {
    "/auth/capabilities",
    "/auth/branches",
    "/auth/register/request-otp",
    "/auth/register/verify-otp",
    "/auth/register/complete",
    "/auth/mfa/confirm",
    "/auth/mfa/verify-login",
    "/auth/forgot-password/request-otp",
    "/auth/forgot-password/verify-otp",
    "/auth/forgot-password/reset",
    "/auth/my-branches",
    "/auth/select-branch",
    "/auth/logout",
    "/audit/page-view",
    "/tickets",
    "/tickets/{ticket_id}",
    "/tickets/{ticket_id}/messages",
    "/notifications",
    "/notifications/{notification_id}/read",
    "/software/users",
    "/software/audit",
    "/software/users/{user_id}/reset-authenticator",
}


def normalize_route(path: str) -> str:
    prefix = "/api"
    return path[len(prefix):] if path.startswith(prefix) else path


def main() -> None:
    available = {normalize_route(route.path) for route in app.routes}
    missing = sorted(REQUIRED_ROUTES - available)
    if missing:
        print("EMPLOYEE PORTAL ROUTE VERIFICATION FAILED")
        for path in missing:
            print(f"MISSING: {path}")
        raise SystemExit(1)

    tables = {
        model.__tablename__
        for model in (
            Branch,
            UserBranchAccess,
            EmailOTPChallenge,
            AuthenticatorCredential,
            UserSession,
            SupportTicket,
            TicketMessage,
            TicketNotification,
            AuditEvent,
        )
    }
    expected_tables = {
        "branches",
        "user_branch_access",
        "email_otp_challenges",
        "authenticator_credentials",
        "user_sessions",
        "support_tickets",
        "ticket_messages",
        "ticket_notifications",
        "audit_events",
    }
    if tables != expected_tables:
        print("EMPLOYEE PORTAL MODEL VERIFICATION FAILED")
        raise SystemExit(1)

    print("EMPLOYEE PORTAL VERIFICATION PASSED")
    print(f"Required routes: {len(REQUIRED_ROUTES)}")
    print(f"Required tables: {len(expected_tables)}")
    print("No database records were created, updated, or deleted by this verification.")


if __name__ == "__main__":
    main()
