from __future__ import annotations

from pathlib import Path
import os
import sys

from sqlalchemy import or_, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
backend_root_text = str(BACKEND_ROOT)
if backend_root_text not in sys.path:
    sys.path.insert(0, backend_root_text)

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.service import ortho_dashboard_payload

PM_EMAIL = os.getenv("V710_ORTHO_PM_EMAIL", "ortho@nakshatech.com").strip().lower()


def codes(rows: list[FinanceProject]) -> str:
    return ", ".join(project.project_code for project in rows) if rows else "(none)"


with SessionLocal() as db:
    pm = db.scalar(select(User).where(User.email.ilike(PM_EMAIL)))
    if pm is None:
        raise SystemExit(f"V710_ORTHO_PM_USER_MISSING: {PM_EMAIL}")

    assigned = db.scalars(
        select(FinanceProject)
        .join(FinanceProjectMasterProfile, FinanceProjectMasterProfile.project_id == FinanceProject.id)
        .where(FinanceProjectMasterProfile.project_manager_id == pm.id)
        .order_by(FinanceProject.project_code.asc())
    ).all()

    reporting_only = db.scalars(
        select(FinanceProject)
        .join(FinanceProjectMasterProfile, FinanceProjectMasterProfile.project_id == FinanceProject.id)
        .where(
            FinanceProjectMasterProfile.reporting_manager_id == pm.id,
            or_(
                FinanceProjectMasterProfile.project_manager_id.is_(None),
                FinanceProjectMasterProfile.project_manager_id != pm.id,
            ),
        )
        .order_by(FinanceProject.project_code.asc())
    ).all()

    payload = ortho_dashboard_payload(db, actor=pm, effective_role="ortho")
    master_ids = {int(row["id"]) for row in payload["project_master"]}
    assigned_ids = {project.id for project in assigned}
    if master_ids != assigned_ids:
        raise SystemExit(
            "V710_FINANCE_ASSIGNMENT_DISCOVERY_MISMATCH: "
            f"database={sorted(assigned_ids)} dashboard={sorted(master_ids)}"
        )

    visible_ids = {int(row["profile"]["project_id"]) for row in payload["projects"]}
    pending = [project for project in assigned if project.id not in visible_ids]

    print(f"V710_ORTHO_PM: {pm.full_name} <{pm.email}> id={pm.id}")
    print(f"V710_FINANCE_ASSIGNED_PROJECTS: {codes(assigned)}")
    print(f"V710_ALREADY_VISIBLE_IN_ORTHO: {', '.join(row['project']['project_code'] for row in payload['projects']) if payload['projects'] else '(none)'}")
    print(f"V710_WAITING_ACTIVATION: {codes(pending)}")
    print(f"V710_REPORTING_MANAGER_ONLY_PROJECTS: {codes(reporting_only)}")
    if reporting_only:
        print("V710_REPORTING_ONLY_HINT: Edit these Finance projects and set Project Manager to the Ortho PM. Reporting Manager alone does not grant Ortho ownership.")
    print("V710_ORTHO_FINANCE_VISIBILITY_OK")
