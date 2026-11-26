from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User, utc_now
from app.modules.finance.service import all_projects, employee_project_payload
from app.modules.employee_portal.service import record_audit
from app.modules.notifications.service import create_global_notification
from app.modules.travel_km.emailing import send_submission_email
from app.modules.travel_km.attachments import (
    TravelPhotoStorageError, TravelPhotoValidationError, delete_travel_photo, preview_data_url,
    store_travel_photo, stream_travel_photo, validate_travel_photo,
)
from app.modules.travel_km.models import TravelKmAttachment, TravelKmClaim, TravelKmEvent, TravelKmTrackPoint
from app.modules.travel_km.reporting import EXCEL_MIME, build_travel_km_workbook
from app.modules.travel_km.schemas import (
    TravelKmClaimCreateRequest,
    TravelKmDecisionRequest,
    TravelKmEmailRoutingRequest,
    TravelKmEndRequest,
    TravelKmFinanceDecisionRequest,
    TravelKmPaymentRequest,
    TravelKmProjectGeofenceRequest,
    TravelKmReviseRequest,
    TravelKmTrackPointRequest,
)
from app.modules.travel_km.verification import (
    project_geofence_payload,
    set_project_geofence,
    verification_payload,
)
from app.modules.travel_km.service import (
    ADMIN_ROLE, EMPLOYEE_ROLE, FINANCE_ROLE, HR_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE,
    add_event, admin_decision, claim_payload, create_claim, dashboard_payload, finance_decision, finance_payment,
    finish_journey, get_visible_claim, haversine_km, hr_decision, list_visible_claims, recalculate_claim, revise_claim, set_email_routing, submit_claim,
)

router = APIRouter(prefix="/travel-km", tags=["Employee Travel & KM"])
logger = logging.getLogger(__name__)


def _role(auth: CurrentAuth) -> str:
    return auth.effective_role.strip().lower()


def _require(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=403, detail="Insufficient permission for this Travel & KM action")


def _claim(db: Session, auth: CurrentAuth, claim_id: int) -> TravelKmClaim:
    row = get_visible_claim(db, claim_id=claim_id, viewer=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Travel KM claim not found")
    return row


def _employee_safe_verification_payload(payload: dict) -> dict:
    """Redact internal project/site identity from employee-facing verification evidence.

    Employees still receive the evidence needed to understand the advisory score
    (site-entered flag, distance, radius and timing), but never the configured
    site name or exact project-site center coordinates.
    """
    result = dict(payload)
    geofence = dict(result.get("geofence") or {})
    if geofence:
        geofence["site_name"] = "Assigned Project Site" if geofence.get("configured") else None
        geofence["center_latitude"] = None
        geofence["center_longitude"] = None
        result["geofence"] = geofence
    return result


def _tracking_events(db: Session, claim_id: int) -> tuple[TravelKmEvent | None, TravelKmEvent | None]:
    events = list(db.scalars(
        select(TravelKmEvent)
        .where(
            TravelKmEvent.claim_id == claim_id,
            TravelKmEvent.action.in_(["live_tracking_started", "live_tracking_stopped"]),
        )
        .order_by(TravelKmEvent.created_at.desc(), TravelKmEvent.id.desc())
    ).all())
    latest_start = next((event for event in events if event.action == "live_tracking_started"), None)
    latest_stop = next((event for event in events if event.action == "live_tracking_stopped"), None)
    return latest_start, latest_stop


def _tracking_is_active(db: Session, row: TravelKmClaim) -> bool:
    latest_start, latest_stop = _tracking_events(db, row.id)
    if latest_start is None or row.end_captured_at is not None or row.status != "draft":
        return False
    if latest_stop is None:
        return True
    return (latest_start.created_at, latest_start.id) > (latest_stop.created_at, latest_stop.id)


def _track_point_payload(point: TravelKmTrackPoint) -> dict:
    return {
        "id": point.id,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "accuracy_m": point.accuracy_m,
        "speed_mps": point.speed_mps,
        "heading_deg": point.heading_deg,
        "captured_at": point.captured_at,
        "received_at": point.received_at,
    }


def _tracking_snapshot(db: Session, row: TravelKmClaim, *, limit: int = 1500) -> dict:
    limit = max(1, min(limit, 5000))
    all_points = list(db.scalars(
        select(TravelKmTrackPoint)
        .where(TravelKmTrackPoint.claim_id == row.id)
        .order_by(TravelKmTrackPoint.captured_at.asc(), TravelKmTrackPoint.id.asc())
    ).all())
    points = all_points[-limit:]
    route_distance_km = 0.0
    for previous, current in zip(all_points, all_points[1:]):
        route_distance_km += haversine_km(previous.latitude, previous.longitude, current.latitude, current.longitude)
    latest_start, latest_stop = _tracking_events(db, row.id)
    active = _tracking_is_active(db, row)
    latest = all_points[-1] if all_points else None
    live_now = bool(
        active
        and latest is not None
        and latest.received_at >= (utc_now() - timedelta(minutes=2))
    )
    return {
        "tracking_active": active,
        "live_now": live_now,
        "started_at": latest_start.created_at if latest_start else None,
        "stopped_at": latest_stop.created_at if latest_stop else None,
        "point_count": len(all_points),
        "route_distance_km": round(route_distance_km, 3),
        "last_point": _track_point_payload(latest) if latest else None,
        "points": [_track_point_payload(point) for point in points],
        "foreground_tracking_note": "Browser live tracking is reliable while this Travel/KM page remains active. Mobile browsers may pause GPS updates when the phone is locked or the browser is suspended.",
    }


def _require_tracking_owner(row: TravelKmClaim, auth: CurrentAuth) -> None:
    if row.requester_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Only the employee who owns this claim can send live GPS points")
    if row.status != "draft" or row.end_captured_at is not None:
        raise HTTPException(status_code=409, detail="Live GPS tracking is available only during an active journey before End Journey is saved")


def _audit(db: Session, request: Request, auth: CurrentAuth, event: str, claim: TravelKmClaim, details: dict | None = None) -> None:
    record_audit(
        db, event_type=event, request=request, user=auth.user, module="travel_km",
        target_type="travel_km_claim", target_id=claim.id,
        details={"claim_code": claim.claim_code, "status": claim.status, **(details or {})},
    )


def _notify(
    db: Session,
    *,
    claim: TravelKmClaim,
    event_type: str,
    title: str,
    message: str,
    recipient_user_ids: list[int] | None = None,
    recipient_roles: list[str] | None = None,
) -> None:
    """Best-effort workflow notification; notification outages never roll back a valid claim action."""
    try:
        create_global_notification(
            db,
            event_type=event_type,
            title=title,
            message=message,
            category="approval",
            target_url=f"/travel-km/{claim.id}",
            recipient_user_ids=recipient_user_ids,
            recipient_roles=recipient_roles,
        )
    except Exception:
        logger.exception("Travel KM workflow notification could not be created for claim %s", claim.id)


@router.get("/projects")
def employee_project_numbers(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    """Employee-safe project selector.

    Every employee can see the Client + Project identity needed to choose an
    ongoing project. Completed/on-hold/inactive/upcoming projects are returned
    with a blocked status so the UI can show them instead of silently hiding
    them. Client contacts, email, BD and commercial metadata remain redacted.
    """
    _require(auth, EMPLOYEE_ROLE)
    rows: list[dict] = []
    for project in all_projects(db):
        safe = employee_project_payload(project)
        rows.append({
            "id": project.id,
            "project_number": safe["project_code"],
            "project_name": safe["project_name"],
            "client_name": safe.get("client_name"),
            "task": safe.get("task"),
            "lifecycle_status": safe.get("lifecycle_status"),
            "claim_allowed": bool(safe.get("expense_allowed")),
            "claim_block_reason": safe.get("expense_block_reason"),
        })
    return rows


@router.get("/claims")
def claims(
    status_filter: str | None = Query(default=None, alias="status"),
    project_id: int | None = None,
    requester_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    rows = list_visible_claims(db, viewer=auth.user, effective_role=_role(auth), status=status_filter, project_id=project_id, requester_id=requester_id, date_from=date_from, date_to=date_to)
    return [claim_payload(db, row, viewer=auth.user, effective_role=_role(auth)) for row in rows]


@router.post("/claims", status_code=status.HTTP_201_CREATED)
def create(
    payload: TravelKmClaimCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    # Project lifecycle/status is the access gate. create_claim() validates the
    # selected project against status and project dates.
    try:
        row = create_claim(db, requester=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_CLAIM_CREATED", row)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.put("/claims/{claim_id}/email-routing")
def update_email_routing(
    claim_id: int,
    payload: TravelKmEmailRoutingRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        set_email_routing(db, claim=row, requester=auth.user, payload=payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    add_event(
        db, claim=row, action="email_routing_updated", actor=auth.user,
        from_status=row.status, to_status=row.status,
        comments="Employee updated Reporting Manager, TO and CC recipients for the Travel/KM submission email.",
    )
    _audit(db, request, auth, "TRAVEL_KM_EMAIL_ROUTING_UPDATED", row)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.get("/projects/{project_id}/geofence")
def get_project_site_geofence(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE, ADMIN_ROLE, HR_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE)
    try:
        payload = project_geofence_payload(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if _role(auth) == EMPLOYEE_ROLE:
        # Never leak internal project/client naming through the geofence endpoint.
        return {
            "configured": payload.get("configured", False),
            "active": payload.get("active", False),
            "project_id": project_id,
            "project_code": payload.get("project_code"),
            "project_name": None,
            "site_name": "Assigned Project Site" if payload.get("configured") else None,
            "center_latitude": None,
            "center_longitude": None,
            "radius_m": payload.get("radius_m"),
            "updated_at": payload.get("updated_at"),
        }
    return payload


@router.put("/projects/{project_id}/geofence")
def update_project_site_geofence(
    project_id: int,
    payload: TravelKmProjectGeofenceRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    # Management remains read-only. Admin owns project-site geofence configuration.
    _require(auth, ADMIN_ROLE)
    try:
        row = set_project_geofence(db, project_id=project_id, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit(
        db,
        event_type="TRAVEL_KM_PROJECT_GEOFENCE_UPDATED",
        request=request,
        user=auth.user,
        module="travel_km",
        target_type="finance_project",
        target_id=project_id,
        details={
            "site_name": row.site_name,
            "center_latitude": row.center_latitude,
            "center_longitude": row.center_longitude,
            "radius_m": row.radius_m,
            "is_active": row.is_active,
        },
    )
    db.commit()
    return project_geofence_payload(db, project_id)


@router.post("/claims/{claim_id}/tracking/start")
def start_live_tracking(
    claim_id: int, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    _require_tracking_owner(row, auth)
    add_event(
        db, claim=row, action="live_tracking_started", actor=auth.user,
        from_status=row.status, to_status=row.status,
        comments="Employee explicitly started live GPS tracking for the active journey.",
        metadata={"consent_action": "employee_tapped_start_live_gps", "tracking_scope": "active_travel_claim_only"},
    )
    _audit(db, request, auth, "TRAVEL_KM_LIVE_TRACKING_STARTED", row)
    db.commit()
    return _tracking_snapshot(db, row)


@router.post("/claims/{claim_id}/tracking/point", status_code=status.HTTP_201_CREATED)
def record_live_tracking_point(
    claim_id: int, payload: TravelKmTrackPointRequest,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    _require_tracking_owner(row, auth)
    if not _tracking_is_active(db, row):
        raise HTTPException(status_code=409, detail="Tap Start Live GPS Tracking before sending journey locations")
    captured_at = payload.captured_at.replace(tzinfo=None)
    now = datetime.utcnow()
    if captured_at > now + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="GPS timestamp is too far in the future")
    if captured_at < row.start_captured_at - timedelta(minutes=10):
        raise HTTPException(status_code=422, detail="GPS timestamp predates the active journey")
    existing = db.scalar(
        select(TravelKmTrackPoint).where(
            TravelKmTrackPoint.claim_id == row.id,
            TravelKmTrackPoint.captured_at == captured_at,
        )
    )
    if existing is not None:
        return _track_point_payload(existing)
    point = TravelKmTrackPoint(
        claim_id=row.id, latitude=payload.latitude, longitude=payload.longitude,
        accuracy_m=payload.accuracy_m, speed_mps=payload.speed_mps, heading_deg=payload.heading_deg,
        captured_at=captured_at, source="browser_watch",
    )
    db.add(point)
    db.flush()
    db.commit(); db.refresh(point)
    return _track_point_payload(point)


@router.post("/claims/{claim_id}/tracking/stop")
def stop_live_tracking(
    claim_id: int, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    if row.requester_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Only the employee who owns this claim can stop live GPS tracking")
    if _tracking_is_active(db, row):
        add_event(
            db, claim=row, action="live_tracking_stopped", actor=auth.user,
            from_status=row.status, to_status=row.status,
            comments="Employee stopped live GPS tracking.",
            metadata={"consent_action": "employee_tapped_stop_live_gps"},
        )
        _audit(db, request, auth, "TRAVEL_KM_LIVE_TRACKING_STOPPED", row)
        db.commit()
    return _tracking_snapshot(db, row)


@router.get("/claims/{claim_id}/tracking")
def live_tracking_snapshot(
    claim_id: int, limit: int = Query(default=1500, ge=1, le=5000),
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    row = _claim(db, auth, claim_id)
    return _tracking_snapshot(db, row, limit=limit)


@router.get("/claims/{claim_id}/verification")
def smart_journey_verification(
    claim_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    row = _claim(db, auth, claim_id)
    payload = verification_payload(db, row)
    if _role(auth) == EMPLOYEE_ROLE:
        return _employee_safe_verification_payload(payload)
    return payload


@router.get("/claims/{claim_id}")
def claim_detail(claim_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    row = _claim(db, auth, claim_id)
    return claim_payload(db, row, viewer=auth.user, effective_role=_role(auth))


@router.put("/claims/{claim_id}/end")
def complete_journey(
    claim_id: int, payload: TravelKmEndRequest, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    tracking_was_active = _tracking_is_active(db, row)
    try:
        row = finish_journey(db, claim=row, requester=auth.user, payload=payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    if tracking_was_active:
        add_event(
            db, claim=row, action="live_tracking_stopped", actor=auth.user,
            from_status=row.status, to_status=row.status,
            comments="Live GPS tracking stopped automatically when End Journey was saved.",
            metadata={"automatic_stop": True},
        )
    _audit(db, request, auth, "TRAVEL_KM_JOURNEY_COMPLETED", row)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.put("/claims/{claim_id}/revise")
def revise(
    claim_id: int, payload: TravelKmReviseRequest, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        row = revise_claim(db, claim=row, requester=auth.user, payload=payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_CLAIM_REVISED", row)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.post("/claims/{claim_id}/attachments")
async def upload_photo(
    claim_id: int,
    request: Request,
    phase: str = Query(pattern="^(start|end)$"),
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    accuracy_m: float | None = Query(default=None, ge=0),
    captured_at: datetime = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    if not row.requester_id == auth.user.id or row.status not in {"draft", "admin_sent_back", "hr_sent_back"}:
        raise HTTPException(status_code=409, detail="Odometer evidence is locked at the current workflow stage")
    raw = await file.read()
    try:
        photo = validate_travel_photo(filename=file.filename, declared_mime_type=file.content_type, data=raw)
    except TravelPhotoValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if phase == "start":
        row.start_latitude, row.start_longitude = latitude, longitude
        row.start_accuracy_m, row.start_captured_at = accuracy_m, captured_at.replace(tzinfo=None)
    else:
        if row.end_km is None:
            raise HTTPException(status_code=409, detail="Record End KM and live End GPS before uploading the End photo")
        row.end_latitude, row.end_longitude = latitude, longitude
        row.end_accuracy_m, row.end_captured_at = accuracy_m, captured_at.replace(tzinfo=None)

    mismatch_m = None
    flag = "live_gps_captured"
    if photo.exif_latitude is not None and photo.exif_longitude is not None:
        mismatch_m = haversine_km(latitude, longitude, photo.exif_latitude, photo.exif_longitude) * 1000.0
        flag = "exif_matches_live_gps" if mismatch_m <= 250 else "exif_live_gps_mismatch"
    elif accuracy_m is not None and accuracy_m > 100:
        flag = "low_gps_accuracy"

    existing = db.scalar(select(TravelKmAttachment).where(TravelKmAttachment.claim_id == row.id, TravelKmAttachment.phase == phase))
    old_key = existing.storage_key if existing else None
    try:
        storage_key = store_travel_photo(row.id, phase, photo)
    except TravelPhotoStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if existing is None:
        existing = TravelKmAttachment(claim_id=row.id, phase=phase, uploaded_by_id=auth.user.id, original_filename=photo.original_filename, storage_key=storage_key, mime_type=photo.mime_type, file_size=photo.file_size, content_sha256=photo.content_sha256, device_latitude=latitude, device_longitude=longitude, device_accuracy_m=accuracy_m, device_captured_at=captured_at.replace(tzinfo=None), exif_gps_present=photo.exif_latitude is not None and photo.exif_longitude is not None, exif_latitude=photo.exif_latitude, exif_longitude=photo.exif_longitude, exif_captured_at=photo.exif_captured_at, exif_device_distance_m=mismatch_m, verification_flag=flag)
        db.add(existing)
    else:
        existing.uploaded_by_id = auth.user.id; existing.original_filename = photo.original_filename; existing.storage_key = storage_key
        existing.mime_type = photo.mime_type; existing.file_size = photo.file_size; existing.content_sha256 = photo.content_sha256
        existing.device_latitude = latitude; existing.device_longitude = longitude; existing.device_accuracy_m = accuracy_m; existing.device_captured_at = captured_at.replace(tzinfo=None)
        existing.exif_gps_present = photo.exif_latitude is not None and photo.exif_longitude is not None
        existing.exif_latitude = photo.exif_latitude; existing.exif_longitude = photo.exif_longitude; existing.exif_captured_at = photo.exif_captured_at
        existing.exif_device_distance_m = mismatch_m; existing.verification_flag = flag
    recalculate_claim(row)
    add_event(db, claim=row, action=f"{phase}_photo_uploaded", actor=auth.user, from_status=row.status, to_status=row.status, comments=f"{phase.title()} geotagged odometer evidence uploaded.", metadata={"verification_flag": flag, "gps_accuracy_m": accuracy_m, "exif_live_distance_m": mismatch_m})
    _audit(db, request, auth, "TRAVEL_KM_PHOTO_UPLOADED", row, {"phase": phase, "verification_flag": flag})
    db.commit(); db.refresh(existing)
    if old_key and old_key != storage_key:
        delete_travel_photo(old_key)
    return {"id": existing.id, "phase": existing.phase, "verification_flag": existing.verification_flag, "exif_gps_present": existing.exif_gps_present, "exif_device_distance_m": existing.exif_device_distance_m}


@router.get("/claims/{claim_id}/attachments/{attachment_id}/preview")
def photo_preview(claim_id: int, attachment_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    row = _claim(db, auth, claim_id)
    item = db.get(TravelKmAttachment, attachment_id)
    if item is None or item.claim_id != row.id:
        raise HTTPException(status_code=404, detail="Travel evidence not found")
    try:
        return {"data_url": preview_data_url(item.storage_key), "phase": item.phase, "verification_flag": item.verification_flag}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored travel evidence is unavailable") from exc
    except TravelPhotoStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/claims/{claim_id}/attachments/{attachment_id}/download")
def photo_download(claim_id: int, attachment_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    row = _claim(db, auth, claim_id)
    item = db.get(TravelKmAttachment, attachment_id)
    if item is None or item.claim_id != row.id:
        raise HTTPException(status_code=404, detail="Travel evidence not found")
    try:
        stream = stream_travel_photo(item.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored travel evidence is unavailable") from exc
    except TravelPhotoStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StreamingResponse(stream, media_type=item.mime_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.original_filename)}"})


@router.post("/claims/{claim_id}/submit")
def submit(claim_id: int, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    was_resubmission = row.submitted_at is not None
    try:
        row = submit_claim(db, claim=row, requester=auth.user)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_SUBMITTED", row)
    _notify(db, claim=row, event_type="travel_km_submitted", title="Travel KM claim needs Admin verification", message=f"{row.claim_code} was submitted and is waiting for Admin verification.", recipient_roles=[ADMIN_ROLE])
    db.commit()

    delivery = send_submission_email(
        db,
        claim=row,
        actor=auth.user,
        public_base_url=str(request.base_url).rstrip("/"),
        event_type="resubmission" if was_resubmission else "submission",
    )
    email_action = "submission_email_failed" if delivery.status == "failed" else "submission_email_sent"
    email_comment = (
        f"Travel/KM submission email failed: {delivery.error_message}"
        if delivery.status == "failed"
        else (
            "Travel/KM submission email recorded in local console/log mode."
            if delivery.status == "console"
            else "Travel/KM submission email sent to the configured TO and CC recipients."
        )
    )
    add_event(
        db, claim=row, action=email_action, actor=auth.user,
        from_status=row.status, to_status=row.status, comments=email_comment,
        metadata={"delivery_status": delivery.status, "delivery_mode": delivery.delivery_mode},
    )
    _audit(
        db, request, auth,
        "TRAVEL_KM_SUBMISSION_EMAIL_FAILED" if delivery.status == "failed" else "TRAVEL_KM_SUBMISSION_EMAIL_SENT",
        row, {"delivery_status": delivery.status, "delivery_mode": delivery.delivery_mode},
    )
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.post("/claims/{claim_id}/email/retry")
def retry_submission_email(
    claim_id: int, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    _require(auth, EMPLOYEE_ROLE)
    row = _claim(db, auth, claim_id)
    if row.requester_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Employees can retry email only for their own Travel/KM claims")
    if row.submitted_at is None:
        raise HTTPException(status_code=409, detail="Submit the Travel/KM claim before retrying the email notification")
    delivery = send_submission_email(
        db, claim=row, actor=auth.user, public_base_url=str(request.base_url).rstrip("/"), event_type="manual_retry",
    )
    add_event(
        db, claim=row,
        action="submission_email_failed" if delivery.status == "failed" else "submission_email_sent",
        actor=auth.user, from_status=row.status, to_status=row.status,
        comments=(delivery.error_message if delivery.status == "failed" else "Employee retried the Travel/KM submission email notification."),
        metadata={"delivery_status": delivery.status, "delivery_mode": delivery.delivery_mode, "manual_retry": True},
    )
    _audit(db, request, auth, "TRAVEL_KM_SUBMISSION_EMAIL_RETRY", row, {"delivery_status": delivery.status})
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.post("/claims/{claim_id}/admin-decision")
def admin_action(claim_id: int, payload: TravelKmDecisionRequest, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    _require(auth, ADMIN_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        row = admin_decision(db, claim=row, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_ADMIN_DECISION", row, {"action": payload.action})
    if payload.action == "approve":
        _notify(db, claim=row, event_type="travel_km_admin_approved", title="Travel KM claim Admin verified", message=f"{row.claim_code} passed Admin verification and is waiting for HR.", recipient_user_ids=[row.requester_id], recipient_roles=[HR_ROLE])
    else:
        _notify(db, claim=row, event_type=f"travel_km_admin_{payload.action}", title=f"Travel KM claim {payload.action.replace('_', ' ')} by Admin", message=f"{row.claim_code} requires your attention. Review the Admin remarks and workflow status.", recipient_user_ids=[row.requester_id])
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.post("/claims/{claim_id}/hr-decision")
def hr_action(claim_id: int, payload: TravelKmDecisionRequest, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    _require(auth, HR_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        row = hr_decision(db, claim=row, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_HR_DECISION", row, {"action": payload.action})
    if payload.action == "approve":
        _notify(db, claim=row, event_type="travel_km_hr_approved", title="Travel KM claim HR approved", message=f"{row.claim_code} passed HR verification and is waiting for final Finance approval for monthly salary addition.", recipient_user_ids=[row.requester_id], recipient_roles=[FINANCE_ROLE])
    else:
        _notify(db, claim=row, event_type=f"travel_km_hr_{payload.action}", title=f"Travel KM claim {payload.action.replace('_', ' ')} by HR", message=f"{row.claim_code} requires your attention. Review the HR remarks and workflow status.", recipient_user_ids=[row.requester_id])
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


def _notify_finance_outcome(db: Session, row: TravelKmClaim, *, action: str) -> None:
    approved = action != "reject"
    _notify(
        db,
        claim=row,
        event_type="travel_km_finance_approved" if approved else "travel_km_finance_rejected",
        title="Travel KM claim Finance approved" if approved else "Travel KM claim rejected by Finance",
        message=(
            f"{row.claim_code} received final Finance approval and the approved allowance will be included through monthly salary processing."
            if approved
            else f"{row.claim_code} was rejected by Finance. Review the Finance remarks."
        ),
        recipient_user_ids=[row.requester_id],
        # Final outcome returns visibly to Admin + HR and is also surfaced to
        # both Management accounts (Vinod and Chethan) through role targeting.
        recipient_roles=[ADMIN_ROLE, HR_ROLE, MANAGEMENT_ROLE],
    )


@router.post("/claims/{claim_id}/finance-decision")
def finance_decision_action(claim_id: int, payload: TravelKmFinanceDecisionRequest, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    _require(auth, FINANCE_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        row = finance_decision(db, claim=row, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(db, request, auth, "TRAVEL_KM_FINANCE_DECISION", row, {"action": payload.action})
    _notify_finance_outcome(db, row, action=payload.action)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.post("/claims/{claim_id}/finance-payment")
def finance_action_legacy(claim_id: int, payload: TravelKmPaymentRequest, request: Request, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    """V1 compatibility route. No payment is recorded; pay maps to approval."""
    _require(auth, FINANCE_ROLE)
    row = _claim(db, auth, claim_id)
    try:
        row = finance_payment(db, claim=row, actor=auth.user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    action = "reject" if payload.action == "reject" else "approve"
    _audit(db, request, auth, "TRAVEL_KM_FINANCE_DECISION_LEGACY_ROUTE", row, {"action": action})
    _notify_finance_outcome(db, row, action=action)
    db.commit()
    return claim_payload(db, _claim(db, auth, row.id), viewer=auth.user, effective_role=_role(auth))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)) -> dict:
    _require(auth, ADMIN_ROLE, HR_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE)
    return dashboard_payload(db, viewer=auth.user, effective_role=_role(auth))


@router.get("/reports.xlsx")
def report(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _require(auth, ADMIN_ROLE, HR_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE)
    stream = build_travel_km_workbook(db, viewer=auth.user, effective_role=_role(auth))
    filename = "NakshaTech Employee Travel KM Report.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})
