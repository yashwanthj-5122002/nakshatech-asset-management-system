from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceRevenueTarget
from app.modules.finance.revenue_target_service import list_revenue_targets, upsert_revenue_target


def _finance_user(db) -> User:
    row = User(
        email="finance.revenue.target.test@nakshatech.com",
        full_name="Finance Revenue Target Test",
        password_hash="test-only",
        role="finance",
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_monthly_department_revenue_target_upsert_and_audit():
    with SessionLocal() as db:
        actor = _finance_user(db)

        created = upsert_revenue_target(
            db,
            month_start=date(2026, 9, 18),
            department_code="LiDAR",
            target_amount_inr=Decimal("1200000.00"),
            actor=actor,
        )
        assert created["month"] == "2026-09"
        assert created["department_code"] == "lidar"
        assert created["target_amount_inr"] == 1200000.0
        assert created["updated_by_name"] == actor.full_name

        updated = upsert_revenue_target(
            db,
            month_start=date(2026, 9, 1),
            department_code="lidar",
            target_amount_inr=Decimal("1350000.00"),
            actor=actor,
        )
        assert updated["id"] == created["id"]
        assert updated["target_amount_inr"] == 1350000.0

        rows = list_revenue_targets(db, year=2026)
        matching = [row for row in rows if row["month"] == "2026-09" and row["department_code"] == "lidar"]
        assert len(matching) == 1
        assert matching[0]["target_amount_inr"] == 1350000.0
        db.rollback()


def test_revenue_target_rejects_unknown_department():
    with SessionLocal() as db:
        actor = _finance_user(db)
        try:
            upsert_revenue_target(
                db,
                month_start=date(2026, 10, 1),
                department_code="unknown_department",
                target_amount_inr=Decimal("100000.00"),
                actor=actor,
            )
        except ValueError as exc:
            assert "supported performing department" in str(exc)
        else:
            raise AssertionError("Expected unsupported department to be rejected")
        db.rollback()
