"""Regression checks for BD Employee lifecycle project boundaries.

Requires the full ERP test environment. All authorization checks here are
read-only stubs and do not touch live PostgreSQL records.
"""
from types import SimpleNamespace

from app.modules.operations import lifecycle_service as service


def _actor(user_id, role, active=True):
    return SimpleNamespace(id=user_id, role=role, is_active=active)


def _workflow(project_id, bd_owner_id):
    return SimpleNamespace(project_id=project_id, bd_owner_user_id=bd_owner_id)


def test_employee_can_only_access_own_visible_bd_project(monkeypatch):
    db = object()
    monkeypatch.setattr(service, "_employee_feedback_project_ids", lambda _db, actor: {10} if actor.id == 1 else {20})
    assert service._can_manage_feedback(db, _actor(1, "bd_employee"), _workflow(10, 9))
    assert not service._can_manage_feedback(db, _actor(1, "bd_employee"), _workflow(20, 9))
    assert not service._can_manage_feedback(db, _actor(2, "bd_employee"), _workflow(10, 9))


def test_employee_cannot_bypass_source_boundary_as_original_workflow_owner(monkeypatch):
    monkeypatch.setattr(service, "_employee_feedback_project_ids", lambda *_args: set())
    assert not service._can_manage_feedback(object(), _actor(1, "bd_employee"), _workflow(10, 1))


def test_existing_bd_manager_and_admin_permissions_remain_unchanged():
    db = object()
    assert service._can_manage_feedback(db, _actor(9, "bd"), _workflow(10, 9))
    assert not service._can_manage_feedback(db, _actor(8, "bd"), _workflow(10, 9))
    assert service._can_manage_feedback(db, _actor(7, "admin"), _workflow(10, 9))
    assert not service._can_manage_feedback(db, _actor(6, "finance"), _workflow(10, 9))
