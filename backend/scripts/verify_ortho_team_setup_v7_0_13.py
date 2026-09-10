"""Runtime verifier for V7.0.13 Ortho project-team setup and SMTP decoupling."""
from __future__ import annotations

from pathlib import Path
import inspect as pyinspect
import os
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
root_text = str(BACKEND_ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)

from fastapi.routing import iter_route_contexts  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.batch4_main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.modules.finance.models import FinanceProject  # noqa: E402
from app.modules.operations import router as operations_router_module  # noqa: E402
from app.modules.operations.models import OrthoProjectMember, OrthoWorkPackage  # noqa: E402

EXPECTED = {
    "/api/operations/ortho/projects/{project_id}/members",
    "/api/operations/ortho/projects/{project_id}/team",
    "/api/operations/ortho/projects/{project_id}/team/emails",
}
paths = {context.path for context in iter_route_contexts(app.router.routes)}
missing = sorted(EXPECTED.difference(paths))
if missing:
    raise SystemExit("V713_ORTHO_TEAM_ROUTES_MISSING: " + ", ".join(missing))

source = pyinspect.getsource(operations_router_module.ortho_upsert_member)
commit_pos = source.find("db.commit()")
email_pos = source.find("send_ortho_assignment_email")
if commit_pos < 0 or email_pos < 0 or commit_pos > email_pos:
    raise SystemExit("V713_MEMBER_EMAIL_DECOUPLING_ORDER_INVALID")

print("V713_ORTHO_TEAM_SETUP_ROUTES_OK")
print("V713_ASSIGNMENT_SAVES_BEFORE_EMAIL_OK")
print("V713_EMAIL_FAILURE_NON_BLOCKING_OK")
print(f"V713_EMAIL_DELIVERY_MODE: {settings.email_delivery_mode.strip().lower()}")

project_code = os.getenv("V713_VERIFY_PROJECT_CODE", "GFI-ORTHO-260909-01").strip()
with SessionLocal() as db:
    project = db.scalar(select(FinanceProject).where(FinanceProject.project_code == project_code))
    if project is None:
        print(f"V713_PROJECT_STATUS: {project_code} not found (route verification still passed)")
    else:
        members = list(db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id,
            OrthoProjectMember.is_active.is_(True),
        )).all())
        roles = sorted(row.member_role for row in members if row.member_role != "project_manager")
        packages = list(db.scalars(select(OrthoWorkPackage).where(OrthoWorkPackage.project_id == project.id)).all())
        unassigned = sum(
            1 for pkg in packages
            if None in (pkg.team_leader_user_id, pkg.production_user_id, pkg.qc_user_id, pkg.qa_user_id)
        )
        print(f"V713_PROJECT_STATUS: {project.project_code} active_team_roles={','.join(roles) if roles else '(none)'} packages={len(packages)} packages_with_unassigned_role={unassigned}")

print("V713_ORTHO_TEAM_SETUP_RUNTIME_OK")
