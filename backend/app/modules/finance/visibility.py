from __future__ import annotations

from typing import Iterable

from sqlalchemy import Select, inspect as sa_inspect, or_, select, table, column

from sqlalchemy.orm import Session

from app.modules.finance.models import FinanceClient, FinanceProject

HIDDEN_ENTITIES_TABLE = "patch_v81_hidden_entities"

FINANCE_CLEANUP_PATCH_ID = "FINANCE_CLEANUP_20260924"
MANAGEMENT_VISIBILITY_PATCH_ID = "V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918"

ACTIVE_HIDDEN_PATCH_IDS: tuple[str, ...] = (
    FINANCE_CLEANUP_PATCH_ID,
    MANAGEMENT_VISIBILITY_PATCH_ID,
)

_hidden_entities = table(
    HIDDEN_ENTITIES_TABLE,
    column("patch_id"),
    column("entity_type"),
    column("entity_id"),
    column("entity_key"),
    column("reason"),
    column("hidden_at"),
)


def hidden_table_available(db: Session) -> bool:
    try:
        return sa_inspect(db.get_bind()).has_table(HIDDEN_ENTITIES_TABLE)
    except Exception:
        return False


def hidden_entity_ids(db: Session, *, entity_type: str, patch_ids: tuple[str, ...] | None = None) -> set[int]:
    if not hidden_table_available(db):
        return set()
    patch_filter = _hidden_entities.c.patch_id.in_(patch_ids or ACTIVE_HIDDEN_PATCH_IDS)
    rows = db.execute(
        select(_hidden_entities.c.entity_id).where(
            patch_filter,
            _hidden_entities.c.entity_type == entity_type,
        )
    ).scalars()
    return {int(value) for value in rows}


def hidden_client_ids(db: Session) -> set[int]:
    return hidden_entity_ids(db, entity_type="finance_client")


def hidden_project_ids(db: Session) -> set[int]:
    return hidden_entity_ids(db, entity_type="finance_project")


def exclude_hidden_clients(db: Session, stmt: Select) -> Select:
    ids = hidden_client_ids(db)
    if ids:
        stmt = stmt.where(FinanceClient.id.not_in(ids))
    return stmt


def exclude_hidden_projects(db: Session, stmt: Select) -> Select:
    project_ids = hidden_project_ids(db)
    client_ids = hidden_client_ids(db)
    if project_ids:
        stmt = stmt.where(FinanceProject.id.not_in(project_ids))
    if client_ids:
        stmt = stmt.where(
            or_(
                FinanceProject.client_id.is_(None),
                FinanceProject.client_id.not_in(client_ids),
            )
        )
    return stmt


def filter_visible_project_ids(db: Session, project_ids: Iterable[int]) -> list[int]:
    """Return the subset of candidate project ids that pass the unified visibility rule."""
    candidates = {int(value) for value in project_ids if value is not None}
    if not candidates:
        return []
    stmt = exclude_hidden_projects(
        db,
        select(FinanceProject.id).where(FinanceProject.id.in_(candidates)),
    )
    return [int(value) for value in db.scalars(stmt).all()]
