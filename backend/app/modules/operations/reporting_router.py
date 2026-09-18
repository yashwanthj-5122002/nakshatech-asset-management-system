from __future__ import annotations

import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.operations.reporting_service import REPORTING_ROLES, powerbi_semantic_payload, reporting_dashboard_payload
from app.modules.operations.service import normalize_role

router = APIRouter(prefix="/reporting", tags=["Phase 8 Reporting"])


def _role(auth: CurrentAuth) -> str:
    return normalize_role(auth.effective_role)


def _allow_reporting(auth: CurrentAuth) -> str:
    role = _role(auth)
    if role not in REPORTING_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reporting dashboard is not available for this role")
    return role


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _csv_response(rows: list[dict], filename: str) -> Response:
    output = StringIO()
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(output, fieldnames=fieldnames or ["no_data"])
    writer.writeheader()
    if rows:
        writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard")
def reporting_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow_reporting(auth)
    try:
        return reporting_dashboard_payload(db, actor=auth.user, effective_role=role)
    except Exception as exc:
        raise _write_error(exc) from exc


@router.get("/powerbi/semantic-model")
def reporting_powerbi_semantic_model(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow_reporting(auth)
    try:
        return powerbi_semantic_payload(db, actor=auth.user, effective_role=role)
    except Exception as exc:
        raise _write_error(exc) from exc


@router.get("/powerbi/projects.csv")
def reporting_powerbi_projects_csv(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow_reporting(auth)
    try:
        payload = powerbi_semantic_payload(db, actor=auth.user, effective_role=role)
        return _csv_response(payload["datasets"]["project_facts"], "nakshatech_project_facts.csv")
    except Exception as exc:
        raise _write_error(exc) from exc


@router.get("/powerbi/departments.csv")
def reporting_powerbi_departments_csv(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow_reporting(auth)
    try:
        payload = powerbi_semantic_payload(db, actor=auth.user, effective_role=role)
        return _csv_response(payload["datasets"]["department_facts"], "nakshatech_department_facts.csv")
    except Exception as exc:
        raise _write_error(exc) from exc
