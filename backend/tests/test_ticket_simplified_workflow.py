from app.modules.employee_portal.service import (
    calculate_it_ticket_priority,
    resolve_manual_it_ticket_priority,
)


def test_manual_priority_is_authoritative_for_simplified_it_form() -> None:
    priority, reason, sla_minutes, problem_label, component_label = resolve_manual_it_ticket_priority(
        "mouse",
        "mouse_unusable",
        "low",
    )
    assert priority == "low"
    assert sla_minutes == 1440
    assert problem_label == "Mouse completely unusable"
    assert component_label == "Mouse"
    assert "Employee selected Low priority" in reason


def test_manual_priority_supports_critical_and_moderate_labels() -> None:
    critical = resolve_manual_it_ticket_priority("login_account", "suspected_account_compromise", "critical")
    moderate = resolve_manual_it_ticket_priority("mouse", "scroll_not_working", "medium")
    assert critical[0] == "critical"
    assert critical[2] == 30
    assert "Critical priority" in critical[1]
    assert moderate[0] == "medium"
    assert moderate[2] == 480
    assert "Moderate priority" in moderate[1]


def test_legacy_impact_priority_preview_remains_available() -> None:
    priority, reason, sla_minutes, problem_label = calculate_it_ticket_priority(
        "mouse",
        "mouse_unusable",
        {
            "work_stopped": True,
            "alternative_available": False,
            "multiple_users_affected": False,
            "data_loss_risk": False,
            "security_risk": False,
            "client_delivery_affected": False,
            "recurring_issue": False,
        },
    )
    assert priority == "high"
    assert sla_minutes == 120
    assert problem_label == "Mouse completely unusable"
    assert "work is completely stopped" in reason
