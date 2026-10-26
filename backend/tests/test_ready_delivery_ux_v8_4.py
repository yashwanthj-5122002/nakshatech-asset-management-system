"""Focused tests for the Ready -> Delivery UAT defects (V8.4 fix pass).

Covers the four reported defects:
  1. Ready button stayed active after success (payload never sent ready_for_delivery),
  2. no explicit Deliver action appeared (can_deliver came from the stale legacy stage and
     mark_delivered was gated on the legacy stage/qa_state),
  3. stale "NOT STARTED" package badge (UI rendered the raw legacy current_stage),
  4. repeated Ready submissions must not duplicate state/notifications.

Isolated TEST DATA only. Not the release regression.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.notifications.models import GlobalNotification
from app.modules.operations import production_items as items_service
from app.modules.operations.schemas import WorkflowDeliveryRequest, WorkflowOperationalCompletion
from app.modules.operations.workflow_service import mark_delivered, operational_complete, ortho_dashboard
from test_physical_file_workflow_v8_4 import (  # noqa: E402
    PM,
    TL,
    _agg,
    _assign,
    _qa_all,
    _setup,
)

READY_EVENT = "workflow.package.ready_confirmed"


def _pkg_payload(db, ctx, pkg):
    project = next(p for p in ortho_dashboard(db, actor=ctx["pm"], role=PM)["projects"]
                   if p["project_id"] == ctx["project"].id)
    return project, next(x for x in project["packages"] if x["id"] == pkg.id)


def _ready(db, ctx, pkg):
    return items_service.mark_ready_for_delivery(
        db, actor=ctx["team"]["tl"], role=TL, work_package_id=pkg.id)


def _ready_notifications(db, pkg):
    return db.scalar(select(func.count(GlobalNotification.id)).where(
        GlobalNotification.event_type == READY_EVENT,
        GlobalNotification.dedupe_key == f"package-ready-confirmed-{pkg.id}",
    )) or 0


# ======================= 1 + 4: ready once, repeat idempotent, no duplicate =============

def test_ready_succeeds_once_and_repeat_is_idempotent_without_duplicate_notifications():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-1", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        first = _ready(db, ctx, pkg)
        assert first["ready"] is True
        db.flush()
        ready_at, ready_by = pkg.ready_for_delivery_at, pkg.ready_for_delivery_by_id
        assert ready_at is not None and ready_by == ctx["team"]["tl"].id
        assert _ready_notifications(db, pkg) == 1
        # repeated Ready (double click / retry) must not duplicate state or notifications
        for _ in range(3):
            again = _ready(db, ctx, pkg)
            assert again["ready"] is True
        db.flush()
        assert pkg.ready_for_delivery_at == ready_at
        assert pkg.ready_for_delivery_by_id == ready_by
        assert _ready_notifications(db, pkg) == 1


def test_ready_payload_flags_drive_the_button_state():
    """Defect 1: the payload must expose ready_eligible/ready_for_delivery so the UI can
    replace the Mark Ready button with Ready-confirmed (and survive a page reload)."""
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-2", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        _, before = _pkg_payload(db, ctx, pkg)
        assert before["ready_eligible"] is True
        assert before["ready_for_delivery"] is False      # not confirmed yet -> button shows
        assert before["delivered"] is False
        _ready(db, ctx, pkg)
        db.flush()
        db.expire_all()
        _, after = _pkg_payload(db, ctx, pkg)
        assert after["ready_eligible"] is True
        assert after["ready_for_delivery"] is True        # confirmed -> "READY CONFIRMED"
        assert after["delivered"] is False                # ready is NOT delivery


# ======================= 3: derived stage (no stale NOT STARTED) =========================

def test_package_display_stage_is_derived_not_legacy_not_started():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-3", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        _, payload = _pkg_payload(db, ctx, pkg)
        # legacy column is still "not_started" for a purely file-tracked area
        assert payload["current_stage"] == "not_started"
        assert payload["display_stage"] == "delivery_ready"     # derived from physical files
        _ready(db, ctx, pkg)
        db.flush()
        db.expire_all()
        _, confirmed = _pkg_payload(db, ctx, pkg)
        assert confirmed["display_stage"] == "delivery_ready"
        _deliver(db, ctx, pkg)
        db.flush()
        db.expire_all()
        _, delivered = _pkg_payload(db, ctx, pkg)
        assert delivered["display_stage"] == "delivered"


# ======================= 2: explicit delivery after ready ================================

def _deliver(db, ctx, pkg, remarks="Delivered to client"):
    return mark_delivered(db, actor=ctx["team"]["tl"], work_package_id=pkg.id,
                          payload=WorkflowDeliveryRequest(remarks=remarks))


def test_deliver_blocked_before_ready_then_works_and_is_not_repeatable():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-4", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        # QA passed but Ready NOT confirmed -> explicit delivery must be refused
        with pytest.raises(ValueError, match="Confirm Ready for Delivery"):
            _deliver(db, ctx, pkg)
        _ready(db, ctx, pkg)
        db.flush()
        _, ready_payload = _pkg_payload(db, ctx, pkg)
        assert ready_payload["can_deliver"] is True        # Deliver action now exposed
        _deliver(db, ctx, pkg)
        db.flush()
        db.expire_all()
        agg = _agg(db, pkg)
        assert agg["files_delivered"] == agg["files_expected"]     # counters updated
        assert _agg(db, pkg)["ready_for_delivery"] is True
        _, delivered_payload = _pkg_payload(db, ctx, pkg)
        assert delivered_payload["delivered"] is True
        assert delivered_payload["can_deliver"] is False   # Deliver action removed
        # repeated delivery is refused (no duplicate state)
        with pytest.raises(ValueError, match="already delivered"):
            _deliver(db, ctx, pkg)


def test_deliver_blocked_when_a_file_has_not_passed_qa():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-5", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items[:1])                        # only 1 of 2 files QA-passed
        with pytest.raises(ValueError, match="Not all files passed QA"):
            _deliver(db, ctx, pkg)


# ======================= 5/6: delivered counters + PM completion + finance ===============

def test_project_delivered_counter_updates_only_after_explicit_delivery():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-6", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        before = next(p for p in ortho_dashboard(db, actor=ctx["pm"], role=PM)["projects"]
                      if p["project_id"] == ctx["project"].id)
        assert before["summary"]["delivery_ready"] == 1     # ready count
        assert before["summary"]["delivered"] == 0          # NOT delivered yet
        _ready(db, ctx, pkg)
        db.flush()
        db.expire_all()
        still = next(p for p in ortho_dashboard(db, actor=ctx["pm"], role=PM)["projects"]
                     if p["project_id"] == ctx["project"].id)
        assert still["summary"]["delivered"] == 0           # Ready != Delivered
        _deliver(db, ctx, pkg)
        db.flush()
        db.expire_all()
        after = next(p for p in ortho_dashboard(db, actor=ctx["pm"], role=PM)["projects"]
                     if p["project_id"] == ctx["project"].id)
        assert after["summary"]["delivered"] == 1
        assert after["can_complete_project"] is True        # PM action now offered


def test_pm_operational_completion_requires_delivery_and_finance_stays_open():
    with SessionLocal() as db:
        ctx, pkg, items = _setup(db, "RD-7", n=2)
        _assign(db, ctx, pkg, items)
        _qa_all(db, ctx, items)
        _ready(db, ctx, pkg)
        db.flush()
        with pytest.raises(ValueError, match="must be delivered"):
            operational_complete(db, actor=ctx["pm"], project_id=ctx["project"].id,
                                 payload=WorkflowOperationalCompletion(
                                     completion_date=date(2026, 10, 30),
                                     final_delivery_reference="REF-RD"))
        _deliver(db, ctx, pkg)
        db.flush()
        db.expire_all()
        workflow = operational_complete(
            db, actor=ctx["pm"], project_id=ctx["project"].id,
            payload=WorkflowOperationalCompletion(completion_date=date(2026, 10, 30),
                                                  final_delivery_reference="REF-RD"))
        assert workflow.operational_completed_at is not None
        assert workflow.finance_closed_at is None
        assert workflow.status != "closed"
