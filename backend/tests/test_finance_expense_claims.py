from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.finance.models import ExpenseClaimAttachment, FinanceProject
from app.modules.finance.schemas import ExpenseClaimCreateRequest
from app.modules.finance.service import (
    admin_decision,
    claim_payload,
    create_claim,
    dashboard_payload,
    ensure_finance_seed_data,
    finance_decision,
    get_visible_claim,
    mark_paid,
    project_expense_allowed,
    submit_claim,
)


def make_user(db, *, email: str, name: str, role: str, department: str | None = None) -> User:
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
        role=role,
        branch="Head Office",
        department=department,
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def advance_payload(project_id: int) -> ExpenseClaimCreateRequest:
    return ExpenseClaimCreateRequest(
        project_id=project_id,
        claim_type="advance",
        purpose_description="Project field survey travel and accommodation advance.",
        requested_work_start_date=date(2026, 8, 28),
        requested_work_end_date=date(2026, 8, 30),
        items=[
            {"category": "travel", "description": "Bus and local travel for survey team", "amount": 2500},
            {"category": "hotel", "description": "Two nights accommodation near project site", "amount": 5000},
        ],
    )


def test_finance_claim_lifecycle_is_separate_and_role_scoped():
    with SessionLocal() as db:
        ensure_finance_seed_data(db)
        project = db.scalar(select(FinanceProject).order_by(FinanceProject.id.asc()))
        assert project is not None

        employee = make_user(db, email="employee.finance.test@nakshatech.com", name="Finance Test Employee", role="employee", department="Survey")
        admin = make_user(db, email="admin.finance.test@nakshatech.com", name="Finance Test Admin", role="admin")
        finance = make_user(db, email="finance.test@nakshatech.com", name="Finance Test Team", role="finance")
        management = make_user(db, email="management.finance.test@nakshatech.com", name="Finance Test Management", role="management")
        other_employee = make_user(db, email="other.finance.test@nakshatech.com", name="Other Employee", role="employee")
        db.commit()

        claim = create_claim(db, requester=employee, payload=advance_payload(project.id))
        assert claim.status == "draft"
        assert float(claim.total_amount) == 7500.0
        assert claim.claim_code.startswith("NT-EXP-")

        employee_view = claim_payload(db, claim, employee, "employee")
        assert employee_view["can_edit"] is True
        assert employee_view["can_admin_decide"] is False
        assert get_visible_claim(db, claim_id=claim.id, viewer=other_employee, effective_role="employee") is None

        claim = submit_claim(db, claim=claim, requester=employee)
        assert claim.status == "submitted"
        assert claim_payload(db, claim, admin, "admin")["can_admin_decide"] is True
        assert claim_payload(db, claim, finance, "finance")["can_finance_decide"] is False

        claim = admin_decision(db, claim=claim, actor=admin, action="approve", comments="Project and advance are legitimate.")
        assert claim.status == "admin_approved"
        assert claim_payload(db, claim, finance, "finance")["can_finance_decide"] is True

        claim = finance_decision(db, claim=claim, actor=finance, action="approve", comments="Bills and amount verified for payment.", approved_work_start_date=date(2026, 8, 28), approved_work_end_date=date(2026, 8, 29), settlement_due_date=date(2026, 9, 5))
        assert claim.status == "finance_approved"
        assert claim.requested_work_end_date == date(2026, 8, 30)
        assert claim.approved_work_end_date == date(2026, 8, 29)
        assert claim_payload(db, claim, finance, "finance")["can_mark_paid"] is True
        assert claim_payload(db, claim, management, "management")["can_mark_paid"] is False

        claim = mark_paid(
            db,
            claim=claim,
            actor=finance,
            payment_reference="UTR-TEST-0001",
            paid_amount=7500,
            comments="Test settlement completed.",
        )
        assert claim.status == "paid"
        assert float(claim.paid_amount or 0) == 7500.0
        assert claim.payment_reference == "UTR-TEST-0001"
        assert len(claim.events) >= 5

        management_dashboard = dashboard_payload(db, viewer=management, effective_role="management")
        assert management_dashboard["total_claims"] == 1
        assert management_dashboard["paid_count"] == 1
        assert management_dashboard["paid_amount"] == 7500.0


def test_reimbursement_requires_supporting_proof_before_submission():
    with SessionLocal() as db:
        ensure_finance_seed_data(db)
        project = db.scalar(select(FinanceProject).order_by(FinanceProject.id.asc()))
        employee = make_user(db, email="reimbursement.test@nakshatech.com", name="Reimbursement Employee", role="employee")
        db.commit()
        assert project is not None

        payload = ExpenseClaimCreateRequest(
            project_id=project.id,
            claim_type="reimbursement",
            purpose_description="Employee paid the project hotel expense personally.",
            requested_work_start_date=date(2026, 8, 28),
            requested_work_end_date=date(2026, 8, 30),
            items=[{"category": "hotel", "description": "Project site accommodation paid by employee", "amount": 4200}],
        )
        claim = create_claim(db, requester=employee, payload=payload)
        with pytest.raises(ValueError, match="Attach at least one"):
            submit_claim(db, claim=claim, requester=employee)

        db.add(ExpenseClaimAttachment(
            claim_id=claim.id,
            uploaded_by_id=employee.id,
            original_filename="hotel-receipt.pdf",
            storage_key=f"finance-expenses/test/{claim.id}/hotel-receipt.pdf",
            mime_type="application/pdf",
            file_size=1234,
        ))
        db.commit()
        db.refresh(claim)
        claim = submit_claim(db, claim=claim, requester=employee)
        assert claim.status == "submitted"


def test_additional_advance_requires_original_released_advance_link():
    with SessionLocal() as db:
        ensure_finance_seed_data(db)
        project = db.scalar(select(FinanceProject).order_by(FinanceProject.id.asc()))
        assert project is not None
        with pytest.raises(ValueError, match="Select the original Advance Request"):
            ExpenseClaimCreateRequest(
                project_id=project.id,
                claim_type="additional_advance",
                purpose_description="Original project advance is not sufficient for the remaining field work.",
                requested_work_start_date=date(2026, 8, 28),
                requested_work_end_date=date(2026, 8, 30),
                previous_advance_amount=5000,
                amount_already_used=1000,
                items=[{"category": "fuel", "description": "Additional fuel required for site work", "amount": 1500}],
            )


def test_project_calendar_blocks_expenses_outside_project_window():
    with SessionLocal() as db:
        ensure_finance_seed_data(db)
        project = db.scalar(select(FinanceProject).order_by(FinanceProject.id.asc()))
        assert project is not None
        project.start_date = date(2026, 8, 10)
        project.end_date = date(2026, 8, 20)
        project.is_active = True
        assert project_expense_allowed(project, on_date=date(2026, 8, 9))[0] is False
        assert project_expense_allowed(project, on_date=date(2026, 8, 15))[0] is True
        allowed, reason = project_expense_allowed(project, on_date=date(2026, 8, 21))
        assert allowed is False
        assert "finished" in (reason or "").lower()
