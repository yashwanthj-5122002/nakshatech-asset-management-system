
from __future__ import annotations

import io
import os
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def build_project_tracking_router(
    authenticate: Callable,
    reporting_service,
) -> APIRouter:

    router = APIRouter(
        prefix="/api/management/project-tracking-sales",
        tags=["Project Tracking and Sales"],
    )

    async def require_management(user=Depends(authenticate)):
        allowed = {
            value.strip()
            for value in os.getenv(
                "PROJECT_TRACKING_ALLOWED_USER_IDS", ""
            ).split(",")
            if value.strip()
        }

        if not allowed:
            raise HTTPException(
                503, "Management reporting is not configured"
            )

        if isinstance(user, dict):
            user_id = user.get("id") or user.get("user_id")
        else:
            user_id = getattr(
                user, "id", getattr(user, "user_id", None)
            )

        if user_id is None or str(user_id) not in allowed:
            raise HTTPException(403, "Access denied")

        return user

    def validate_dates(start: date, end: date):
        if start > end:
            raise HTTPException(
                422, "Start date must precede end date"
            )

    async def get_report(start: date, end: date):
        validate_dates(start, end)
        return await reporting_service.get_dashboard(
            start, end
        )

    @router.get("/access")
    async def check_access(
        user=Depends(require_management),
    ):
        return {"allowed": True}

    @router.get("/dashboard")
    async def dashboard(
        start: date,
        end: date,
        user=Depends(require_management),
    ):
        result = await get_report(start, end)

        return JSONResponse(
            content=jsonable_encoder(result),
            headers={"Cache-Control": "no-store, private"},
        )

    @router.get("/projects/{project_id}")
    async def project_details(
        project_id: str,
        end: date,
        user=Depends(require_management),
    ):
        result = await reporting_service.get_project_detail(
            project_id, end
        )

        if result is None:
            raise HTTPException(404, "Project not found")

        return JSONResponse(
            content=jsonable_encoder(result),
            headers={"Cache-Control": "no-store, private"},
        )

    @router.get("/export/{file_type}")
    async def export_report(
        file_type: str,
        start: date,
        end: date,
        user=Depends(require_management),
    ):
        if file_type not in {"xlsx", "pdf"}:
            raise HTTPException(400, "Unsupported format")

        report = await get_report(start, end)
        projects = report.get("projects", [])
        summary = report.get("summary", {})

        columns = [
            ("Project", "project_name"),
            ("Client", "client_name"),
            ("Department", "department"),
            ("Manager", "manager"),
            ("Sales (INR)", "sales_approved"),
            ("Received (INR)", "payments_received"),
            ("Outstanding (INR)", "outstanding"),
        ]

        def safe_text(value):
            text = str(value or "")
            if text.startswith(("=", "+", "-", "@")):
                return "'" + text
            return text

        if file_type == "xlsx":
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Project Tracking"

            sheet.append([label for label, _ in columns])

            for project in projects:
                values = []
                for _, key in columns:
                    value = project.get(key, "")
                    if key in {
                        "sales_approved",
                        "payments_received",
                        "outstanding",
                    }:
                        value = int(value or 0) / 100
                    else:
                        value = safe_text(value)
                    values.append(value)
                sheet.append(values)

            buffer = io.BytesIO()
            workbook.save(buffer)
            buffer.seek(0)

            return StreamingResponse(
                buffer,
                media_type=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                headers={
                    "Content-Disposition":
                    'attachment; filename="project-tracking.xlsx"',
                    "Cache-Control": "no-store, private",
                },
            )

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        def header():
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(
                36, height - 45,
                "NakshaTech - Project Tracking and Sales"
            )
            pdf.setFont("Helvetica", 9)
            pdf.drawString(
                36, height - 63,
                f"Period: {start} to {end}"
            )

        header()
        y = height - 100

        for label, key in [
            ("Approved Sales", "sales_approved"),
            ("Payments Received", "payments_received"),
            ("Expenses", "expenses"),
            ("Bad Debts", "bad_debts"),
            ("Outstanding", "outstanding"),
        ]:
            amount = int(summary.get(key, 0)) / 100
            pdf.drawString(
                36, y, f"{label}: INR {amount:,.2f}"
            )
            y -= 17

        y -= 20

        for project in projects:
            if y < 65:
                pdf.showPage()
                header()
                y = height - 100

            name = str(
                project.get("project_name", "Unnamed")
            )[:42]
            received = (
                int(project.get("payments_received", 0))
                / 100
            )
            outstanding = (
                int(project.get("outstanding", 0))
                / 100
            )

            pdf.drawString(36, y, name)
            pdf.drawRightString(
                width - 36, y,
                f"Received: {received:,.2f} | "
                f"Pending: {outstanding:,.2f}"
            )
            y -= 18

        pdf.save()
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                'attachment; filename="project-tracking.pdf"',
                "Cache-Control": "no-store, private",
            },
        )

    return router
