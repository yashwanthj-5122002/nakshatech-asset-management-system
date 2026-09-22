from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.departments import SUPPORTED_DEPARTMENTS, department_label, normalize_department_code
from app.models.entities import User
from app.modules.finance.models import FinanceRevenueTarget


def _money(value: object | None) -> float:
    return float(Decimal(str(value or 0)))


def revenue_target_payload(row: FinanceRevenueTarget, users: dict[int, User] | None = None) -> dict:
    users = users or {}
    created_by = users.get(row.created_by_id)
    updated_by = users.get(row.updated_by_id)
    return {
        "id": row.id,
        "month_start": row.month_start.isoformat(),
        "month": row.month_start.strftime("%Y-%m"),
        "department_code": row.department_code,
        "department_label": department_label(row.department_code),
        "target_amount_inr": _money(row.target_amount_inr),
        "created_by_id": row.created_by_id,
        "created_by_name": created_by.full_name if created_by else None,
        "updated_by_id": row.updated_by_id,
        "updated_by_name": updated_by.full_name if updated_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_revenue_targets(db: Session, *, year: int | None = None) -> list[dict]:
    stmt = select(FinanceRevenueTarget).order_by(
        FinanceRevenueTarget.month_start.desc(),
        FinanceRevenueTarget.department_code,
    )
    if year is not None:
        stmt = stmt.where(
            FinanceRevenueTarget.month_start >= date(year, 1, 1),
            FinanceRevenueTarget.month_start <= date(year, 12, 31),
        )
    rows = list(db.scalars(stmt).all())
    user_ids = {row.created_by_id for row in rows} | {row.updated_by_id for row in rows}
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    return [revenue_target_payload(row, users) for row in rows]


def upsert_revenue_target(
    db: Session,
    *,
    month_start: date,
    department_code: str,
    target_amount_inr: Decimal,
    actor: User,
) -> dict:
    if month_start.day != 1:
        month_start = month_start.replace(day=1)
    department = normalize_department_code(department_code)
    if department is None or department not in SUPPORTED_DEPARTMENTS:
        raise ValueError("Select a supported performing department")
    if target_amount_inr < 0:
        raise ValueError("Revenue target cannot be negative")

    row = db.scalar(
        select(FinanceRevenueTarget).where(
            FinanceRevenueTarget.month_start == month_start,
            FinanceRevenueTarget.department_code == department,
        )
    )
    if row is None:
        row = FinanceRevenueTarget(
            month_start=month_start,
            department_code=department,
            target_amount_inr=target_amount_inr,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        db.add(row)
    else:
        row.target_amount_inr = target_amount_inr
        row.updated_by_id = actor.id

    db.flush()
    db.commit()
    users = {actor.id: actor}
    return revenue_target_payload(row, users)
