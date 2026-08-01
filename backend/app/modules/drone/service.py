from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import Drone, DroneLocation, User
from app.modules.drone.import_service import ALL_ATTRIBUTE_GROUPS, DISPLAY_LABELS, NORMALIZED_FIELDS, parse_workbook
from app.modules.drone.models import (
    DroneAssetAttributeDefinition,
    DroneAssetKit,
    DroneAuditLog,
    DroneHDDDelivery,
    DroneImportBatch,
    DroneImportException,
    DroneImportRow,
    DroneKitComponent,
    DroneOperation,
    DroneOperationItem,
    DroneAssetMovement,
    DroneWorkRecord,
    DroneProject,
    DroneSurveyAsset,
    DroneTelecomConnection,
    DroneUINRegistration,
)

ASSET_STATUSES = {
    "available", "reserved", "assigned_to_employee", "deployed_to_project", "in_transit",
    "under_maintenance", "sent_for_service", "under_calibration", "with_vendor",
    "pending_verification", "not_verified", "missing", "damaged", "retired", "disposed",
}
PROJECT_STATUSES = {"planned", "active", "on_hold", "delayed", "completed", "closure_pending", "closed", "cancelled"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prefix(category: str, asset_name: str) -> str:
    text = f"{category} {asset_name}".lower()
    if "drone" in text or "uav" in text or "vtol" in text:
        return "NT-UAV"
    if "survey" in text or "dgps" in text or "rtk" in text or "rover" in text:
        return "NT-DGPS"
    if "battery" in text:
        return "NT-BAT"
    if "storage" in text or "hdd" in text:
        return "NT-HDD"
    if "camera" in text or "sensor" in text:
        return "NT-CAM"
    if "controller" in text:
        return "NT-CTRL"
    if "computing" in text or "laptop" in text or "mobile" in text:
        return "NT-COMP"
    if "connectivity" in text or "modem" in text:
        return "NT-NET"
    return "NT-EQP"


def next_code(db: Session, model, field, prefix: str, width: int = 4) -> str:
    values = db.scalars(select(field).where(field.like(f"{prefix}-%"))).all()
    highest = 0
    for value in values:
        if not value:
            continue
        match = re.search(r"(\d+)$", str(value))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:0{width}d}"


def asset_dict(asset: DroneSurveyAsset, db: Session | None = None) -> dict[str, Any]:
    allocated_quantity = active_asset_quantity(db, asset.id) if db is not None else 0.0
    return {
        "id": asset.id,
        "asset_tag": asset.asset_tag,
        "imported_equipment_id": asset.imported_equipment_id,
        "asset_name": asset.asset_name,
        "category": asset.category,
        "subcategory": asset.subcategory,
        "manufacturer": asset.manufacturer,
        "model_number": asset.model_number,
        "serial_number": asset.serial_number,
        "raw_serial_number": asset.raw_serial_number,
        "quantity": asset.quantity,
        "allocated_quantity": allocated_quantity,
        "available_quantity": max(float(asset.quantity) - allocated_quantity, 0.0),
        "raw_quantity": asset.raw_quantity,
        "unit_of_measure": asset.unit_of_measure,
        "tracking_type": asset.tracking_type,
        "calibration_required": asset.calibration_required,
        "maintenance_required": asset.maintenance_required,
        "technical_frequency": asset.technical_frequency,
        "responsible_function": asset.responsible_function,
        "last_calibration_date": asset.last_calibration_date.isoformat() if asset.last_calibration_date else None,
        "next_calibration_date": asset.next_calibration_date.isoformat() if asset.next_calibration_date else None,
        "equipment_tolerance": asset.equipment_tolerance,
        "current_status": asset.current_status,
        "working_condition": asset.working_condition,
        "current_custodian": asset.current_custodian,
        "associated_people": asset.associated_people or [],
        "current_project_id": asset.current_project_id,
        "current_project": asset.project.project_name if asset.project else None,
        "current_location": asset.current_location,
        "parent_kit_id": asset.parent_kit_id,
        "parent_kit": asset.parent_kit.kit_name if asset.parent_kit else None,
        "is_serialized": asset.is_serialized,
        "is_telemetry_capable": asset.is_telemetry_capable,
        "source_workbook": asset.source_workbook,
        "source_sheet": asset.source_sheet,
        "source_row": asset.source_row,
        "source_section": asset.source_section,
        "original_raw_payload": asset.original_raw_payload,
        "original_header_map": asset.original_header_map,
        "reconciliation_status": asset.reconciliation_status,
        "remarks": asset.remarks,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }


def project_dict(project: DroneProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "client": project.client,
        "project_manager": project.project_manager,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "expected_end_date": project.expected_end_date.isoformat() if project.expected_end_date else None,
        "actual_completion_date": project.actual_completion_date.isoformat() if project.actual_completion_date else None,
        "closure_date": project.closure_date.isoformat() if project.closure_date else None,
        "status": project.status,
        "financial_year": project.financial_year,
        "location": project.location,
        "project_area": project.project_area,
        "description": project.description,
        "remarks": project.remarks,
        "created_at": project.created_at.isoformat(),
    }


def kit_dict(kit: DroneAssetKit) -> dict[str, Any]:
    active_components = [component for component in kit.components if component.removed_at is None]
    unavailable_states = {"missing", "damaged", "under_maintenance", "sent_for_service", "retired", "disposed"}
    def component_available(component: DroneKitComponent) -> bool:
        return component.asset.current_status not in unavailable_states and float(component.asset.quantity or 0) >= float(component.required_quantity or 1)
    available = sum(component_available(component) for component in active_components)
    essential = [component for component in active_components if component.is_essential]
    essential_available = sum(component_available(component) for component in essential)
    readiness = round((essential_available / len(essential)) * 100, 1) if essential else 100.0
    return {
        "id": kit.id,
        "kit_tag": kit.kit_tag,
        "kit_name": kit.kit_name,
        "model": kit.model,
        "unit_number": kit.unit_number,
        "uin": kit.uin,
        "current_status": kit.current_status,
        "current_custodian": kit.current_custodian,
        "current_project_id": kit.current_project_id,
        "current_project": kit.project.project_name if kit.project else None,
        "current_location": kit.current_location,
        "remarks": kit.remarks,
        "component_count": len(active_components),
        "available_components": available,
        "missing_components": len(active_components) - available,
        "readiness_percentage": readiness,
        "components": [
            {
                "id": component.id,
                "asset_id": component.asset_id,
                "asset_tag": component.asset.asset_tag,
                "component_name": component.component_name,
                "serial_number": component.asset.serial_number,
                "quantity": component.asset.quantity,
                "status": component.asset.current_status,
                "is_essential": component.is_essential,
            }
            for component in active_components
        ],
    }


def ensure_attribute_registry(db: Session) -> None:
    existing = {(row.source_sheet, row.original_header) for row in db.scalars(select(DroneAssetAttributeDefinition)).all()}
    for source_sheet, headers in ALL_ATTRIBUTE_GROUPS.items():
        for header in headers:
            key = (source_sheet, header)
            if key in existing:
                continue
            db.add(DroneAssetAttributeDefinition(
                source_sheet=source_sheet,
                original_header=header,
                display_label=DISPLAY_LABELS.get(header, header.strip()),
                normalized_field=NORMALIZED_FIELDS.get(header),
                data_type="date" if "Date" in header else "number" if header in {"QTY", "Quantity", "Qty ", "Sq.Km"} else "text",
                dashboard_usage=header in {"DGPS Details", "Equipment Manufacturer", "Model Number", "Working", "UIN Status"},
            ))
    db.flush()


def create_import_preview(db: Session, content: bytes, filename: str, reporting_month: str | None, user: User) -> DroneImportBatch:
    parsed = parse_workbook(content, filename)
    if reporting_month:
        parsed["summary"]["reporting_month"] = reporting_month
    batch = DroneImportBatch(
        batch_code=next_code(db, DroneImportBatch, DroneImportBatch.batch_code, "DRN-IMP"),
        source_workbook=filename,
        reporting_month=parsed["summary"].get("reporting_month"),
        status="preview",
        summary=parsed["summary"],
        created_by=user.email,
    )
    db.add(batch)
    db.flush()
    ensure_attribute_registry(db)

    existing_serials = {value.lower() for value in db.scalars(select(DroneSurveyAsset.serial_number).where(DroneSurveyAsset.serial_number.is_not(None))).all() if value}
    existing_ids = {value.lower() for value in db.scalars(select(DroneSurveyAsset.imported_equipment_id).where(DroneSurveyAsset.imported_equipment_id.is_not(None))).all() if value}

    for record in parsed["records"]:
        normalized = record["normalized_payload"]
        issues = list(record["issues"])
        classification = record["classification"]
        serial = normalized.get("serial_number") or normalized.get("hdd_serial_number")
        imported_id = normalized.get("imported_equipment_id")
        if serial and str(serial).lower() in existing_serials:
            issues.append("serial_already_in_master")
            classification = "probable_match"
        if imported_id and str(imported_id).lower() in existing_ids:
            issues.append("equipment_id_already_in_master")
            classification = "probable_match"
        row = DroneImportRow(
            batch_id=batch.id,
            source_sheet=record["source_sheet"],
            source_row=record["source_row"],
            source_section=record["source_section"],
            record_type=record["record_type"],
            original_raw_payload=record["original_raw_payload"],
            original_header_map=record["original_header_map"],
            normalized_payload=normalized,
            issues=issues,
            classification=classification,
            reconciliation_status="needs_review" if issues else "ready",
        )
        db.add(row)
        db.flush()
        for issue in issues:
            severity = "critical" if issue in {"serial_already_in_master", "equipment_id_already_in_master"} else "warning"
            db.add(DroneImportException(
                batch_id=batch.id,
                row_id=row.id,
                severity=severity,
                exception_type=issue,
                message=issue.replace("_", " ").title(),
            ))
    db.add(DroneAuditLog(
        action="import_preview_created",
        entity_type="import_batch",
        entity_id=batch.id,
        details=parsed["summary"],
        performed_by=user.email,
    ))
    db.commit()
    db.refresh(batch)
    return batch


def batch_dict(batch: DroneImportBatch, include_records: bool = True) -> dict[str, Any]:
    records = []
    if include_records:
        records = [
            {
                "id": row.id,
                "source_sheet": row.source_sheet,
                "source_row": row.source_row,
                "source_section": row.source_section,
                "record_type": row.record_type,
                "original_raw_payload": row.original_raw_payload,
                "normalized_payload": row.normalized_payload,
                "issues": row.issues or [],
                "classification": row.classification,
                "reconciliation_status": row.reconciliation_status,
                "created_asset_id": row.created_asset_id,
            }
            for row in batch.rows
        ]
    return {
        "batch_id": batch.id,
        "batch_code": batch.batch_code,
        "status": batch.status,
        "source_workbook": batch.source_workbook,
        "reporting_month": batch.reporting_month,
        "summary": batch.summary or {},
        "records": records,
        "exceptions": [
            {
                "id": exc.id,
                "row_id": exc.row_id,
                "severity": exc.severity,
                "exception_type": exc.exception_type,
                "message": exc.message,
                "resolved": exc.resolved,
                "resolution": exc.resolution,
            }
            for exc in batch.exceptions
        ],
        "created_by": batch.created_by,
        "approved_by": batch.approved_by,
        "created_at": batch.created_at.isoformat(),
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
    }


def _date_value(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _get_or_create_project(db: Session, name: str | None) -> DroneProject | None:
    if not name:
        return None
    project = db.scalar(select(DroneProject).where(func.lower(DroneProject.project_name) == name.lower()))
    if project:
        return project
    project = DroneProject(
        project_code=next_code(db, DroneProject, DroneProject.project_code, "DRN-PRJ"),
        project_name=name,
        status="active",
        description="Created from approved Drone workbook import",
    )
    db.add(project)
    db.flush()
    return project


def _create_asset_from_row(db: Session, batch: DroneImportBatch, row: DroneImportRow, kit: DroneAssetKit | None = None) -> DroneSurveyAsset:
    data = dict(row.normalized_payload)
    category = data.get("category") or "Other"
    asset_name = data.get("asset_name") or "Imported Equipment"
    prefix = _prefix(category, asset_name)
    project = _get_or_create_project(db, data.get("kit_project"))
    status = data.get("current_status") or "available"
    if status not in ASSET_STATUSES:
        status = "available"
    asset = DroneSurveyAsset(
        asset_tag=next_code(db, DroneSurveyAsset, DroneSurveyAsset.asset_tag, prefix),
        imported_equipment_id=data.get("imported_equipment_id"),
        asset_name=asset_name,
        category=category,
        subcategory=data.get("subcategory"),
        manufacturer=data.get("manufacturer"),
        model_number=data.get("model_number"),
        serial_number=data.get("serial_number"),
        raw_serial_number=data.get("raw_serial_number"),
        quantity=float(data.get("quantity") or 0),
        raw_quantity=data.get("raw_quantity"),
        unit_of_measure=data.get("unit_of_measure"),
        tracking_type=data.get("tracking_type") or "serialized_asset",
        date_of_initial_verification=_date_value(data.get("date_of_initial_verification")),
        calibration_required=data.get("calibration_required"),
        maintenance_required=data.get("maintenance_required"),
        technical_frequency=data.get("technical_frequency"),
        responsible_function=data.get("responsible_function"),
        calibrated_by=data.get("calibrated_by"),
        last_calibration_date=_date_value(data.get("last_calibration_date")),
        next_calibration_date=_date_value(data.get("next_calibration_date")),
        location_of_location=data.get("location_of_location"),
        location_of_equipment=data.get("location_of_equipment"),
        equipment_tolerance=data.get("equipment_tolerance"),
        remarks=data.get("remarks"),
        current_status=status,
        working_condition=data.get("working_condition"),
        current_custodian=data.get("current_custodian"),
        associated_people=data.get("associated_people") or [],
        current_project_id=project.id if project else None,
        current_location=data.get("current_location"),
        parent_kit_id=kit.id if kit else None,
        is_serialized=bool(data.get("is_serialized")),
        is_telemetry_capable=bool(data.get("is_telemetry_capable")),
        source_workbook=batch.source_workbook,
        source_sheet=row.source_sheet,
        source_row=row.source_row,
        source_section=row.source_section,
        import_batch_id=batch.id,
        original_raw_payload=row.original_raw_payload,
        original_header_map=row.original_header_map,
        reconciliation_status="approved_with_warning" if row.issues else "approved",
    )
    db.add(asset)
    db.flush()
    row.created_asset_id = asset.id
    row.reconciliation_status = "committed"
    if asset.is_telemetry_capable:
        existing_profile = None
        if asset.serial_number:
            existing_profile = db.scalar(select(Drone).where(func.lower(Drone.serial_number) == asset.serial_number.lower()))
        if not existing_profile:
            db.add(Drone(
                asset_code=asset.asset_tag,
                name=asset.asset_name,
                model=asset.model_number or asset.asset_name,
                serial_number=asset.serial_number,
                pilot=asset.current_custodian,
                project=project.project_name if project else None,
                status="deployed" if asset.current_status == "deployed_to_project" else "available",
                survey_asset_id=asset.id,
            ))
    return asset


def commit_import_batch(db: Session, batch: DroneImportBatch, user: User, allow_warnings: bool, selected_row_ids: list[int] | None) -> dict[str, Any]:
    if batch.status == "committed":
        raise HTTPException(status_code=409, detail="This import batch has already been committed")
    selected = set(selected_row_ids or [])
    rows = [row for row in batch.rows if not selected or row.id in selected]
    critical = [exc for exc in batch.exceptions if exc.severity == "critical" and not exc.resolved and (not selected or exc.row_id in selected)]
    if critical:
        raise HTTPException(status_code=409, detail="Resolve critical duplicate matches before committing this import")
    warning_rows = [row for row in rows if row.issues]
    if warning_rows and not allow_warnings:
        raise HTTPException(status_code=409, detail="This import contains warnings. Review them or allow warning records")

    created_assets = 0
    created_kits = 0
    created_projects_before = db.scalar(select(func.count(DroneProject.id))) or 0
    kit_cache: dict[str, DroneAssetKit] = {}

    try:
        for row in rows:
            data = row.normalized_payload
            if row.record_type in {"asset", "amrut_asset"}:
                _create_asset_from_row(db, batch, row)
                created_assets += 1
            elif row.record_type == "trinity_component":
                unit = str(data.get("unit_number") or "UNKNOWN")
                kit = kit_cache.get(unit)
                if not kit:
                    kit = db.scalar(select(DroneAssetKit).where(DroneAssetKit.unit_number == unit))
                if not kit:
                    project = _get_or_create_project(db, data.get("kit_project"))
                    kit = DroneAssetKit(
                        kit_tag=next_code(db, DroneAssetKit, DroneAssetKit.kit_tag, "NT-KIT"),
                        kit_name=data.get("kit_name") or f"Trinity Unit {unit}",
                        model=data.get("model_number"),
                        unit_number=unit,
                        uin=data.get("uin"),
                        current_status=data.get("kit_status") or "available",
                        current_project_id=project.id if project else None,
                        current_location=data.get("current_location"),
                        remarks=data.get("remarks"),
                        source_sheet=row.source_sheet,
                        source_row=row.source_row,
                        original_raw_payload=row.original_raw_payload,
                    )
                    db.add(kit)
                    db.flush()
                    created_kits += 1
                kit_cache[unit] = kit
                asset = _create_asset_from_row(db, batch, row, kit=kit)
                created_assets += 1
                db.add(DroneKitComponent(
                    kit_id=kit.id,
                    asset_id=asset.id,
                    component_name=asset.asset_name,
                    required_quantity=max(asset.quantity, 1),
                    is_essential=asset.asset_name.lower() not in {"transport box", "anemometer"},
                ))
            elif row.record_type == "telecom":
                number = data.get("connection_number")
                if number and not db.scalar(select(DroneTelecomConnection).where(DroneTelecomConnection.connection_number == number)):
                    db.add(DroneTelecomConnection(
                        connection_number=number,
                        device_type=data.get("device_type") or "Airtel Modem",
                        provider=data.get("provider") or "Airtel",
                        current_status=data.get("current_status") or "available",
                        remarks=data.get("remarks"),
                        source_sheet=row.source_sheet,
                        source_row=row.source_row,
                        original_raw_payload=row.original_raw_payload,
                        import_batch_id=batch.id,
                    ))
                row.reconciliation_status = "committed"
            elif row.record_type == "uin":
                registration = DroneUINRegistration(
                    application_number=data.get("application_number"),
                    serial_number=data.get("serial_number"),
                    category=data.get("category"),
                    uin_status=data.get("uin_status"),
                    uin=data.get("uin"),
                    uav=data.get("uav"),
                    issue_date=_date_value(data.get("issue_date")),
                    uav_class=data.get("uav_class"),
                    source_sheet=row.source_sheet,
                    source_row=row.source_row,
                    original_raw_payload=row.original_raw_payload,
                    import_batch_id=batch.id,
                )
                if registration.serial_number:
                    linked = db.scalar(select(DroneSurveyAsset).where(func.lower(DroneSurveyAsset.serial_number) == registration.serial_number.lower()))
                    registration.linked_asset_id = linked.id if linked else None
                db.add(registration)
                row.reconciliation_status = "committed"
            elif row.record_type == "hdd_delivery":
                delivery = DroneHDDDelivery(
                    delivery_code=next_code(db, DroneHDDDelivery, DroneHDDDelivery.delivery_code, "DRN-DEL"),
                    delivery_date=_date_value(data.get("delivery_date")),
                    ulbs=data.get("ulbs"),
                    square_km=data.get("square_km"),
                    hdd_serial_number=data.get("hdd_serial_number"),
                    storage=data.get("storage"),
                    courier_name=data.get("courier_name"),
                    courier_details=data.get("courier_details"),
                    remarks=data.get("remarks"),
                    delivery_status=data.get("delivery_status") or "delivered",
                    source_sheet=row.source_sheet,
                    source_row=row.source_row,
                    original_raw_payload=row.original_raw_payload,
                    import_batch_id=batch.id,
                )
                if delivery.hdd_serial_number:
                    linked = db.scalar(select(DroneSurveyAsset).where(func.lower(DroneSurveyAsset.serial_number) == delivery.hdd_serial_number.lower()))
                    delivery.linked_asset_id = linked.id if linked else None
                db.add(delivery)
                db.flush()
                row.reconciliation_status = "committed"
        batch.status = "committed"
        batch.approved_by = user.email
        batch.committed_at = utc_now()
        db.add(DroneAuditLog(
            action="import_batch_committed",
            entity_type="import_batch",
            entity_id=batch.id,
            details={"assets": created_assets, "kits": created_kits, "selected_rows": len(rows)},
            performed_by=user.email,
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise

    projects_after = db.scalar(select(func.count(DroneProject.id))) or 0
    return {
        "batch_id": batch.id,
        "batch_code": batch.batch_code,
        "status": batch.status,
        "created_assets": created_assets,
        "created_kits": created_kits,
        "created_projects": int(projects_after - created_projects_before),
        "telecom_connections": sum(row.record_type == "telecom" for row in rows),
        "uin_registrations": sum(row.record_type == "uin" for row in rows),
        "hdd_deliveries": sum(row.record_type == "hdd_delivery" for row in rows),
    }


def dashboard_data(db: Session) -> dict[str, Any]:
    assets = list(db.scalars(select(DroneSurveyAsset).where(DroneSurveyAsset.archived_at.is_(None))).all())
    projects = list(db.scalars(select(DroneProject).where(DroneProject.archived_at.is_(None))).all())
    kits = list(db.scalars(select(DroneAssetKit).where(DroneAssetKit.archived_at.is_(None))).all())
    status_counts = Counter(asset.current_status for asset in assets)
    category_counts = Counter(asset.category for asset in assets)
    project_counts = Counter(asset.project.project_name if asset.project else "Unassigned" for asset in assets)
    missing_serials = sum(not asset.serial_number for asset in assets if asset.is_serialized)
    duplicate_ids = db.execute(
        select(DroneSurveyAsset.imported_equipment_id, func.count(DroneSurveyAsset.id))
        .where(DroneSurveyAsset.imported_equipment_id.is_not(None))
        .group_by(DroneSurveyAsset.imported_equipment_id)
        .having(func.count(DroneSurveyAsset.id) > 1)
    ).all()
    unresolved = db.scalar(select(func.count(DroneImportException.id)).where(DroneImportException.resolved.is_(False))) or 0
    calibration_overdue = sum(bool(asset.next_calibration_date and asset.next_calibration_date < date.today()) for asset in assets)
    flight_ready = sum(kit_dict(kit)["readiness_percentage"] == 100 for kit in kits)
    active_operations = list(db.scalars(select(DroneOperation).where(
        DroneOperation.operation_type.in_(("dispatch", "assignment")),
        DroneOperation.status.in_(("active", "partial")),
    )).all())
    recent_movements = list(db.scalars(
        select(DroneAssetMovement).order_by(DroneAssetMovement.occurred_at.desc()).limit(8)
    ).all())
    telemetry = []
    for profile in db.scalars(select(Drone)).all():
        latest = db.scalar(select(DroneLocation).where(DroneLocation.drone_id == profile.id).order_by(DroneLocation.recorded_at.desc()).limit(1))
        freshness = "No Data"
        if latest:
            age = utc_now() - latest.recorded_at
            freshness = "Live" if age.total_seconds() <= 300 else "Recent" if age.total_seconds() <= 3600 else "Stale"
        telemetry.append({
            "id": profile.id,
            "asset_code": profile.asset_code,
            "name": profile.name,
            "status": profile.status,
            "freshness": freshness,
            "latest_location": {
                "latitude": latest.latitude,
                "longitude": latest.longitude,
                "recorded_at": latest.recorded_at.isoformat(),
                "source": latest.source,
            } if latest else None,
        })
    return {
        "kpis": {
            "total_assets": len(assets),
            "total_quantity": sum(asset.quantity for asset in assets),
            "flight_capable_drones": sum(bool(asset.is_telemetry_capable) for asset in assets),
            "available_assets": status_counts["available"],
            "assets_with_employees": sum(bool(asset.current_custodian) for asset in assets),
            "assets_at_projects": sum(bool(asset.current_project_id) for asset in assets),
            "under_maintenance": status_counts["under_maintenance"] + status_counts["sent_for_service"],
            "calibration_overdue": calibration_overdue,
            "flight_ready_kits": flight_ready,
            "incomplete_kits": len(kits) - flight_ready,
            "missing_assets": status_counts["missing"],
            "pending_verification": status_counts["pending_verification"] + status_counts["not_verified"],
            "active_projects": sum(project.status == "active" for project in projects),
            "completed_projects": sum(project.status == "completed" for project in projects),
            "hdd_deliveries": db.scalar(select(func.count(DroneHDDDelivery.id))) or 0,
            "in_transit": status_counts["in_transit"],
            "active_operations": len(active_operations),
            "overdue_returns": sum(bool(operation.expected_return_date and operation.expected_return_date < date.today()) for operation in active_operations),
        },
        "category_distribution": [{"name": name, "value": value} for name, value in category_counts.most_common()],
        "status_distribution": [{"name": name.replace("_", " ").title(), "value": value} for name, value in status_counts.most_common()],
        "project_distribution": [{"name": name, "value": value} for name, value in project_counts.most_common()],
        "recent_assets": [asset_dict(asset, db) for asset in sorted(assets, key=lambda item: item.created_at, reverse=True)[:8]],
        "import_quality": {
            "missing_serial_numbers": missing_serials,
            "duplicate_imported_ids": len(duplicate_ids),
            "unresolved_import_exceptions": unresolved,
        },
        "telemetry": telemetry,
        "recent_movements": [movement_dict(record) for record in recent_movements],
        "active_operations": [operation_dict(operation, include_items=False) for operation in sorted(active_operations, key=lambda item: item.created_at, reverse=True)[:8]],
    }


def search_entities(db: Session, query: str, limit: int) -> list[dict[str, Any]]:
    term = f"%{query.strip().lower()}%"
    results = []
    assets = db.scalars(
        select(DroneSurveyAsset)
        .where(
            DroneSurveyAsset.archived_at.is_(None),
            or_(
                func.lower(DroneSurveyAsset.asset_tag).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.imported_equipment_id, "")).like(term),
                func.lower(DroneSurveyAsset.asset_name).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.serial_number, "")).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.model_number, "")).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.manufacturer, "")).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.current_custodian, "")).like(term),
                func.lower(func.coalesce(DroneSurveyAsset.current_location, "")).like(term),
            ),
        )
        .limit(limit)
    ).all()
    for asset in assets:
        results.append({
            "entity_type": "asset",
            "id": asset.id,
            "primary": f"{asset.asset_tag} · {asset.asset_name}",
            "secondary": " · ".join(filter(None, [asset.model_number, asset.serial_number, asset.current_project_id and asset.project.project_name])),
            "status": asset.current_status,
            "context": {"category": asset.category, "custodian": asset.current_custodian, "location": asset.current_location},
        })
    if len(results) < limit:
        remaining = limit - len(results)
        projects = db.scalars(
            select(DroneProject).where(or_(func.lower(DroneProject.project_code).like(term), func.lower(DroneProject.project_name).like(term))).limit(remaining)
        ).all()
        results.extend({
            "entity_type": "project", "id": project.id,
            "primary": f"{project.project_code} · {project.project_name}",
            "secondary": " · ".join(filter(None, [project.client, project.location])),
            "status": project.status, "context": {},
        } for project in projects)
    return results[:limit]


ACTIVE_ITEM_STATUSES = {"active", "partial"}
WORK_STATUSES = {"open", "in_progress", "completed", "closed", "cancelled"}
WORK_PRIORITIES = {"low", "medium", "high", "critical"}


def _open_quantity(item: DroneOperationItem) -> float:
    return max(float(item.quantity or 0) - float(item.returned_quantity or 0), 0.0)


def active_asset_quantity(db: Session, asset_id: int, exclude_item_id: int | None = None) -> float:
    filters = [
        DroneOperationItem.asset_id == asset_id,
        DroneOperationItem.item_status.in_(ACTIVE_ITEM_STATUSES),
    ]
    if exclude_item_id is not None:
        filters.append(DroneOperationItem.id != exclude_item_id)
    items = db.scalars(select(DroneOperationItem).where(*filters)).all()
    return sum(_open_quantity(item) for item in items)


def sync_quantity_asset_state(db: Session, asset: DroneSurveyAsset) -> None:
    if asset.is_serialized:
        return
    items = db.scalars(select(DroneOperationItem).where(
        DroneOperationItem.asset_id == asset.id,
        DroneOperationItem.item_status.in_(ACTIVE_ITEM_STATUSES),
    )).all()
    items = [item for item in items if _open_quantity(item) > 1e-9]
    if not items:
        return
    project_ids = {item.operation.to_project_id or item.operation.project_id for item in items if (item.operation.to_project_id or item.operation.project_id)}
    custodians = {item.operation.to_custodian for item in items if item.operation.to_custodian}
    locations = {item.operation.destination for item in items if item.operation.destination}
    asset.current_status = "deployed_to_project" if project_ids else "assigned_to_employee"
    asset.current_project_id = next(iter(project_ids)) if len(project_ids) == 1 else None
    asset.current_custodian = next(iter(custodians)) if len(custodians) == 1 else "Multiple custodians"
    asset.current_location = next(iter(locations)) if len(locations) == 1 else "Multiple locations"


def movement_dict(record: DroneAssetMovement) -> dict[str, Any]:
    return {
        "id": record.id,
        "movement_code": record.movement_code,
        "operation_id": record.operation_id,
        "asset_id": record.asset_id,
        "asset_tag": record.asset.asset_tag if record.asset else None,
        "asset_name": record.asset.asset_name if record.asset else None,
        "kit_id": record.kit_id,
        "kit_tag": record.kit.kit_tag if record.kit else None,
        "kit_name": record.kit.kit_name if record.kit else None,
        "movement_type": record.movement_type,
        "quantity": record.quantity,
        "old_status": record.old_status,
        "new_status": record.new_status,
        "old_project_id": record.old_project_id,
        "old_project": record.old_project.project_name if record.old_project else None,
        "new_project_id": record.new_project_id,
        "new_project": record.new_project.project_name if record.new_project else None,
        "old_custodian": record.old_custodian,
        "new_custodian": record.new_custodian,
        "old_location": record.old_location,
        "new_location": record.new_location,
        "condition": record.condition,
        "remarks": record.remarks,
        "performed_by": record.performed_by,
        "occurred_at": record.occurred_at.isoformat(),
    }


def operation_item_dict(item: DroneOperationItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "parent_item_id": item.parent_item_id,
        "source_operation_item_id": item.source_operation_item_id,
        "asset_id": item.asset_id,
        "asset_tag": item.asset.asset_tag if item.asset else None,
        "asset_name": item.asset.asset_name if item.asset else None,
        "asset_category": item.asset.category if item.asset else None,
        "serial_number": item.asset.serial_number if item.asset else None,
        "kit_id": item.kit_id,
        "kit_tag": item.kit.kit_tag if item.kit else None,
        "kit_name": item.kit.kit_name if item.kit else None,
        "quantity": item.quantity,
        "returned_quantity": item.returned_quantity,
        "open_quantity": _open_quantity(item),
        "item_status": item.item_status,
        "condition": item.condition,
        "next_status": item.next_status,
        "remarks": item.remarks,
        "is_kit_component": bool(item.parent_item_id and item.asset_id),
    }


def operation_dict(operation: DroneOperation, include_items: bool = True) -> dict[str, Any]:
    payload = {
        "id": operation.id,
        "operation_code": operation.operation_code,
        "operation_type": operation.operation_type,
        "status": operation.status,
        "project_id": operation.project_id,
        "project": operation.project.project_name if operation.project else None,
        "from_project_id": operation.from_project_id,
        "from_project": operation.from_project.project_name if operation.from_project else None,
        "to_project_id": operation.to_project_id,
        "to_project": operation.to_project.project_name if operation.to_project else None,
        "parent_operation_id": operation.parent_operation_id,
        "from_custodian": operation.from_custodian,
        "to_custodian": operation.to_custodian,
        "source_location": operation.source_location,
        "destination": operation.destination,
        "operation_date": operation.operation_date.isoformat(),
        "expected_return_date": operation.expected_return_date.isoformat() if operation.expected_return_date else None,
        "purpose": operation.purpose,
        "condition": operation.condition,
        "approved_by": operation.approved_by,
        "override_reason": operation.override_reason,
        "remarks": operation.remarks,
        "performed_by": operation.performed_by,
        "created_at": operation.created_at.isoformat(),
        "completed_at": operation.completed_at.isoformat() if operation.completed_at else None,
    }
    payload["items"] = [operation_item_dict(item) for item in operation.items] if include_items else []
    payload["open_item_count"] = sum(_open_quantity(item) > 0 for item in operation.items)
    payload["overdue"] = bool(
        operation.expected_return_date
        and operation.expected_return_date < date.today()
        and operation.status in {"active", "partial"}
    )
    return payload


def work_record_dict(record: DroneWorkRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "work_code": record.work_code,
        "title": record.title,
        "work_type": record.work_type,
        "project_id": record.project_id,
        "project": record.project.project_name if record.project else None,
        "asset_id": record.asset_id,
        "asset_tag": record.asset.asset_tag if record.asset else None,
        "asset_name": record.asset.asset_name if record.asset else None,
        "kit_id": record.kit_id,
        "kit_tag": record.kit.kit_tag if record.kit else None,
        "kit_name": record.kit.kit_name if record.kit else None,
        "operation_id": record.operation_id,
        "assigned_to": record.assigned_to,
        "technician": record.technician,
        "priority": record.priority,
        "status": record.status,
        "approval_status": record.approval_status,
        "description": record.description,
        "initial_condition": record.initial_condition,
        "resolution": record.resolution,
        "start_date": record.start_date.isoformat() if record.start_date else None,
        "expected_completion_date": record.expected_completion_date.isoformat() if record.expected_completion_date else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "performed_by": record.performed_by,
        "approved_by": record.approved_by,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _add_movement(
    db: Session,
    *,
    operation: DroneOperation,
    movement_type: str,
    user: User,
    asset: DroneSurveyAsset | None = None,
    kit: DroneAssetKit | None = None,
    quantity: float = 1,
    old_status: str | None = None,
    new_status: str | None = None,
    old_project_id: int | None = None,
    new_project_id: int | None = None,
    old_custodian: str | None = None,
    new_custodian: str | None = None,
    old_location: str | None = None,
    new_location: str | None = None,
    condition: str | None = None,
    remarks: str | None = None,
) -> DroneAssetMovement:
    movement = DroneAssetMovement(
        movement_code=next_code(db, DroneAssetMovement, DroneAssetMovement.movement_code, "DRN-MOV"),
        operation_id=operation.id,
        asset_id=asset.id if asset else None,
        kit_id=kit.id if kit else None,
        movement_type=movement_type,
        quantity=quantity,
        old_status=old_status,
        new_status=new_status,
        old_project_id=old_project_id,
        new_project_id=new_project_id,
        old_custodian=old_custodian,
        new_custodian=new_custodian,
        old_location=old_location,
        new_location=new_location,
        condition=condition,
        remarks=remarks,
        performed_by=user.email,
    )
    db.add(movement)
    db.flush()
    return movement


def _create_operation_work_record(
    db: Session,
    operation: DroneOperation,
    user: User,
    title: str,
    work_type: str,
    description: str | None = None,
) -> DroneWorkRecord:
    record = DroneWorkRecord(
        work_code=next_code(db, DroneWorkRecord, DroneWorkRecord.work_code, "DRW"),
        title=title,
        work_type=work_type,
        project_id=operation.project_id or operation.to_project_id,
        operation_id=operation.id,
        assigned_to=operation.to_custodian,
        technician="Drone Department",
        priority="medium",
        status="completed",
        approval_status="approved" if operation.approved_by else "recorded",
        description=description or operation.purpose,
        initial_condition=operation.condition,
        resolution=f"{work_type.replace('_', ' ').title()} recorded through {operation.operation_code}",
        start_date=operation.operation_date,
        expected_completion_date=operation.operation_date,
        completed_at=utc_now(),
        performed_by=user.email,
        approved_by=operation.approved_by,
    )
    db.add(record)
    db.flush()
    return record


def _ensure_project(db: Session, project_id: int | None) -> DroneProject | None:
    if project_id is None:
        return None
    project = db.get(DroneProject, project_id)
    if not project or project.archived_at:
        raise HTTPException(status_code=404, detail="Drone project not found")
    if project.status in {"closed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Assets cannot be assigned to a closed or cancelled project")
    return project


def _validate_selection(selection: Any) -> tuple[int | None, int | None, float]:
    asset_id = getattr(selection, "asset_id", None)
    kit_id = getattr(selection, "kit_id", None)
    quantity = float(getattr(selection, "quantity", 1) or 0)
    if bool(asset_id) == bool(kit_id):
        raise HTTPException(status_code=400, detail="Select exactly one asset or one kit per item")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Selected quantity must be greater than zero")
    return asset_id, kit_id, quantity


def _dispatch_asset(
    db: Session,
    operation: DroneOperation,
    asset: DroneSurveyAsset,
    quantity: float,
    project: DroneProject | None,
    custodian: str,
    destination: str,
    condition: str | None,
    user: User,
    parent_item_id: int | None = None,
) -> DroneOperationItem:
    if asset.archived_at:
        raise HTTPException(status_code=400, detail=f"{asset.asset_tag} is archived")
    if asset.is_serialized and asset.current_status not in {"available", "reserved"}:
        raise HTTPException(status_code=409, detail=f"{asset.asset_tag} is {asset.current_status.replace('_', ' ')} and is not available")
    if not asset.is_serialized and asset.current_status in {"retired", "disposed", "missing", "damaged", "under_maintenance", "sent_for_service", "under_calibration"}:
        raise HTTPException(status_code=409, detail=f"{asset.asset_tag} is {asset.current_status.replace('_', ' ')} and cannot be allocated")
    already_allocated = active_asset_quantity(db, asset.id)
    available = max(float(asset.quantity) - already_allocated, 0.0)
    if asset.is_serialized and already_allocated > 0:
        raise HTTPException(status_code=409, detail=f"{asset.asset_tag} already has an active assignment")
    if quantity > available + 1e-9:
        raise HTTPException(status_code=409, detail=f"Only {available:g} of {asset.asset_tag} is available")
    old_status = asset.current_status
    old_project_id = asset.current_project_id
    old_custodian = asset.current_custodian
    old_location = asset.current_location
    new_status = "deployed_to_project" if project else "assigned_to_employee"
    asset.current_status = new_status
    asset.current_project_id = project.id if project else None
    asset.current_custodian = custodian
    asset.current_location = destination
    item = DroneOperationItem(
        operation_id=operation.id,
        parent_item_id=parent_item_id,
        asset_id=asset.id,
        quantity=quantity,
        item_status="active",
        condition=condition,
    )
    db.add(item)
    db.flush()
    if not asset.is_serialized:
        sync_quantity_asset_state(db, asset)
        new_status = asset.current_status
    _add_movement(
        db,
        operation=operation,
        movement_type=operation.operation_type,
        user=user,
        asset=asset,
        quantity=quantity,
        old_status=old_status,
        new_status=new_status,
        old_project_id=old_project_id,
        new_project_id=project.id if project else None,
        old_custodian=old_custodian,
        new_custodian=custodian,
        old_location=old_location,
        new_location=destination,
        condition=condition,
        remarks=operation.remarks,
    )
    return item


def create_dispatch_operation(db: Session, payload: Any, user: User) -> dict[str, Any]:
    project = _ensure_project(db, payload.project_id)
    if payload.expected_return_date and payload.expected_return_date < payload.dispatch_date:
        raise HTTPException(status_code=400, detail="Expected return date cannot be before dispatch date")
    operation = DroneOperation(
        operation_code=next_code(db, DroneOperation, DroneOperation.operation_code, "DRN-DSP"),
        operation_type="dispatch",
        status="active",
        project_id=project.id,
        to_project_id=project.id,
        to_custodian=payload.custodian,
        destination=payload.destination,
        operation_date=payload.dispatch_date,
        expected_return_date=payload.expected_return_date,
        purpose=payload.purpose,
        condition=payload.condition,
        approved_by=payload.approved_by,
        override_reason=payload.override_reason,
        remarks=payload.remarks,
        performed_by=user.email,
    )
    db.add(operation)
    db.flush()
    selected_assets: set[int] = set()
    selected_kits: set[int] = set()
    for selection in payload.items:
        asset_id, kit_id, quantity = _validate_selection(selection)
        if asset_id:
            if asset_id in selected_assets:
                raise HTTPException(status_code=400, detail="The same asset was selected more than once")
            selected_assets.add(asset_id)
            asset = db.get(DroneSurveyAsset, asset_id)
            if not asset:
                raise HTTPException(status_code=404, detail="Selected Drone asset not found")
            _dispatch_asset(db, operation, asset, quantity, project, payload.custodian, payload.destination, payload.condition, user)
        else:
            if kit_id in selected_kits:
                raise HTTPException(status_code=400, detail="The same kit was selected more than once")
            selected_kits.add(kit_id)
            kit = db.get(DroneAssetKit, kit_id)
            if not kit or kit.archived_at:
                raise HTTPException(status_code=404, detail="Selected Drone kit not found")
            if kit.current_status not in {"available", "reserved"}:
                raise HTTPException(status_code=409, detail=f"{kit.kit_tag} is not available")
            readiness = kit_dict(kit)["readiness_percentage"]
            if readiness < 100 and not payload.allow_incomplete_kit:
                raise HTTPException(status_code=409, detail=f"{kit.kit_tag} is only {readiness:g}% ready")
            if readiness < 100 and not (payload.override_reason or "").strip():
                raise HTTPException(status_code=400, detail="An override reason is required for an incomplete kit")
            old_status, old_project, old_custodian, old_location = (
                kit.current_status, kit.current_project_id, kit.current_custodian, kit.current_location
            )
            kit.current_status = "deployed_to_project"
            kit.current_project_id = project.id
            kit.current_custodian = payload.custodian
            kit.current_location = payload.destination
            parent_item = DroneOperationItem(
                operation_id=operation.id,
                kit_id=kit.id,
                quantity=1,
                item_status="active",
                condition=payload.condition,
            )
            db.add(parent_item)
            db.flush()
            _add_movement(
                db, operation=operation, movement_type="dispatch", user=user, kit=kit,
                old_status=old_status, new_status="deployed_to_project", old_project_id=old_project,
                new_project_id=project.id, old_custodian=old_custodian, new_custodian=payload.custodian,
                old_location=old_location, new_location=payload.destination, condition=payload.condition,
                remarks=payload.remarks,
            )
            for component in [c for c in kit.components if c.removed_at is None]:
                if component.asset_id in selected_assets:
                    raise HTTPException(status_code=400, detail=f"{component.asset.asset_tag} is already included through {kit.kit_tag}")
                selected_assets.add(component.asset_id)
                component_quantity = min(float(component.required_quantity or 1), float(component.asset.quantity or 0))
                if component_quantity <= 0:
                    if component.is_essential and not payload.allow_incomplete_kit:
                        raise HTTPException(status_code=409, detail=f"Essential component {component.component_name} has zero quantity")
                    continue
                _dispatch_asset(
                    db, operation, component.asset, component_quantity, project, payload.custodian,
                    payload.destination, payload.condition, user, parent_item_id=parent_item.id,
                )
    _create_operation_work_record(
        db, operation, user,
        title=f"Dispatch equipment to {project.project_name}",
        work_type="dispatch",
        description=payload.purpose,
    )
    db.add(DroneAuditLog(
        action="dispatch_created", entity_type="drone_operation", entity_id=operation.id,
        details={"operation_code": operation.operation_code, "project": project.project_name, "items": len(operation.items)},
        performed_by=user.email,
    ))
    db.commit()
    db.refresh(operation)
    return operation_dict(operation)


def create_assignment_operation(db: Session, payload: Any, user: User) -> dict[str, Any]:
    project = _ensure_project(db, payload.project_id)
    if payload.expected_return_date and payload.expected_return_date < payload.assignment_date:
        raise HTTPException(status_code=400, detail="Expected return date cannot be before assignment date")
    operation = DroneOperation(
        operation_code=next_code(db, DroneOperation, DroneOperation.operation_code, "DRN-ASG"),
        operation_type="assignment",
        status="active",
        project_id=project.id if project else None,
        to_project_id=project.id if project else None,
        to_custodian=payload.custodian,
        destination=payload.location,
        operation_date=payload.assignment_date,
        expected_return_date=payload.expected_return_date,
        purpose=payload.purpose,
        approved_by=payload.approved_by,
        remarks=payload.remarks,
        performed_by=user.email,
    )
    db.add(operation)
    db.flush()
    for selection in payload.items:
        asset_id, kit_id, quantity = _validate_selection(selection)
        if kit_id:
            kit = db.get(DroneAssetKit, kit_id)
            if not kit:
                raise HTTPException(status_code=404, detail="Selected Drone kit not found")
            if kit.current_status not in {"available", "reserved"}:
                raise HTTPException(status_code=409, detail=f"{kit.kit_tag} is not available")
            kit.current_status = "deployed_to_project" if project else "assigned_to_employee"
            kit.current_project_id = project.id if project else None
            kit.current_custodian = payload.custodian
            kit.current_location = payload.location
            parent_item = DroneOperationItem(operation_id=operation.id, kit_id=kit.id, quantity=1, item_status="active")
            db.add(parent_item); db.flush()
            for component in [c for c in kit.components if c.removed_at is None and c.asset.quantity > 0]:
                _dispatch_asset(db, operation, component.asset, min(component.required_quantity, component.asset.quantity), project, payload.custodian, payload.location, None, user, parent_item.id)
        else:
            asset = db.get(DroneSurveyAsset, asset_id)
            if not asset:
                raise HTTPException(status_code=404, detail="Selected Drone asset not found")
            _dispatch_asset(db, operation, asset, quantity, project, payload.custodian, payload.location, None, user)
    _create_operation_work_record(db, operation, user, f"Assign equipment to {payload.custodian}", "assignment", payload.purpose)
    db.add(DroneAuditLog(action="assignment_created", entity_type="drone_operation", entity_id=operation.id, details={"operation_code": operation.operation_code}, performed_by=user.email))
    db.commit(); db.refresh(operation)
    return operation_dict(operation)


def create_return_operation(db: Session, payload: Any, user: User) -> dict[str, Any]:
    source = db.get(DroneOperation, payload.dispatch_operation_id)
    if not source or source.operation_type not in {"dispatch", "assignment"}:
        raise HTTPException(status_code=404, detail="Active dispatch or assignment not found")
    if source.status not in {"active", "partial"}:
        raise HTTPException(status_code=409, detail="This operation has already been fully returned or closed")
    operation = DroneOperation(
        operation_code=next_code(db, DroneOperation, DroneOperation.operation_code, "DRN-RTN"),
        operation_type="return",
        status="completed",
        project_id=source.project_id,
        from_project_id=source.to_project_id or source.project_id,
        parent_operation_id=source.id,
        from_custodian=source.to_custodian,
        to_custodian=payload.receiver,
        source_location=source.destination,
        destination=payload.return_location,
        operation_date=payload.return_date,
        purpose=f"Return against {source.operation_code}",
        remarks=payload.remarks,
        performed_by=user.email,
        completed_at=utc_now(),
    )
    db.add(operation); db.flush()
    requested = {item.operation_item_id: item for item in payload.items}
    source_items = {item.id: item for item in source.items}
    expanded: dict[int, Any] = dict(requested)
    for item_id, request in list(requested.items()):
        source_item = source_items.get(item_id)
        if not source_item:
            raise HTTPException(status_code=404, detail=f"Dispatch item {item_id} was not found")
        if source_item.kit_id:
            for child in source_item.child_items:
                if _open_quantity(child) > 0 and child.id not in expanded:
                    clone = type("ReturnRequest", (), {
                        "operation_item_id": child.id,
                        "quantity": _open_quantity(child),
                        "condition": request.condition,
                        "next_status": request.next_status,
                        "remarks": request.remarks,
                    })()
                    expanded[child.id] = clone
    processed_assets: set[int] = set()
    for item_id, request in expanded.items():
        source_item = source_items.get(item_id)
        if not source_item:
            raise HTTPException(status_code=404, detail=f"Dispatch item {item_id} was not found")
        open_qty = _open_quantity(source_item)
        quantity = float(request.quantity)
        if quantity > open_qty + 1e-9:
            raise HTTPException(status_code=409, detail=f"Only {open_qty:g} is still open for this item")
        if request.next_status not in ASSET_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid next asset status")
        source_item.returned_quantity = float(source_item.returned_quantity or 0) + quantity
        source_item.item_status = "returned" if _open_quantity(source_item) <= 1e-9 else "partial"
        return_item = DroneOperationItem(
            operation_id=operation.id,
            source_operation_item_id=source_item.id,
            asset_id=source_item.asset_id,
            kit_id=source_item.kit_id,
            quantity=quantity,
            returned_quantity=quantity,
            item_status="returned",
            condition=request.condition,
            next_status=request.next_status,
            remarks=request.remarks,
        )
        db.add(return_item); db.flush()
        if source_item.asset and source_item.asset_id not in processed_assets:
            asset = source_item.asset
            processed_assets.add(asset.id)
            old_status, old_project, old_custodian, old_location = asset.current_status, asset.current_project_id, asset.current_custodian, asset.current_location
            remaining = active_asset_quantity(db, asset.id, exclude_item_id=source_item.id) + _open_quantity(source_item)
            if remaining <= 1e-9:
                asset.current_status = request.next_status
                if request.next_status in {"available", "under_maintenance", "sent_for_service", "under_calibration", "missing", "damaged", "retired", "disposed"}:
                    asset.current_project_id = None
                    asset.current_custodian = None
                asset.current_location = payload.return_location
            elif not asset.is_serialized:
                sync_quantity_asset_state(db, asset)
            _add_movement(
                db, operation=operation, movement_type="return", user=user, asset=asset, quantity=quantity,
                old_status=old_status, new_status=asset.current_status, old_project_id=old_project,
                new_project_id=asset.current_project_id, old_custodian=old_custodian,
                new_custodian=asset.current_custodian, old_location=old_location,
                new_location=asset.current_location, condition=request.condition,
                remarks=request.remarks or payload.remarks,
            )
    for source_item in source.items:
        if source_item.kit and _open_quantity(source_item) <= 1e-9:
            kit = source_item.kit
            children_open = sum(_open_quantity(child) for child in source_item.child_items)
            if children_open <= 1e-9:
                old_status, old_project, old_custodian, old_location = kit.current_status, kit.current_project_id, kit.current_custodian, kit.current_location
                parent_request = requested.get(source_item.id)
                next_status = parent_request.next_status if parent_request else "available"
                kit.current_status = next_status
                kit.current_project_id = None
                kit.current_custodian = None
                kit.current_location = payload.return_location
                _add_movement(
                    db, operation=operation, movement_type="return", user=user, kit=kit,
                    old_status=old_status, new_status=kit.current_status, old_project_id=old_project,
                    new_project_id=None, old_custodian=old_custodian, new_custodian=None,
                    old_location=old_location, new_location=payload.return_location,
                    remarks=payload.remarks,
                )
    remaining_items = sum(_open_quantity(item) for item in source.items)
    source.status = "completed" if remaining_items <= 1e-9 else "partial"
    source.completed_at = utc_now() if source.status == "completed" else None
    _create_operation_work_record(db, operation, user, f"Return equipment from {source.project.project_name if source.project else source.to_custodian or source.operation_code}", "return", payload.remarks)
    db.add(DroneAuditLog(action="return_created", entity_type="drone_operation", entity_id=operation.id, details={"operation_code": operation.operation_code, "source_operation": source.operation_code}, performed_by=user.email))
    db.commit(); db.refresh(operation)
    return {"return_operation": operation_dict(operation), "source_operation": operation_dict(source)}


def create_transfer_operation(db: Session, payload: Any, user: User) -> dict[str, Any]:
    target_project = _ensure_project(db, payload.to_project_id)
    if not target_project and not (payload.to_custodian or "").strip():
        raise HTTPException(status_code=400, detail="A destination project or custodian is required")
    operation = DroneOperation(
        operation_code=next_code(db, DroneOperation, DroneOperation.operation_code, "DRN-TRF"),
        operation_type="transfer",
        status="completed",
        to_project_id=target_project.id if target_project else None,
        to_custodian=payload.to_custodian,
        destination=payload.destination,
        operation_date=payload.transfer_date,
        purpose=payload.reason,
        approved_by=payload.approved_by,
        remarks=payload.remarks,
        performed_by=user.email,
        completed_at=utc_now(),
    )
    db.add(operation); db.flush()
    processed_assets: set[int] = set()
    for selection in payload.items:
        asset_id, kit_id, quantity = _validate_selection(selection)
        if asset_id:
            asset = db.get(DroneSurveyAsset, asset_id)
            if not asset or asset.archived_at:
                raise HTTPException(status_code=404, detail="Selected Drone asset not found")
            if asset.current_status in {"retired", "disposed", "missing"}:
                raise HTTPException(status_code=409, detail=f"{asset.asset_tag} cannot be transferred")
            old_status, old_project, old_custodian, old_location = asset.current_status, asset.current_project_id, asset.current_custodian, asset.current_location
            asset.current_project_id = target_project.id if target_project else None
            asset.current_custodian = payload.to_custodian
            asset.current_location = payload.destination
            asset.current_status = "deployed_to_project" if target_project else "assigned_to_employee"
            db.add(DroneOperationItem(operation_id=operation.id, asset_id=asset.id, quantity=quantity, item_status="transferred"))
            processed_assets.add(asset.id)
            _add_movement(db, operation=operation, movement_type="transfer", user=user, asset=asset, quantity=quantity, old_status=old_status, new_status=asset.current_status, old_project_id=old_project, new_project_id=asset.current_project_id, old_custodian=old_custodian, new_custodian=asset.current_custodian, old_location=old_location, new_location=asset.current_location, remarks=payload.reason)
        else:
            kit = db.get(DroneAssetKit, kit_id)
            if not kit or kit.archived_at:
                raise HTTPException(status_code=404, detail="Selected Drone kit not found")
            old_status, old_project, old_custodian, old_location = kit.current_status, kit.current_project_id, kit.current_custodian, kit.current_location
            kit.current_project_id = target_project.id if target_project else None
            kit.current_custodian = payload.to_custodian
            kit.current_location = payload.destination
            kit.current_status = "deployed_to_project" if target_project else "assigned_to_employee"
            parent_item = DroneOperationItem(operation_id=operation.id, kit_id=kit.id, quantity=1, item_status="transferred")
            db.add(parent_item); db.flush()
            _add_movement(db, operation=operation, movement_type="transfer", user=user, kit=kit, old_status=old_status, new_status=kit.current_status, old_project_id=old_project, new_project_id=kit.current_project_id, old_custodian=old_custodian, new_custodian=kit.current_custodian, old_location=old_location, new_location=kit.current_location, remarks=payload.reason)
            for component in [c for c in kit.components if c.removed_at is None]:
                asset = component.asset
                if asset.id in processed_assets:
                    continue
                processed_assets.add(asset.id)
                old_status, old_project, old_custodian, old_location = asset.current_status, asset.current_project_id, asset.current_custodian, asset.current_location
                asset.current_project_id = target_project.id if target_project else None
                asset.current_custodian = payload.to_custodian
                asset.current_location = payload.destination
                asset.current_status = "deployed_to_project" if target_project else "assigned_to_employee"
                db.add(DroneOperationItem(operation_id=operation.id, parent_item_id=parent_item.id, asset_id=asset.id, quantity=min(component.required_quantity, asset.quantity), item_status="transferred"))
                _add_movement(db, operation=operation, movement_type="transfer", user=user, asset=asset, quantity=min(component.required_quantity, asset.quantity), old_status=old_status, new_status=asset.current_status, old_project_id=old_project, new_project_id=asset.current_project_id, old_custodian=old_custodian, new_custodian=asset.current_custodian, old_location=old_location, new_location=asset.current_location, remarks=payload.reason)
    _create_operation_work_record(db, operation, user, "Transfer Drone/Survey equipment", "transfer", payload.reason)
    db.add(DroneAuditLog(action="transfer_created", entity_type="drone_operation", entity_id=operation.id, details={"operation_code": operation.operation_code}, performed_by=user.email))
    db.commit(); db.refresh(operation)
    return operation_dict(operation)


def project_detail_dict(db: Session, project: DroneProject) -> dict[str, Any]:
    assets = db.scalars(select(DroneSurveyAsset).where(DroneSurveyAsset.current_project_id == project.id, DroneSurveyAsset.archived_at.is_(None)).order_by(DroneSurveyAsset.asset_tag)).all()
    kits = db.scalars(select(DroneAssetKit).where(DroneAssetKit.current_project_id == project.id, DroneAssetKit.archived_at.is_(None)).order_by(DroneAssetKit.kit_tag)).all()
    operations = db.scalars(select(DroneOperation).where(or_(DroneOperation.project_id == project.id, DroneOperation.from_project_id == project.id, DroneOperation.to_project_id == project.id)).order_by(DroneOperation.created_at.desc()).limit(100)).all()
    work_records = db.scalars(select(DroneWorkRecord).where(DroneWorkRecord.project_id == project.id).order_by(DroneWorkRecord.created_at.desc()).limit(100)).all()
    movements = db.scalars(select(DroneAssetMovement).where(or_(DroneAssetMovement.old_project_id == project.id, DroneAssetMovement.new_project_id == project.id)).order_by(DroneAssetMovement.occurred_at.desc()).limit(200)).all()
    open_operations = [operation for operation in operations if operation.operation_type in {"dispatch", "assignment"} and operation.status in {"active", "partial"}]
    payload = project_dict(project)
    payload.update({
        "assets": [asset_dict(asset, db) for asset in assets],
        "kits": [kit_dict(kit) for kit in kits],
        "operations": [operation_dict(operation) for operation in operations],
        "work_records": [work_record_dict(record) for record in work_records],
        "movements": [movement_dict(record) for record in movements],
        "summary": {
            "asset_count": len(assets),
            "kit_count": len(kits),
            "open_operations": len(open_operations),
            "overdue_returns": sum(bool(operation.expected_return_date and operation.expected_return_date < date.today()) for operation in open_operations),
            "missing_or_damaged": sum(asset.current_status in {"missing", "damaged"} for asset in assets),
            "work_records": len(work_records),
        },
    })
    return payload
