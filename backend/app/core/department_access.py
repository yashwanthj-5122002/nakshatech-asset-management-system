"""Server-side department scope enforcement.

A normal employee (``role='employee'``) may only reach operational data for the
department their authenticated identity belongs to. The department is resolved
server-side from the Employee Master record linked to the session user (falling
back to the profile department) — never from a frontend-supplied parameter.

Privileged roles (admin, software_team, management, finance, hr, it, drone, bd,
bim) keep their existing access. Technical PM roles (ortho, lidar, civil,
laser_scanning, mobile_mapping) are scoped to their own department.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.departments import (
    DEPARTMENT_FOR_PM_ROLE,
    TECHNICAL_PM_ROLES,
    normalize_department_code,
)
from app.core.roles import (
    ADMIN_ROLE,
    BD_ROLE,
    BIM_ROLE,
    DRONE_ROLE,
    FINANCE_ROLE,
    HR_ROLE,
    IT_ROLE,
    MANAGEMENT_ROLE,
    SOFTWARE_TEAM_ROLE,
)
from app.models.entities import User
from app.modules.employee_portal.employee_master import authenticated_department_code
from app.modules.operations.models import ProjectWorkflow

DEPARTMENT_ACCESS_PRIVILEGED_ROLES = frozenset(
    {
        ADMIN_ROLE,
        SOFTWARE_TEAM_ROLE,
        MANAGEMENT_ROLE,
        FINANCE_ROLE,
        HR_ROLE,
        IT_ROLE,
        DRONE_ROLE,
        BD_ROLE,
        BIM_ROLE,
    }
)

DEPARTMENT_SCOPE_DENIED = "Your account is not assigned to this department"


def user_department_code(db: Session, user: User) -> str | None:
    """Department for a user: Employee Master first, profile fallback."""
    return authenticated_department_code(db, user)


def project_department_code(db: Session, project_id: int) -> str | None:
    """Performing department of a project from the authoritative workflow row."""
    return db.scalar(
        select(ProjectWorkflow.performing_department_code).where(ProjectWorkflow.project_id == project_id)
    )


def ensure_department_access(db: Session, user: User, effective_role: str, department_code: str) -> None:
    """Raise 403 unless the authenticated user may access ``department_code``.

    Employees whose department cannot be resolved (no Employee Master link and an
    unrecognized profile department) keep the legacy assignment-based visibility;
    the per-package assignment checks remain the enforcement for them.
    """
    role = (effective_role or "").strip().lower()
    if role in DEPARTMENT_ACCESS_PRIVILEGED_ROLES:
        return
    if role in TECHNICAL_PM_ROLES:
        if DEPARTMENT_FOR_PM_ROLE.get(role) == department_code:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEPARTMENT_SCOPE_DENIED)
    user_department = authenticated_department_code(db, user)
    if user_department is None:
        return
    if normalize_department_code(user_department) == department_code:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEPARTMENT_SCOPE_DENIED)


def ensure_project_department_access(db: Session, user: User, effective_role: str, project_id: int) -> None:
    """Raise 403 unless the user may access operational data for ``project_id``."""
    role = (effective_role or "").strip().lower()
    if role in DEPARTMENT_ACCESS_PRIVILEGED_ROLES:
        return
    department_code = project_department_code(db, project_id)
    if department_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_department_access(db, user, role, department_code)
