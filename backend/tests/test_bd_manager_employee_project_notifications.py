"""Isolated tests: BD Manager alerts for BD Employee-origin project milestones.

No live database, Docker service, or production records are used here.
"""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.models.entities import User
from app.modules.bd_employee.handoff_models import BdEmployeeProjectLink
from app.modules.bd_employee import manager_notification_service as manager_notifications
from app.modules.bd_employee import notification_service as employee_notifications
from app.modules.finance.models import FinanceClient, FinanceProject


class FakeSession:
    def __init__(self, project=None, client=None, users=None, link=None, managers=()):
        self.project = project
        self.client = client
        self.users = users or {}
        self.link = link
        self.managers = tuple(managers)

    def get(self, model, key):
        if model is FinanceProject:
            return self.project if self.project and self.project.id == key else None
        if model is FinanceClient:
            return self.client if self.client and self.client.id == key else None
        if model is BdEmployeeProjectLink:
            return self.link if self.link and self.link.project_id == key else None
        if model is User:
            return self.users.get(key)
        raise AssertionError(f"Unexpected model {model}")

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: list(self.managers))

    def begin_nested(self):
        return nullcontext()


def make_session(*, project_source="bd_team", client_source="bd_team", creator_role="bd_employee", link=None, manager_ids=(10,)):
    employee = SimpleNamespace(id=5, role=creator_role, full_name="Employee A", is_active=True, account_status="active")
    manager = SimpleNamespace(id=10, role="bd", full_name="BD Manager", is_active=True, account_status="active")
    project = SimpleNamespace(id=24, client_id=12, created_by_id=5, project_source_team=project_source, project_code="BD-24")
    client = SimpleNamespace(id=12, source_team=client_source)
    return FakeSession(project=project, client=client, users={5: employee, 10: manager}, link=link, managers=manager_ids)


def test_project_creation_informs_active_manager_once(monkeypatch):
    db = make_session()
    emitted = []
    monkeypatch.setattr(manager_notifications, "create_global_notification", lambda *_a, **kwargs: emitted.append(kwargs))
    manager_notifications.notify_manager_project_event(db, project_id=24, milestone="project_created")
    assert len(emitted) == 1
    assert emitted[0]["recipient_user_ids"] == [10]
    assert emitted[0]["dedupe_key"] == "bd-manager-employee-project:24:project_created"
    assert emitted[0]["requires_action"] is False
    assert emitted[0]["target_url"] == "/bd/projects?project=24"


@pytest.mark.parametrize("milestone,event_id,url", [
    ("project_delivered", None, "/bd/feedback?project=24"),
    ("client_feedback_updated", 73, "/bd/feedback?project=24"),
    ("project_closed", None, "/bd/projects?project=24"),
])
def test_manager_milestones_are_correct_and_deduped(monkeypatch, milestone, event_id, url):
    db = make_session()
    emitted = []
    monkeypatch.setattr(manager_notifications, "create_global_notification", lambda *_a, **kwargs: emitted.append(kwargs))
    manager_notifications.notify_manager_project_event(db, project_id=24, milestone=milestone, event_id=event_id)
    assert len(emitted) == 1
    assert emitted[0]["target_url"] == url
    expected = f"bd-manager-employee-project:24:{milestone}"
    if event_id is not None:
        expected += f":{event_id}"
    assert emitted[0]["dedupe_key"] == expected


@pytest.mark.parametrize("kwargs", [
    {"project_source": "management_team"},
    {"client_source": "management_team"},
    {"creator_role": "bd"},
])
def test_unrelated_or_management_projects_never_notify_bd_manager(monkeypatch, kwargs):
    db = make_session(**kwargs)
    emitted = []
    monkeypatch.setattr(manager_notifications, "create_global_notification", lambda *_a, **data: emitted.append(data))
    manager_notifications.notify_manager_project_event(db, project_id=24, milestone="project_closed")
    assert emitted == []


def test_handoff_notifies_only_explicit_manager(monkeypatch):
    link = SimpleNamespace(project_id=24, employee_user_id=6, manager_user_id=10)
    db = make_session(creator_role="bd", link=link, manager_ids=(10, 20))
    db.users[6] = SimpleNamespace(id=6, role="bd_employee", full_name="Employee B", is_active=True, account_status="active")
    emitted = []
    monkeypatch.setattr(manager_notifications, "create_global_notification", lambda *_a, **data: emitted.append(data))
    manager_notifications.notify_manager_project_event(db, project_id=24, milestone="client_feedback_updated", event_id=5)
    assert emitted[0]["recipient_user_ids"] == [10]


def test_milestone_hook_preserves_employee_and_adds_manager(monkeypatch):
    employee_events = []
    manager_events = []
    db = make_session()
    monkeypatch.setattr(employee_notifications, "notify_project_milestone", lambda *_a, **kwargs: employee_events.append(kwargs))
    monkeypatch.setattr(manager_notifications, "safe_notify_manager_project_event", lambda *_a, **kwargs: manager_events.append(kwargs))
    employee_notifications.safe_notify_project_milestone(db, project_id=24, milestone="client_feedback_updated", event_id=101)
    assert employee_events[0]["event_id"] == 101
    assert manager_events == [{"project_id": 24, "milestone": "client_feedback_updated", "event_id": 101}]
    employee_notifications.safe_notify_project_milestone(db, project_id=24, milestone="production_started")
    assert len(manager_events) == 1  # no manager spam on production changes


def test_notification_errors_do_not_cancel_project_savepoint(monkeypatch):
    db = make_session()
    def failed_notification(*_args, **_kwargs):
        raise RuntimeError("Simulated notification insert failure")
    monkeypatch.setattr(manager_notifications, "notify_manager_project_event", failed_notification)
    manager_notifications.safe_notify_manager_project_event(db, project_id=24, milestone="project_created")
