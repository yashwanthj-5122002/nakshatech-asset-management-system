"""Production tracking reports (V8.1 additive) built with the existing reporting conventions.

Reuses ``workflow_reporting`` sheet/finish helpers so styling, freeze panes, auto
filters and file naming stay identical to the current Project Operations exports.

Report types (server-side aggregation only):
- ``production_detail``        — detailed package report in the familiar LiDAR Daily
                                 Activity column order (MARCHE LOTTO 3 … REMARKS),
                                 with the unit made explicit instead of assuming KM.
- ``project_progress``         — Project Progress Summary (production %, workflow %).
- ``employee_production``      — Team Lead / Employee Production Summary.
- ``pending_stages``           — Pending Production/QC/QA/DXF/Inspection/Delivery/Upload.
- ``rework_quality``           — Rework / Quality Report (QC & QA attempts incl. rejects).
- ``management_consolidated``  — Management read-only consolidated project report.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import User
from app.modules.finance.models import FinanceProject
from app.modules.operations.models import (
    OrthoProjectMember,
    OrthoWorkPackage,
    ProjectWorkflow,
)
from app.modules.operations.production_service import (
    ADMIN_ROLE,
    EMPLOYEE_ROLE,
    MANAGEMENT_ROLE,
    _department_of,
    visible_project_ids,
)
from app.modules.operations.production_stages import (
    STAGE_DELIVERY,
    STAGE_LABELS,
    aggregate_project_progress,
    package_production_progress,
    package_workflow_progress,
    pending_stages,
    stage_profile_for_department,
    stage_status,
)
from app.modules.operations.workflow_reporting import _bounds, _finish, _sheet

PRODUCTION_REPORT_TYPES = {
    "production_detail",
    "project_progress",
    "employee_production",
    "pending_stages",
    "rework_quality",
    "management_consolidated",
    "project_workbook",
}

# V8.2 project workbook: the business's familiar AREA MASTER column order, EXACTLY 26 columns.
AREA_MASTER_HEADERS = [
    "MARCHE LOTTO 3",
    "CODE",
    "AREA NAME",
    "LENGTH",
    "INSPECTED DATE",
    "SUPPLY DATE",
    "ACTUAL KM",
    "IMP_DATE",
    "IMPORTING",
    "PROD_DATE",
    "PROD_ALLOTMENT",
    "STATUS",
    "QC_DATE",
    "QC_ALLOTMENT",
    "STATUS",
    "QA_DATE",
    "QA_ALLOTMENT",
    "STATUS",
    "DXF_ALLOTMENT",
    "STATUS",
    "NO OF FILES",
    "INSPECTED",
    "DELIVERED STATUS",
    "DELIVERED DATE",
    "UPLOAD STATUS",
    "REMARKS",
]

FILE_ACTIVITY_HEADERS = [
    "PROJECT", "MARCHE LOTTO 3", "CODE", "AREA NAME", "FILE NUMBER", "FILE NAME",
    "PLANNED LENGTH", "UOM", "SUPPLY DATE",
    "PRODUCTION EMPLOYEE", "PRODUCTION TARGET DATE",
    "PRODUCTION START DATE", "PRODUCTION START TIME",
    "PRODUCTION END DATE", "PRODUCTION END TIME", "PRODUCTION DURATION",
    "ACTUAL QUANTITY", "PRODUCTION STATUS", "PRODUCTION DEADLINE STATUS", "PRODUCTION REMARKS",
    "DELAY CATEGORY", "AFFECTED FILE", "DELAY REASON", "SYSTEM MALFUNCTION", "DELAY REMARKS",
    "QC EMPLOYEE", "QC TARGET DATE",
    "QC START DATE", "QC START TIME", "QC END DATE", "QC END TIME",
    "QC DURATION", "QC STATUS", "QC DEADLINE STATUS", "QC REMARKS",
    "QA EMPLOYEE", "QA TARGET DATE",
    "QA START DATE", "QA START TIME", "QA END DATE", "QA END TIME",
    "QA DURATION", "QA STATUS", "QA DEADLINE STATUS", "QA REMARKS",
    "READY FOR DELIVERY", "DELIVERED BY", "DELIVERY DATE", "DELIVERY TIME",
    "DELIVERY STATUS", "DELIVERY REMARKS",
]

EMPLOYEE_PRODUCTIVITY_HEADERS = [
    "EMPLOYEE", "ROLE", "PROJECT", "MARCHE LOTTO 3", "CODE", "AREA", "DATE",
    "ASSIGNED FILES", "COMPLETED FILES", "PENDING FILES", "FILES WORKED",
    "ACTUAL QUANTITY", "UOM",
    "PRODUCTION TIME", "QC TIME", "QA TIME", "TOTAL TRACKED TIME",
    "QUANTITY / HOUR", "FILES / HOUR",
    "ON-TIME COUNT", "LATE COUNT", "REWORK COUNT", "SYSTEM MALFUNCTION COUNT", "REMARKS",
]

ACTIVITY_HISTORY_HEADERS = [
    "PROJECT", "MARCHE LOTTO 3", "CODE", "AREA", "FILE NUMBER", "FILE NAME",
    "PLANNED QUANTITY", "UOM", "STAGE",
    "EMPLOYEE", "ROLE", "DATE", "START TIME", "COMPLETION TIME", "TIME TAKEN",
    "QUANTITY THIS SESSION", "UNIT", "STATUS", "FINALIZED",
    "DELAY / DIFFICULTY", "DELAY REASON", "SYSTEM MALFUNCTION", "REMARKS",
]

LEGACY_TILE_ACTIVITY_HEADERS = [
    "STAGE", "TILE / FILE NAME", "DATE", "TECHNICIAN", "START TIME", "COMP TIME",
    "TIME TAKEN", "STATUS", "LENGTH", "REMARKS",
]


def _load_context(db: Session, *, actor: User, role: str, project_id: int | None):
    project_ids = visible_project_ids(db, actor=actor, role=role)
    if project_id is not None:
        project_ids &= {project_id}
    if not project_ids:
        return {}, {}, [], {}
    projects = {p.id: p for p in db.scalars(select(FinanceProject).where(FinanceProject.id.in_(project_ids))).all()}
    workflows = {w.project_id: w for w in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()}
    packages = list(db.scalars(
        select(OrthoWorkPackage)
        .options(selectinload(OrthoWorkPackage.daily_updates), selectinload(OrthoWorkPackage.reviews))
        .where(OrthoWorkPackage.project_id.in_(project_ids))
        .order_by(OrthoWorkPackage.id.asc())
    ).unique().all())
    assignee_ids = {uid for pkg in packages for uid in (pkg.team_leader_user_id, pkg.production_user_id, pkg.qc_user_id, pkg.qa_user_id, pkg.dxf_user_id) if uid}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(assignee_ids))).all()} if assignee_ids else {}
    return projects, workflows, packages, users


def _last_review_date(package: OrthoWorkPackage, kind: str) -> date | None:
    rows = [row for row in package.reviews if row.review_type == kind]
    if not rows:
        return None
    latest = max(rows, key=lambda row: (row.created_at or date.min))
    return latest.created_at.date() if latest.created_at else None


def _name(users: dict, user_id: int | None) -> str | None:
    user = users.get(user_id) if user_id else None
    return user.full_name if user else None


def _package_totals(package: OrthoWorkPackage) -> tuple[Decimal, int]:
    total = sum((row.achieved_area or Decimal("0")) for row in package.daily_updates)
    files = sum(int(row.files_completed or 0) for row in package.daily_updates)
    return total, files


def build_production_workbook(
    db: Session,
    *,
    report_type: str,
    actor: User,
    role: str,
    project_id: int | None = None,
    search: str | None = None,
) -> tuple[bytes, str]:
    """Build one production-tracking workbook. Access follows the dashboard contract."""
    if report_type not in PRODUCTION_REPORT_TYPES:
        raise ValueError("Unsupported production report type")
    projects, workflows, packages, users = _load_context(db, actor=actor, role=role, project_id=project_id)
    if role == EMPLOYEE_ROLE:
        packages = [
            pkg for pkg in packages
            if actor.id in {pkg.team_leader_user_id, pkg.production_user_id, pkg.qc_user_id, pkg.qa_user_id, pkg.dxf_user_id}
        ]
    if search:
        token = search.strip().lower()
        packages = [
            pkg for pkg in packages
            if token in (pkg.package_code or "").lower()
            or token in (pkg.package_name or "").lower()
            or token in ((pkg.lot_batch or "").lower())
        ]

    from openpyxl import Workbook
    workbook = Workbook()
    if report_type == "project_workbook":
        if project_id is None:
            raise ValueError("Select a project before downloading its workbook")
        if project_id not in projects:
            raise ValueError("Project not visible to your role")
        _render_project_workbook(db, workbook, projects, workflows, packages, users)
        project_code = getattr(projects.get(project_id), "project_code", None) or project_id
        return _finish(workbook), f"Naksha_{project_code}_Production_Workbook.xlsx"
    result = _render_sheets(workbook, report_type, projects, workflows, packages, users)
    if result is not None:
        return result
    return _finish(workbook), f"Naksha_Production_{report_type}.xlsx"


def _render_sheets(workbook, report_type, projects, workflows, packages, users) -> None:
    if report_type in {"production_detail", "management_consolidated"}:
        _render_detail_sheet(workbook, projects, workflows, packages, users)
    if report_type == "project_progress":
        _render_project_progress(workbook, projects, workflows, packages)
    if report_type == "employee_production":
        _render_employee_production(workbook, projects, packages, users)
    if report_type == "pending_stages":
        _render_pending_stages(workbook, projects, workflows, packages, users)
    if report_type == "rework_quality":
        _render_rework_quality(workbook, projects, packages, users)
    if report_type == "management_consolidated":
        _render_management_summary(workbook, projects, workflows, packages)


def _render_detail_sheet(workbook, projects, workflows, packages, users) -> None:
    """Detailed report in the familiar LiDAR Daily Activity column order.

    LENGTH/ACTUAL show the package's planned and completed quantity WITH the
    package's own unit made explicit (never silently assuming KM). ALLOTMENT
    columns mirror the planned quantity per stage. INSPECTED DATE and INSPECTED
    remain two separate columns (business semantics not yet merged).
    """
    sheet = _sheet(workbook, "Production Tracking", [
        "Project ID", "MARCHE LOTTO 3 (Lot / Batch)", "CODE", "AREA NAME",
        "LENGTH (Planned Qty)", "UNIT", "ACTUAL (Completed Qty)", "PROGRESS %",
        "INSPECTED DATE", "INSPECTED", "SUPPLY DATE",
        "IMP_DATE", "IMPORTING",
        "PROD_DATE", "PROD_ALLOTMENT", "PRODUCTION STATUS",
        "QC_DATE", "QC_ALLOTMENT", "QC STATUS",
        "QA_DATE", "QA_ALLOTMENT", "QA STATUS",
        "DXF_ALLOTMENT", "DXF STATUS", "NO OF FILES",
        "DELIVERED STATUS", "DELIVERED DATE", "UPLOAD STATUS",
        "WORKFLOW %", "CURRENT STAGE", "TEAM LEAD", "REMARKS",
    ])
    for package in packages:
        project = projects.get(package.project_id)
        workflow = workflows.get(package.project_id)
        department = (workflow.performing_department_code if workflow else None) or "ortho"
        total, files = _package_totals(package)
        production = package_production_progress(total, package.area)
        planned = float(package.area) if package.area is not None else None
        sheet.append([
            project.project_code if project else package.project_id,
            package.lot_batch, package.package_code, package.package_name,
            planned, package.area_unit or None, float(total), production["progress_percent"],
            package.inspected_at.date() if package.inspected_at else None,
            stage_status(package, "inspection"),
            package.supply_date,
            package.imported_at.date() if package.imported_at else None,
            package.import_status,
            package.production_completed_at.date() if package.production_completed_at else None,
            planned, package.production_state,
            _last_review_date(package, "qc") or (package.qc_submitted_at.date() if package.qc_submitted_at else None),
            planned, package.qc_state,
            _last_review_date(package, "qa") or (package.qa_submitted_at.date() if package.qa_submitted_at else None),
            planned, package.qa_state,
            _name(users, package.dxf_user_id), package.dxf_status, files,
            "delivered" if package.current_stage == "delivered" else "pending",
            package.delivered_at.date() if package.delivered_at else None,
            package.upload_status,
            package_workflow_progress(package, department), package.current_stage,
            _name(users, package.team_leader_user_id), package.remarks,
        ])


def _render_project_progress(workbook, projects, workflows, packages) -> None:
    sheet = _sheet(workbook, "Project Progress", [
        "Project ID", "Project ID Code", "Department", "Workflow Status", "Packages",
        "Production %", "Workflow %", "Measurement Groups (completed/planned base)", "Rework", "Blocked",
    ])
    by_project: dict[int, list[OrthoWorkPackage]] = {}
    for package in packages:
        by_project.setdefault(package.project_id, []).append(package)
    for pid, project_packages in sorted(by_project.items()):
        project = projects.get(pid)
        workflow = workflows.get(pid)
        department = (workflow.performing_department_code if workflow else None) or "ortho"
        progress = aggregate_project_progress(project_packages, department)
        groups = "; ".join(
            f"{group['measurement_type']}: {group['completed_base_quantity']}/{group['planned_base_quantity']} ({group['production_progress_percent']}%)"
            for group in progress["measurement_groups"]
        )
        rework = sum(1 for pkg in project_packages if pkg.rework_cycle_id is not None and pkg.current_stage != "delivered")
        blocked = sum(1 for pkg in project_packages if any(row.status == "blocked" for row in pkg.daily_updates))
        sheet.append([
            pid, project.project_code if project else pid,
            department, workflow.status if workflow else None, len(project_packages),
            progress["production_progress_percent"], progress["workflow_progress_percent"], groups, rework, blocked,
        ])


def _render_employee_production(workbook, projects, packages, users) -> None:
    sheet = _sheet(workbook, "Employee Production", [
        "Project ID Code", "Employee", "Role(s) on Package", "Packages",
        "Planned Qty", "Completed Qty", "Unit", "Production %",
    ])
    rows: dict[tuple[int, str], dict] = {}
    for package in packages:
        project = projects.get(package.project_id)
        total, _ = _package_totals(package)
        for uid, role_name in (
            (package.team_leader_user_id, "team_leader"),
            (package.production_user_id, "production"),
            (package.qc_user_id, "qc"),
            (package.qa_user_id, "qa"),
            (package.dxf_user_id, "dxf"),
        ):
            if not uid:
                continue
            entry = rows.setdefault((package.project_id, uid), {
                "roles": set(), "packages": 0, "planned": Decimal("0"), "completed": Decimal("0"),
                "unit": package.area_unit,
            })
            entry["roles"].add(role_name)
            entry["packages"] += 1
            if role_name == "production":
                entry["planned"] += package.area or Decimal("0")
                entry["completed"] += total
    for (pid, uid), entry in sorted(rows.items()):
        project = projects.get(pid)
        production = package_production_progress(entry["completed"], entry["planned"])
        sheet.append([
            project.project_code if project else pid,
            _name(users, uid), ", ".join(sorted(entry["roles"])), entry["packages"],
            float(entry["planned"]), float(entry["completed"]), entry["unit"], production["progress_percent"],
        ])


def _render_pending_stages(workbook, projects, workflows, packages, users) -> None:
    sheet = _sheet(workbook, "Pending Stages", [
        "Project ID Code", "CODE", "AREA NAME", "Current Stage", "Pending Stage", "Team Lead", "Production", "Target Date",
    ])
    for package in packages:
        project = projects.get(package.project_id)
        workflow = workflows.get(package.project_id)
        department = (workflow.performing_department_code if workflow else None) or "ortho"
        for stage in pending_stages(package, department):
            sheet.append([
                project.project_code if project else package.project_id,
                package.package_code, package.package_name, package.current_stage,
                STAGE_LABELS.get(stage, stage),
                _name(users, package.team_leader_user_id),
                _name(users, package.production_user_id),
                package.target_date,
            ])


def _render_rework_quality(workbook, projects, packages, users) -> None:
    sheet = _sheet(workbook, "Rework & Quality", [
        "Project ID Code", "CODE", "AREA NAME", "Review", "Attempt", "Decision", "Reviewer", "Comments", "Date", "Rework Cycle",
    ])
    for package in packages:
        project = projects.get(package.project_id)
        for review in sorted(package.reviews, key=lambda row: (row.attempt_no or 0, row.id or 0)):
            sheet.append([
                project.project_code if project else package.project_id,
                package.package_code, package.package_name,
                review.review_type.upper(), review.attempt_no, review.decision,
                _name(users, review.reviewer_user_id), review.comments,
                review.created_at.date() if review.created_at else None,
                package.rework_cycle_id,
            ])


def _render_management_summary(workbook, projects, workflows, packages) -> None:
    sheet = _sheet(workbook, "Consolidated Summary", [
        "Project ID", "Project ID Code", "Department", "Workflow Status", "Packages",
        "Production %", "Workflow %", "Measurement Groups", "Delivered", "Rework", "Blocked",
    ])
    by_project: dict[int, list[OrthoWorkPackage]] = {}
    for package in packages:
        by_project.setdefault(package.project_id, []).append(package)
    for pid, project_packages in sorted(by_project.items()):
        project = projects.get(pid)
        workflow = workflows.get(pid)
        department = (workflow.performing_department_code if workflow else None) or "ortho"
        progress = aggregate_project_progress(project_packages, department)
        groups = "; ".join(
            f"{group['measurement_type']}: {group['completed_base_quantity']}/{group['planned_base_quantity']} ({group['production_progress_percent']}%)"
            for group in progress["measurement_groups"]
        )
        delivered = sum(1 for pkg in project_packages if pkg.current_stage == "delivered")
        rework = sum(1 for pkg in project_packages if pkg.rework_cycle_id is not None and pkg.current_stage != "delivered")
        blocked = sum(1 for pkg in project_packages if any(row.status == "blocked" for row in pkg.daily_updates))
        sheet.append([
            pid, project.project_code if project else pid, department,
            workflow.status if workflow else None, len(project_packages),
            progress["production_progress_percent"], progress["workflow_progress_percent"],
            groups, delivered, rework, blocked,
        ])


# ===========================================================================================
# V8.2 project workbook: AREA MASTER (exact 26 columns) + FILE ACTIVITY + EMPLOYEE PRODUCTIVITY
# ===========================================================================================

def _fmt_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _date_part(iso: str | None) -> str | None:
    return iso[:10] if iso else None


def _time_part(iso: str | None) -> str | None:
    if not iso:
        return None
    return iso[11:19] if len(iso) >= 19 else iso[11:]


def _render_area_master(workbook, packages, users, agg, items_by_pkg) -> None:
    """AREA MASTER — the exact 26-column business layout, populated live.

    When an area tracks files (V8.3), the stage allotment columns show the assignees,
    the stage dates show the real stage completion, and ACTUAL KM sums the actual
    Production quantities. Legacy areas without files keep the previous semantics.
    """
    sheet = _sheet(workbook, "AREA MASTER", list(AREA_MASTER_HEADERS))
    for package in packages:
        total, legacy_files = _package_totals(package)
        planned = float(package.area) if package.area is not None else None
        file_agg = agg.get(package.id, {})
        rows = items_by_pkg.get(package.id, [])
        expected = file_agg.get("files_expected", 0)
        if expected:
            # ACTUAL KM = cumulative actual Production quantity across ALL valid sessions
            # (partial "save progress" sessions included). NO OF FILES stays distinct.
            actual = sum(
                (r["production_quantity"] or 0.0) for r in rows if r["is_active"]
            )
            def assignees(key: str) -> str | None:
                names = sorted({r[key] for r in rows if r["is_active"] and r.get(key)})
                return ", ".join(names) if names else None

            def stage_date(key: str) -> date | None:
                dates = [r[key][:10] for r in rows if r["is_active"] and r.get(key)]
                return max(date.fromisoformat(d) for d in dates) if dates else None

            prod_done = file_agg.get("files_production_done", 0)
            qc_passed = file_agg.get("files_qc_passed", 0)
            qa_passed = file_agg.get("files_qa_passed", 0)
            delivered = file_agg.get("files_delivered", 0)
            production_status = ("completed" if prod_done == expected
                                 else "in_progress" if prod_done else "not_started")
            qc_status = ("approved" if qc_passed == expected
                         else "rework" if file_agg.get("qc_rework") else
                         "in_progress" if (qc_passed or file_agg.get("qc_pending") != expected) else "not_started")
            qa_status = ("approved" if qa_passed == expected
                         else "rework" if file_agg.get("qa_rework") else
                         "in_progress" if qa_passed else "not_started")
            delivered_status = "delivered" if delivered == expected else "pending"
            delivered_date = stage_date("delivery_at")
            length = planned
            actual_km = actual
            prod_allotment = assignees("production_user")
            qc_allotment = assignees("qc_user")
            qa_allotment = assignees("qa_user")
            prod_date = stage_date("production_end")
            qc_date = stage_date("qc_end")
            qa_date = stage_date("qa_end")
            no_of_files = expected
        else:
            production_status = package.production_state
            qc_status = package.qc_state
            qa_status = package.qa_state
            delivered_status = "delivered" if package.current_stage == "delivered" else "pending"
            delivered_date = package.delivered_at.date() if package.delivered_at else None
            length = planned
            actual_km = float(total)
            prod_allotment = planned
            qc_allotment = planned
            qa_allotment = planned
            prod_date = package.production_completed_at.date() if package.production_completed_at else None
            qc_date = _last_review_date(package, "qc") or (package.qc_submitted_at.date() if package.qc_submitted_at else None)
            qa_date = _last_review_date(package, "qa") or (package.qa_submitted_at.date() if package.qa_submitted_at else None)
            no_of_files = legacy_files
        sheet.append([
            package.lot_batch,
            package.package_code,
            package.package_name,
            length,
            package.inspected_at.date() if package.inspected_at else None,
            package.supply_date,
            actual_km,
            package.imported_at.date() if package.imported_at else None,
            package.import_status,
            prod_date,
            prod_allotment,
            production_status,
            qc_date,
            qc_allotment,
            qc_status,
            qa_date,
            qa_allotment,
            qa_status,
            _name(users, package.dxf_user_id),
            package.dxf_status,
            no_of_files,
            stage_status(package, "inspection"),
            delivered_status,
            delivered_date,
            package.upload_status,
            package.remarks,
        ])


def _render_file_activity(workbook, db, projects, packages, item_rows) -> None:
    sheet = _sheet(workbook, "FILE ACTIVITY", list(FILE_ACTIVITY_HEADERS))
    pkg_by_id = {pkg.id: pkg for pkg in packages}
    for row in item_rows:
        if not row["is_active"]:
            continue  # deactivated files leave the active workflow; DB history is preserved
        package = pkg_by_id.get(row["work_package_id"])
        if package is None:
            continue
        project = projects.get(package.project_id)
        sheet.append([
            project.project_code if project else package.project_id,
            package.lot_batch,
            package.package_code,
            package.package_name,
            row["item_number"],
            row["item_name"],
            row["planned_quantity"],
            row["planned_unit"],
            row["supply_date"],
            row["production_employee"] or row["production_user"],
            row["production_target_date"],
            _date_part(row["production_start"]),
            _time_part(row["production_start"]),
            _date_part(row["production_end"]),
            _time_part(row["production_end"]),
            _fmt_duration(row["production_duration_seconds"]),
            row["production_quantity"],
            row["production_status"],
            row["production_deadline"].get("status"),
            row["production_remarks"],
            row["delay_category"],
            row["affected_item_number"],
            row["delay_reason"],
            "YES" if row["system_malfunction"] else "NO",
            row["delay_remarks"],
            row["qc_employee"] or row["qc_user"],
            row["qc_target_date"],
            _date_part(row["qc_start"]),
            _time_part(row["qc_start"]),
            _date_part(row["qc_end"]),
            _time_part(row["qc_end"]),
            _fmt_duration(row["qc_duration_seconds"]),
            row["qc_status"],
            row["qc_deadline"].get("status"),
            row["qc_remarks"],
            row["qa_employee"] or row["qa_user"],
            row["qa_target_date"],
            _date_part(row["qa_start"]),
            _time_part(row["qa_start"]),
            _date_part(row["qa_end"]),
            _time_part(row["qa_end"]),
            _fmt_duration(row["qa_duration_seconds"]),
            row["qa_status"],
            row["qa_deadline"].get("status"),
            row["qa_remarks"],
            "YES" if row["ready_for_delivery"] else "NO",
            row["delivery_by"],
            _date_part(row["delivery_at"]),
            _time_part(row["delivery_at"]),
            row["delivery_status"],
            row["delivery_remarks"],
        ])


def _render_employee_productivity(workbook, db, projects, packages, rows) -> None:
    """EMPLOYEE PRODUCTIVITY — per employee/day/area output including assigned/completed
    and on-time / late / rework counts (all derived server-side)."""
    from app.modules.operations.production_items import employee_file_totals

    sheet = _sheet(workbook, "EMPLOYEE PRODUCTIVITY", list(EMPLOYEE_PRODUCTIVITY_HEADERS))
    pkg_by_id = {pkg.id: pkg for pkg in packages}
    stats_by_uid: dict[int, dict] = {}
    for total in employee_file_totals(db, [pkg.id for pkg in packages]):
        stats_by_uid[total["employee_user_id"]] = total
    for row in rows:
        package = pkg_by_id.get(row["work_package_id"])
        project = projects.get(package.project_id) if package else None
        stats = stats_by_uid.get(row["employee_user_id"], {})
        role = (row["role"] or "production").lower()
        if "qc" in role:
            assigned, pending = stats.get("qc_assigned", 0), stats.get("qc_pending", 0)
        elif "qa" in role:
            assigned, pending = stats.get("qa_assigned", 0), stats.get("qa_pending", 0)
        else:
            assigned, pending = stats.get("production_assigned", 0), stats.get("production_pending", 0)
        # Files WORKED / COMPLETED are scoped to this row's day so one physical file is
        # never multiplied across days; ASSIGNED / PENDING are current-state counts.
        completed = row["files_completed"]
        hours = (row["total_seconds"] or 0) / 3600.0
        quantity = row["quantity_completed"] or 0
        files_worked = row["files_worked"]
        sheet.append([
            row["employee"],
            (row["role"] or "").replace("_", " ").title() or None,
            project.project_code if project else None,
            row.get("lot") or (package.lot_batch if package else None),
            row["area_code"],
            row["area_name"],
            row["date"],
            assigned,
            completed,
            pending,
            files_worked,
            row["quantity_completed"],
            row["unit"],
            _fmt_duration(row["production_seconds"]),
            _fmt_duration(row["qc_seconds"]),
            _fmt_duration(row["qa_seconds"]),
            _fmt_duration(row["total_seconds"]),
            round(quantity / hours, 3) if hours else None,
            round(files_worked / hours, 3) if hours else None,
            row["on_time_count"],
            row["late_count"],
            row["rework_count"],
            row["system_malfunction_count"],
            row["remarks"] or None,
        ])


_STAGE_STATUS_LABELS = {
    "in_progress": "Progress Saved",
    "completed": "Completed",
    "passed": "Passed",
    "approved": "Approved",
    "rejected": "Rejected",
    "rework": "Rework",
}


def _iso_date(value: str | None) -> str | None:
    return value[:10] if value else None


def _iso_time(value: str | None) -> str | None:
    return value[11:19] if value else None


def _activity_label(stage: str, status: str | None) -> str | None:
    if status is None:
        return None
    if stage == "production":
        return "Completed" if status == "completed" else "Progress Saved"
    return _STAGE_STATUS_LABELS.get(status, status.replace("_", " ").title())


def _render_activity_history(workbook, db, projects, packages) -> None:
    """ACTIVITY HISTORY — one row per Production session / QC / QA attempt (append-only;
    multiple sessions of one physical file are never merged or lost)."""
    from app.modules.operations.production_items import activity_rows_for_packages

    sheet = _sheet(workbook, "ACTIVITY HISTORY", list(ACTIVITY_HISTORY_HEADERS))
    pkg_by_id = {pkg.id: pkg for pkg in packages}
    for act in activity_rows_for_packages(db, [pkg.id for pkg in packages]):
        package = pkg_by_id.get(act["work_package_id"])
        project = projects.get(package.project_id) if package else None
        sheet.append([
            project.project_code if project else None,
            act["lot_batch"],
            act["package_code"],
            act["area_name"],
            act["item_number"],
            act["item_name"],
            act["planned_quantity"],
            act["planned_unit"],
            (act["stage"] or "").upper() or None,
            act["employee"],
            (act["performed_role"] or act["stage"] or "").replace("_", " ").title() or None,
            act["date"],
            _iso_time(act["started_at"]),
            _iso_time(act["ended_at"]),
            _fmt_duration(act["duration_seconds"]),
            act["quantity_completed"],
            act["unit"],
            _activity_label(act["stage"], act["status"]),
            "YES" if act["finalized"] else "NO",
            act["delay_category"],
            act["delay_reason"],
            "YES" if act["system_malfunction"] else "NO",
            act["remarks"],
        ])


def _render_legacy_tile_activity(workbook, db, projects, packages) -> None:
    """LEGACY TILE ACTIVITY — reproduces the business information of the legacy tile
    workbook (Production / QC / QA per tile with date, technician, start/comp time,
    time taken, status, length, remarks) from REAL ERP activity data only."""
    from app.modules.operations.production_items import activity_rows_for_packages

    sheet = _sheet(workbook, "LEGACY TILE ACTIVITY", list(LEGACY_TILE_ACTIVITY_HEADERS))
    acts = activity_rows_for_packages(db, [pkg.id for pkg in packages])
    order = {"production": 0, "qc": 1, "qa": 2}
    for act in sorted(acts, key=lambda a: (order.get(a["stage"], 9), a["work_package_item_id"], a["activity_id"])):
        sheet.append([
            (act["stage"] or "").upper() or None,
            act["item_name"] or act["item_number"],
            act["date"],
            act["employee"],
            _iso_time(act["started_at"]),
            _iso_time(act["ended_at"]),
            _fmt_duration(act["duration_seconds"]),
            _activity_label(act["stage"], act["status"]),
            act["quantity_completed"] if act["stage"] == "production" else None,
            act["remarks"],
        ])


def _render_project_workbook(db, workbook, projects, workflows, packages, users) -> None:
    from app.modules.operations.production_items import (
        build_item_rows,
        employee_productivity_rows,
        file_aggregates_for_packages,
    )

    package_ids = [pkg.id for pkg in packages]
    item_rows = build_item_rows(db, package_ids, users=users)
    agg = file_aggregates_for_packages(db, package_ids)
    items_by_pkg: dict[int, list[dict]] = {}
    for row in item_rows:
        items_by_pkg.setdefault(row["work_package_id"], []).append(row)
    _render_area_master(workbook, packages, users, agg, items_by_pkg)
    _render_file_activity(workbook, db, projects, packages, item_rows)
    _render_employee_productivity(
        workbook, db, projects, packages, employee_productivity_rows(db, package_ids)
    )
    _render_activity_history(workbook, db, projects, packages)
    _render_legacy_tile_activity(workbook, db, projects, packages)




