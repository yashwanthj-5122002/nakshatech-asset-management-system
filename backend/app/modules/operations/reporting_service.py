from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.operations.completion_service import completion_dashboard_payload
from app.modules.operations.handover_service import handover_dashboard_payload
from app.modules.operations.monitoring_service import monitoring_dashboard_payload
from app.modules.operations.sample_service import sample_dashboard_payload
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_ROLE_DEPARTMENT_MAP,
    bd_dashboard_payload,
    normalize_role,
    project_workstreams_dashboard_payload,
    technical_department_specs,
)
from app.modules.operations.technical_directory_service import directory_dashboard_payload
from app.modules.operations.technical_routing_service import routing_status_payload

EXECUTIVE_ROLES = {"admin", "management"}
MANAGER_REPORTING_ROLES = {
    "bd",
    "finance",
    "ortho",
    "lidar",
    "civil",
    "laser_scanning",
    "bim",
    "mobile_mapping",
}
REPORTING_ROLES = EXECUTIVE_ROLES | MANAGER_REPORTING_ROLES


def _count_by_status(rows: list[dict[str, Any]], key: str = "status") -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "unknown") for row in rows).items()))


def _flatten_handovers(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows: list[dict[str, Any]] = []
    for project in payload.get("projects", []):
        for handover in project.get("handovers", []):
            rows.append({
                "project_id": project.get("project_id"),
                "project_code": project.get("project_code"),
                "project_name": project.get("project_name"),
                "client_name": project.get("client_name"),
                **handover,
            })
    return rows


def _flatten_samples(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    return list(payload.get("sample_requests", []))


def _completion_by_project(payload: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not payload:
        return {}
    return {
        int(row["project_id"]): row
        for row in payload.get("projects", [])
        if row.get("project_id") is not None
    }


def _project_facts(
    monitoring: dict[str, Any] | None,
    completion: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    completion_map = _completion_by_project(completion)
    rows: list[dict[str, Any]] = []
    if monitoring:
        for project in monitoring.get("projects", []):
            project_id = int(project["project_id"])
            summary = project.get("summary", {})
            completion_row = completion_map.get(project_id, {})
            completion_info = completion_row.get("completion") or {}
            rows.append({
                "project_id": project_id,
                "project_code": project.get("project_code"),
                "project_name": project.get("project_name"),
                "client_name": project.get("client_name"),
                "project_status": project.get("project_status"),
                "health": summary.get("health"),
                "overall_progress_percent": summary.get("overall_progress_percent", 0),
                "total_workstreams": summary.get("total_workstreams", 0),
                "completed_workstreams": summary.get("completed_workstreams", 0),
                "blocked_workstreams": summary.get("blocked_workstreams", 0),
                "unresolved_handovers": summary.get("unresolved_handovers", 0),
                "overdue_handovers": summary.get("overdue_handovers", 0),
                "final_delivery_recorded": bool(completion_info),
                "finance_status": completion_info.get("finance_status"),
            })
    else:
        # Finance users may not have access to the monitoring dashboard. Preserve
        # their completion/closure portfolio as a reporting fact table.
        for project in (completion or {}).get("projects", []):
            completion_info = project.get("completion") or {}
            readiness = project.get("readiness") or {}
            rows.append({
                "project_id": project.get("project_id"),
                "project_code": project.get("project_code"),
                "project_name": project.get("project_name"),
                "client_name": project.get("client_name"),
                "project_status": project.get("project_status"),
                "health": "delivered" if completion_info else ("ready_for_delivery" if readiness.get("ready") else "in_progress"),
                "overall_progress_percent": 100 if completion_info else None,
                "total_workstreams": len(project.get("workstreams", [])),
                "completed_workstreams": sum(1 for row in project.get("workstreams", []) if row.get("status") == "completed"),
                "blocked_workstreams": 0,
                "unresolved_handovers": sum(
                    int(row.get("unresolved_incoming", 0)) + int(row.get("unresolved_outgoing", 0))
                    for row in project.get("workstreams", [])
                ),
                "overdue_handovers": None,
                "final_delivery_recorded": bool(completion_info),
                "finance_status": completion_info.get("finance_status"),
            })
    return rows


def _department_scorecards(
    monitoring: dict[str, Any] | None,
    samples: dict[str, Any] | None,
    handovers: dict[str, Any] | None,
    directory: dict[str, Any] | None,
    *,
    restrict_department: str | None = None,
) -> list[dict[str, Any]]:
    specs = technical_department_specs()
    if restrict_department:
        specs = [item for item in specs if item["code"] == restrict_department]

    state: dict[str, dict[str, Any]] = {}
    for spec in specs:
        state[spec["code"]] = {
            "department_code": spec["code"],
            "department_label": spec["label"],
            "project_ids": set(),
            "workstreams": 0,
            "completed_workstreams": 0,
            "blocked_workstreams": 0,
            "progress_values": [],
            "sample_requests": 0,
            "open_samples": 0,
            "incoming_handovers": 0,
            "outgoing_handovers": 0,
            "unresolved_handovers": 0,
            "overdue_handovers": 0,
            "configured_real_members": 0,
            "pm_candidates": 0,
            "live_ready": False,
        }

    for project in (monitoring or {}).get("projects", []):
        for row in project.get("workstreams", []):
            code = row.get("department_code")
            if code not in state:
                continue
            item = state[code]
            item["project_ids"].add(project.get("project_id"))
            item["workstreams"] += 1
            item["completed_workstreams"] += int(row.get("status") == "completed")
            item["blocked_workstreams"] += int(row.get("status") == "blocked")
            if row.get("progress_percent") is not None:
                item["progress_values"].append(float(row.get("progress_percent") or 0))

    for request in _flatten_samples(samples):
        for department in request.get("departments", []):
            code = department.get("department_code")
            if code not in state:
                continue
            state[code]["sample_requests"] += 1
            if department.get("status") != "client_approved":
                state[code]["open_samples"] += 1

    for row in _flatten_handovers(handovers):
        from_code = row.get("from_department_code")
        to_code = row.get("to_department_code")
        unresolved = row.get("status") != "accepted"
        overdue = bool(row.get("overdue"))
        if from_code in state:
            state[from_code]["outgoing_handovers"] += 1
            state[from_code]["unresolved_handovers"] += int(unresolved)
            state[from_code]["overdue_handovers"] += int(overdue)
        if to_code in state:
            state[to_code]["incoming_handovers"] += 1
            state[to_code]["unresolved_handovers"] += int(unresolved)
            state[to_code]["overdue_handovers"] += int(overdue)

    for department in (directory or {}).get("departments", []):
        code = department.get("department_code")
        if code not in state:
            continue
        readiness = department.get("readiness", {})
        state[code]["configured_real_members"] = int(readiness.get("configured_real_members", 0))
        state[code]["pm_candidates"] = int(readiness.get("pm_candidates", 0))
        state[code]["live_ready"] = bool(readiness.get("live_ready"))

    result: list[dict[str, Any]] = []
    for spec in specs:
        item = state[spec["code"]]
        progress_values = item.pop("progress_values")
        project_ids = item.pop("project_ids")
        item["projects"] = len({value for value in project_ids if value is not None})
        item["average_progress_percent"] = round(sum(progress_values) / len(progress_values), 1) if progress_values else 0.0
        result.append(item)
    return result


def _sample_summary(samples: dict[str, Any] | None) -> dict[str, Any]:
    rows = _flatten_samples(samples)
    return {
        "total": len(rows),
        "open": sum(1 for row in rows if row.get("status") != "client_approved"),
        "client_approved": sum(1 for row in rows if row.get("status") == "client_approved"),
        "by_status": _count_by_status(rows),
    }


def _handover_summary(handovers: dict[str, Any] | None) -> dict[str, Any]:
    rows = _flatten_handovers(handovers)
    return {
        "total": len(rows),
        "unresolved": sum(1 for row in rows if row.get("status") != "accepted"),
        "overdue": sum(1 for row in rows if row.get("overdue")),
        "by_status": _count_by_status(rows),
    }


def _routing_summary(db: Session, directory: dict[str, Any] | None) -> dict[str, Any]:
    state = routing_status_payload(db)
    return {
        "routing_mode": state.get("routing_mode"),
        "live_technical_routing_enabled": bool(state.get("live_technical_routing_enabled")),
        "all_departments_ready": bool(state.get("all_departments_ready")),
        "live_ready_departments": int((directory or {}).get("summary", {}).get("live_ready_departments", 0)),
        "configured_real_members": int((directory or {}).get("summary", {}).get("configured_real_members", 0)),
        "cutover_blockers": state.get("blockers", {}),
    }


def _executive_payload(db: Session, *, actor: User) -> dict[str, Any]:
    role = "management"
    bd = bd_dashboard_payload(db, actor=actor, effective_role=role)
    workstreams = project_workstreams_dashboard_payload(db, actor=actor, effective_role=role)
    monitoring = monitoring_dashboard_payload(db, actor=actor, effective_role=role)
    samples = sample_dashboard_payload(db, actor=actor, effective_role=role)
    handovers = handover_dashboard_payload(db, actor=actor, effective_role=role)
    completion = completion_dashboard_payload(db, actor=actor, effective_role=role)
    directory = directory_dashboard_payload(db, effective_role=role)

    project_facts = _project_facts(monitoring, completion)
    department_facts = _department_scorecards(monitoring, samples, handovers, directory)
    sample_summary = _sample_summary(samples)
    handover_summary = _handover_summary(handovers)
    routing = _routing_summary(db, directory)

    monitoring_summary = monitoring.get("summary", {})
    completion_summary = completion.get("summary", {})
    return {
        "viewer_mode": "executive",
        "current_role": normalize_role(actor.role),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routing": routing,
        "summary": {
            "total_projects": int(monitoring_summary.get("total_projects", 0)),
            "average_progress_percent": float(monitoring_summary.get("average_progress_percent", 0)),
            "attention_projects": int(monitoring_summary.get("delayed_projects", 0)) + int(monitoring_summary.get("blocked_projects", 0)),
            "open_samples": int(sample_summary["open"]),
            "unresolved_handovers": int(handover_summary["unresolved"]),
            "overdue_handovers": int(handover_summary["overdue"]),
            "delivered_projects": int(completion_summary.get("delivered_projects", 0)),
            "pending_finance": int(completion_summary.get("pending_finance", 0)),
            "financially_closed": int(completion_summary.get("financially_closed", 0)),
        },
        "bd": bd.get("summary", {}),
        "samples": sample_summary,
        "handovers": handover_summary,
        "completion": completion_summary,
        "workstreams": workstreams.get("summary", {}),
        "department_scorecards": department_facts,
        "projects": project_facts,
        "powerbi": {
            "semantic_model_url": "/api/operations/reporting/powerbi/semantic-model",
            "projects_csv_url": "/api/operations/reporting/powerbi/projects.csv",
            "departments_csv_url": "/api/operations/reporting/powerbi/departments.csv",
            "note": "Read-only reporting feed. Live ERP actions remain in the ERP dashboards, not in Power BI.",
        },
    }


def _manager_payload(db: Session, *, actor: User, role: str) -> dict[str, Any]:
    if role == "finance":
        completion = completion_dashboard_payload(db, actor=actor, effective_role=role)
        project_facts = _project_facts(None, completion)
        summary = completion.get("summary", {})
        return {
            "viewer_mode": "finance_manager",
            "current_role": role,
            "current_department_code": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "routing": routing_status_payload(db),
            "summary": {
                "visible_projects": int(summary.get("visible_projects", 0)),
                "ready_for_delivery": int(summary.get("ready_for_delivery", 0)),
                "delivered_projects": int(summary.get("delivered_projects", 0)),
                "pending_finance": int(summary.get("pending_finance", 0)),
                "financially_closed": int(summary.get("financially_closed", 0)),
            },
            "bd": {},
            "samples": {"total": 0, "open": 0, "client_approved": 0, "by_status": {}},
            "handovers": {"total": 0, "unresolved": 0, "overdue": 0, "by_status": {}},
            "completion": summary,
            "department_scorecards": [],
            "projects": project_facts,
            "powerbi": {
                "projects_csv_url": "/api/operations/reporting/powerbi/projects.csv",
                "note": "Finance export is restricted to the projects visible to this Finance login.",
            },
        }

    bd = bd_dashboard_payload(db, actor=actor, effective_role=role) if role == "bd" else None
    workstreams = project_workstreams_dashboard_payload(db, actor=actor, effective_role=role)
    monitoring = monitoring_dashboard_payload(db, actor=actor, effective_role=role)
    samples = sample_dashboard_payload(db, actor=actor, effective_role=role)
    handovers = handover_dashboard_payload(db, actor=actor, effective_role=role)
    completion = completion_dashboard_payload(db, actor=actor, effective_role=role)
    directory = directory_dashboard_payload(db, effective_role=role)

    restrict_department = TECHNICAL_ROLE_DEPARTMENT_MAP.get(role)
    sample_summary = _sample_summary(samples)
    handover_summary = _handover_summary(handovers)
    department_facts = _department_scorecards(
        monitoring,
        samples,
        handovers,
        directory,
        restrict_department=restrict_department,
    )
    project_facts = _project_facts(monitoring, completion)
    mon = monitoring.get("summary", {})
    comp = completion.get("summary", {})
    return {
        "viewer_mode": "bd_manager" if role == "bd" else "technical_manager",
        "current_role": role,
        "current_department_code": restrict_department,
        "current_department_label": TECHNICAL_DEPARTMENT_LABELS.get(restrict_department) if restrict_department else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routing": _routing_summary(db, directory),
        "summary": {
            "visible_projects": int(mon.get("total_projects", 0)),
            "average_progress_percent": float(mon.get("average_progress_percent", 0)),
            "attention_projects": int(mon.get("delayed_projects", 0)) + int(mon.get("blocked_projects", 0)),
            "open_samples": int(sample_summary["open"]),
            "unresolved_handovers": int(handover_summary["unresolved"]),
            "overdue_handovers": int(handover_summary["overdue"]),
            "delivered_projects": int(comp.get("delivered_projects", 0)),
            "pending_finance": int(comp.get("pending_finance", 0)),
        },
        "bd": (bd or {}).get("summary", {}),
        "samples": sample_summary,
        "handovers": handover_summary,
        "completion": comp,
        "workstreams": workstreams.get("summary", {}),
        "department_scorecards": department_facts,
        "projects": project_facts,
        "powerbi": {
            "projects_csv_url": "/api/operations/reporting/powerbi/projects.csv",
            "departments_csv_url": "/api/operations/reporting/powerbi/departments.csv",
            "note": "Exports preserve the current login's reporting scope.",
        },
    }


def reporting_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict[str, Any]:
    role = normalize_role(effective_role)
    if role not in REPORTING_ROLES:
        raise PermissionError("Reporting dashboard is not available for this role")
    if role in EXECUTIVE_ROLES:
        return _executive_payload(db, actor=actor)
    return _manager_payload(db, actor=actor, role=role)


def powerbi_semantic_payload(db: Session, *, actor: User, effective_role: str) -> dict[str, Any]:
    dashboard = reporting_dashboard_payload(db, actor=actor, effective_role=effective_role)
    return {
        "generated_at": dashboard["generated_at"],
        "viewer_mode": dashboard["viewer_mode"],
        "current_role": dashboard["current_role"],
        "routing": dashboard.get("routing", {}),
        "datasets": {
            "project_facts": dashboard.get("projects", []),
            "department_facts": dashboard.get("department_scorecards", []),
            "bd_summary": dashboard.get("bd", {}),
            "sample_summary": dashboard.get("samples", {}),
            "handover_summary": dashboard.get("handovers", {}),
            "completion_summary": dashboard.get("completion", {}),
        },
        "governance": {
            "read_only": True,
            "source": "Nakshatech ERP V7.0.22 reporting layer",
            "guidance": "Power BI/reporting consumers must remain read-only; all workflow actions stay in the ERP.",
        },
    }
