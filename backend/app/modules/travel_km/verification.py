from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import math
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceProject
from app.modules.travel_km.models import (
    TravelKmClaim,
    TravelKmProjectGeofence,
    TravelKmTrackPoint,
    TravelKmVerificationSnapshot,
)
from app.modules.travel_km.schemas import TravelKmProjectGeofenceRequest

SMART_VERIFICATION_VERSION = "v5.0"


def _km3(value: float | Decimal | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _pct2(value: float | Decimal | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def get_project_geofence(db: Session, project_id: int) -> TravelKmProjectGeofence | None:
    return db.scalar(
        select(TravelKmProjectGeofence).where(TravelKmProjectGeofence.project_id == project_id)
    )


def project_geofence_payload(db: Session, project_id: int) -> dict:
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise ValueError("Finance Project was not found")
    row = get_project_geofence(db, project_id)
    if row is None:
        return {
            "configured": False,
            "active": False,
            "project_id": project_id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "site_name": None,
            "center_latitude": None,
            "center_longitude": None,
            "radius_m": None,
            "updated_at": None,
        }
    return {
        "configured": True,
        "active": bool(row.is_active),
        "project_id": project_id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "site_name": row.site_name,
        "center_latitude": row.center_latitude,
        "center_longitude": row.center_longitude,
        "radius_m": row.radius_m,
        "updated_at": row.updated_at,
    }


def set_project_geofence(
    db: Session,
    *,
    project_id: int,
    actor: User,
    payload: TravelKmProjectGeofenceRequest,
) -> TravelKmProjectGeofence:
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise ValueError("Finance Project was not found")
    row = get_project_geofence(db, project_id)
    if row is None:
        row = TravelKmProjectGeofence(
            project_id=project_id,
            site_name=payload.site_name.strip(),
            center_latitude=float(payload.center_latitude),
            center_longitude=float(payload.center_longitude),
            radius_m=float(payload.radius_m),
            is_active=bool(payload.is_active),
            configured_by_id=actor.id,
        )
        db.add(row)
    else:
        row.site_name = payload.site_name.strip()
        row.center_latitude = float(payload.center_latitude)
        row.center_longitude = float(payload.center_longitude)
        row.radius_m = float(payload.radius_m)
        row.is_active = bool(payload.is_active)
        row.configured_by_id = actor.id
        row.updated_at = utc_now()
    db.flush()
    return row


def _route_metrics(points: list[TravelKmTrackPoint]) -> dict:
    ordered = sorted(points, key=lambda item: (item.captured_at, item.id or 0))
    route_distance_km = 0.0
    discarded_segments = 0
    gaps: list[float] = []
    accuracies = [float(p.accuracy_m) for p in ordered if p.accuracy_m is not None]

    for previous, current in zip(ordered, ordered[1:]):
        delta_s = max(0.0, (current.captured_at - previous.captured_at).total_seconds())
        if delta_s > 0:
            gaps.append(delta_s)
        segment_km = _haversine_km(
            previous.latitude,
            previous.longitude,
            current.latitude,
            current.longitude,
        )
        # Skip clearly impossible browser-GPS jumps from the route-distance reference.
        # This protects the advisory score from a single bad mobile location sample.
        derived_speed_mps = (segment_km * 1000.0 / delta_s) if delta_s > 0 else None
        if derived_speed_mps is not None and derived_speed_mps > 70.0:
            discarded_segments += 1
            continue
        if segment_km > 5.0 and delta_s <= 60.0:
            discarded_segments += 1
            continue
        route_distance_km += segment_km

    return {
        "point_count": len(ordered),
        "route_distance_km": route_distance_km,
        "max_gap_seconds": max(gaps) if gaps else None,
        "median_accuracy_m": median(accuracies) if accuracies else None,
        "discarded_segments": discarded_segments,
    }


def _geofence_metrics(claim: TravelKmClaim, points: list[TravelKmTrackPoint], geofence: TravelKmProjectGeofence | None) -> dict:
    if geofence is None:
        return {
            "configured": False,
            "active": False,
            "project_id": claim.project_id,
            "site_name": None,
            "center_latitude": None,
            "center_longitude": None,
            "radius_m": None,
            "site_entered": False,
            "nearest_distance_m": None,
            "first_entry_at": None,
            "last_presence_at": None,
            "onsite_minutes": 0,
        }

    result = {
        "configured": True,
        "active": bool(geofence.is_active),
        "project_id": claim.project_id,
        "site_name": geofence.site_name,
        "center_latitude": geofence.center_latitude,
        "center_longitude": geofence.center_longitude,
        "radius_m": geofence.radius_m,
        "site_entered": False,
        "nearest_distance_m": None,
        "first_entry_at": None,
        "last_presence_at": None,
        "onsite_minutes": 0,
    }
    if not geofence.is_active:
        return result

    samples: list[tuple[datetime, float, float]] = [
        (claim.start_captured_at, claim.start_latitude, claim.start_longitude),
    ]
    samples.extend((point.captured_at, point.latitude, point.longitude) for point in points)
    if claim.end_captured_at is not None and claim.end_latitude is not None and claim.end_longitude is not None:
        samples.append((claim.end_captured_at, claim.end_latitude, claim.end_longitude))
    samples.sort(key=lambda item: item[0])

    distances: list[tuple[datetime, float]] = []
    for captured_at, lat, lon in samples:
        meters = _haversine_km(lat, lon, geofence.center_latitude, geofence.center_longitude) * 1000.0
        distances.append((captured_at, meters))
    if distances:
        result["nearest_distance_m"] = min(distance for _, distance in distances)

    inside = [(captured_at, distance <= geofence.radius_m) for captured_at, distance in distances]
    inside_times = [captured_at for captured_at, is_inside in inside if is_inside]
    result["site_entered"] = bool(inside_times)
    if inside_times:
        result["first_entry_at"] = min(inside_times)
        result["last_presence_at"] = max(inside_times)

    onsite_seconds = 0.0
    for (previous_at, previous_inside), (current_at, current_inside) in zip(inside, inside[1:]):
        gap = max(0.0, (current_at - previous_at).total_seconds())
        # Only count continuous in-geofence evidence. A long browser pause does not
        # automatically become on-site time.
        if previous_inside and current_inside and gap <= 300.0:
            onsite_seconds += gap
    result["onsite_minutes"] = int(round(onsite_seconds / 60.0))
    return result


def _score_component(key: str, label: str, earned: int, available: int, status: str) -> dict:
    return {
        "key": key,
        "label": label,
        "earned": int(earned),
        "available": int(available),
        "status": status,
    }


def build_verification(db: Session, claim: TravelKmClaim) -> dict:
    points = list(
        db.scalars(
            select(TravelKmTrackPoint)
            .where(TravelKmTrackPoint.claim_id == claim.id)
            .order_by(TravelKmTrackPoint.captured_at.asc(), TravelKmTrackPoint.id.asc())
        ).all()
    )
    route = _route_metrics(points)
    geofence_row = get_project_geofence(db, claim.project_id)
    geofence = _geofence_metrics(claim, points, geofence_row)

    odometer_km = float(claim.odometer_km) if claim.odometer_km is not None else None
    route_variance_km = None
    route_variance_percent = None
    if odometer_km is not None and odometer_km > 0 and route["route_distance_km"] > 0:
        route_variance_km = abs(odometer_km - route["route_distance_km"])
        route_variance_percent = (route_variance_km / odometer_km) * 100.0

    phases = {item.phase for item in claim.attachments}
    photo_count = int("start" in phases) + int("end" in phases)

    components: list[dict] = []
    point_count = route["point_count"]
    if point_count >= 10:
        gps_points_score = 30
    elif point_count >= 5:
        gps_points_score = 24
    elif point_count >= 3:
        gps_points_score = 16
    elif point_count >= 1:
        gps_points_score = 8
    else:
        gps_points_score = 0
    components.append(_score_component("gps_route", "Live GPS route evidence", gps_points_score, 30, "good" if gps_points_score >= 24 else "review"))

    max_gap = route["max_gap_seconds"]
    if max_gap is None:
        continuity_score = 0
    elif max_gap <= 60:
        continuity_score = 15
    elif max_gap <= 180:
        continuity_score = 10
    elif max_gap <= 600:
        continuity_score = 5
    else:
        continuity_score = 0
    components.append(_score_component("gps_continuity", "GPS continuity", continuity_score, 15, "good" if continuity_score >= 10 else "review"))

    median_accuracy = route["median_accuracy_m"]
    if median_accuracy is None:
        accuracy_score = 0
    elif median_accuracy <= 30:
        accuracy_score = 10
    elif median_accuracy <= 75:
        accuracy_score = 7
    elif median_accuracy <= 150:
        accuracy_score = 4
    else:
        accuracy_score = 1
    components.append(_score_component("gps_accuracy", "GPS accuracy", accuracy_score, 10, "good" if accuracy_score >= 7 else "review"))

    if route_variance_percent is None:
        consistency_score = 0
    elif route_variance_percent <= 10:
        consistency_score = 25
    elif route_variance_percent <= 20:
        consistency_score = 20
    elif route_variance_percent <= 35:
        consistency_score = 12
    elif route_variance_percent <= 50:
        consistency_score = 5
    else:
        consistency_score = 0
    components.append(_score_component("distance_consistency", "Odometer vs tracked route", consistency_score, 25, "good" if consistency_score >= 20 else "review"))

    photo_score = 10 if photo_count == 2 else 4 if photo_count == 1 else 0
    components.append(_score_component("photo_evidence", "Start & End odometer evidence", photo_score, 10, "good" if photo_score == 10 else "review"))

    available_score = 90
    if geofence["configured"] and geofence["active"]:
        available_score += 10
        nearest = geofence["nearest_distance_m"]
        radius = geofence["radius_m"] or 0
        if geofence["site_entered"]:
            geofence_score = 10
        elif nearest is not None and radius and nearest <= radius * 2:
            geofence_score = 5
        else:
            geofence_score = 0
        components.append(_score_component("project_geofence", "Project site geofence", geofence_score, 10, "good" if geofence_score == 10 else "review"))

    earned_score = sum(item["earned"] for item in components)
    normalized_score = int(round((earned_score / available_score) * 100)) if available_score else 0

    flags: list[dict] = []
    if point_count < 3:
        flags.append({"code": "insufficient_gps", "severity": "high", "message": "Fewer than 3 live GPS route points were recorded."})
    elif point_count < 10:
        flags.append({"code": "limited_gps", "severity": "medium", "message": "Live GPS route evidence is limited; review the route before approval."})
    if route_variance_percent is not None and route_variance_percent > 50:
        flags.append({"code": "high_route_variance", "severity": "high", "message": f"Odometer distance differs from tracked route by {route_variance_percent:.1f}%."})
    elif route_variance_percent is not None and route_variance_percent > 25:
        flags.append({"code": "route_variance", "severity": "medium", "message": f"Odometer distance differs from tracked route by {route_variance_percent:.1f}%."})
    if max_gap is not None and max_gap > 600:
        flags.append({"code": "gps_gap", "severity": "medium", "message": f"The largest GPS recording gap was {int(max_gap // 60)} minutes."})
    if median_accuracy is not None and median_accuracy > 150:
        flags.append({"code": "low_gps_accuracy", "severity": "medium", "message": f"Median GPS accuracy was approximately {median_accuracy:.0f} m."})
    if route["discarded_segments"]:
        flags.append({"code": "gps_outliers_filtered", "severity": "info", "message": f"{route['discarded_segments']} impossible GPS jump(s) were excluded from route-distance scoring."})
    if photo_count < 2:
        flags.append({"code": "missing_odometer_evidence", "severity": "high", "message": "Both Start and End odometer photos are required for complete verification."})
    if geofence["configured"] and geofence["active"] and not geofence["site_entered"]:
        flags.append({"code": "site_not_reached", "severity": "medium", "message": "The recorded journey did not enter the configured project-site geofence."})

    ready_for_final_score = bool(claim.end_km is not None and claim.end_captured_at is not None and photo_count == 2)
    if not ready_for_final_score:
        outcome = "collecting"
        score: int | None = None
    elif point_count < 3:
        outcome = "insufficient_gps"
        score = normalized_score
    elif route_variance_percent is not None and route_variance_percent > 50:
        outcome = "high_variance"
        score = normalized_score
    elif normalized_score >= 80:
        outcome = "verified"
        score = normalized_score
    elif normalized_score >= 60:
        outcome = "review"
        score = normalized_score
    else:
        outcome = "needs_review"
        score = normalized_score

    labels = {
        "collecting": "Collecting Evidence",
        "verified": "Verified",
        "review": "Review Recommended",
        "needs_review": "Needs Review",
        "high_variance": "High Variance",
        "insufficient_gps": "Insufficient GPS",
    }
    return {
        "source": "live_preview",
        "source_version": SMART_VERIFICATION_VERSION,
        "generated_at": utc_now(),
        "snapshot_locked": False,
        "advisory_only": True,
        "score": score,
        "outcome": outcome,
        "outcome_label": labels[outcome],
        "route": {
            "point_count": point_count,
            "route_distance_km": round(route["route_distance_km"], 3),
            "odometer_km": odometer_km,
            "variance_km": round(route_variance_km, 3) if route_variance_km is not None else None,
            "variance_percent": round(route_variance_percent, 2) if route_variance_percent is not None else None,
            "max_gap_seconds": round(max_gap, 1) if max_gap is not None else None,
            "median_accuracy_m": round(median_accuracy, 1) if median_accuracy is not None else None,
            "discarded_segments": route["discarded_segments"],
        },
        "evidence": {
            "photo_count": photo_count,
            "start_photo": "start" in phases,
            "end_photo": "end" in phases,
        },
        "geofence": geofence,
        "components": components,
        "flags": flags,
        "scoring_note": "Smart Journey Verification is an advisory evidence score. It never auto-rejects a claim, changes eligible KM, or changes the ₹5/KM allowance.",
    }


def _snapshot_payload(snapshot: TravelKmVerificationSnapshot) -> dict:
    components = json.loads(snapshot.components_json or "[]")
    flags = json.loads(snapshot.flags_json or "[]")
    labels = {
        "verified": "Verified",
        "review": "Review Recommended",
        "needs_review": "Needs Review",
        "high_variance": "High Variance",
        "insufficient_gps": "Insufficient GPS",
    }
    return {
        "source": "submission_snapshot",
        "source_version": snapshot.source_version,
        "generated_at": snapshot.generated_at,
        "snapshot_locked": True,
        "advisory_only": True,
        "score": snapshot.score,
        "outcome": snapshot.outcome,
        "outcome_label": labels.get(snapshot.outcome, snapshot.outcome.replace("_", " ").title()),
        "route": {
            "point_count": snapshot.point_count,
            "route_distance_km": float(snapshot.route_distance_km),
            "odometer_km": float(snapshot.odometer_km),
            "variance_km": float(snapshot.route_variance_km) if snapshot.route_variance_km is not None else None,
            "variance_percent": float(snapshot.route_variance_percent) if snapshot.route_variance_percent is not None else None,
            "max_gap_seconds": snapshot.max_gap_seconds,
            "median_accuracy_m": snapshot.median_accuracy_m,
            "discarded_segments": snapshot.discarded_segments,
        },
        "evidence": {
            "photo_count": snapshot.photo_count,
            "start_photo": snapshot.photo_count >= 1,
            "end_photo": snapshot.photo_count >= 2,
        },
        "geofence": {
            "configured": snapshot.geofence_configured,
            "active": snapshot.geofence_configured,
            "project_id": snapshot.project_id,
            "site_name": snapshot.site_name,
            "center_latitude": snapshot.site_center_latitude,
            "center_longitude": snapshot.site_center_longitude,
            "radius_m": snapshot.site_radius_m,
            "site_entered": snapshot.site_entered,
            "nearest_distance_m": snapshot.nearest_site_distance_m,
            "first_entry_at": snapshot.first_site_entry_at,
            "last_presence_at": snapshot.last_site_presence_at,
            "onsite_minutes": snapshot.onsite_minutes,
        },
        "components": components,
        "flags": flags,
        "scoring_note": "Smart Journey Verification is an advisory evidence score. It never auto-rejects a claim, changes eligible KM, or changes the ₹5/KM allowance.",
    }


def freeze_verification_snapshot(db: Session, claim: TravelKmClaim) -> TravelKmVerificationSnapshot:
    result = build_verification(db, claim)
    if result["score"] is None:
        # Submission requirements should normally prevent this, but keep the
        # snapshot deterministic if an old claim is migrated through the flow.
        score = 0
        outcome = "needs_review"
    else:
        score = int(result["score"])
        outcome = result["outcome"]

    route = result["route"]
    geofence = result["geofence"]
    snapshot = db.scalar(
        select(TravelKmVerificationSnapshot).where(TravelKmVerificationSnapshot.claim_id == claim.id)
    )
    if snapshot is None:
        snapshot = TravelKmVerificationSnapshot(claim_id=claim.id, project_id=claim.project_id)
        db.add(snapshot)
    snapshot.project_id = claim.project_id
    snapshot.score = score
    snapshot.outcome = outcome
    snapshot.route_distance_km = _km3(route["route_distance_km"])
    snapshot.odometer_km = _km3(route["odometer_km"])
    snapshot.route_variance_km = _km3(route["variance_km"]) if route["variance_km"] is not None else None
    snapshot.route_variance_percent = _pct2(route["variance_percent"]) if route["variance_percent"] is not None else None
    snapshot.point_count = int(route["point_count"])
    snapshot.max_gap_seconds = int(round(route["max_gap_seconds"])) if route["max_gap_seconds"] is not None else None
    snapshot.median_accuracy_m = route["median_accuracy_m"]
    snapshot.discarded_segments = int(route["discarded_segments"])
    snapshot.photo_count = int(result["evidence"]["photo_count"])
    snapshot.geofence_configured = bool(geofence["configured"] and geofence["active"])
    snapshot.site_name = geofence["site_name"] if snapshot.geofence_configured else None
    snapshot.site_center_latitude = geofence["center_latitude"] if snapshot.geofence_configured else None
    snapshot.site_center_longitude = geofence["center_longitude"] if snapshot.geofence_configured else None
    snapshot.site_radius_m = geofence["radius_m"] if snapshot.geofence_configured else None
    snapshot.site_entered = bool(geofence["site_entered"]) if snapshot.geofence_configured else False
    snapshot.nearest_site_distance_m = geofence["nearest_distance_m"] if snapshot.geofence_configured else None
    snapshot.first_site_entry_at = geofence["first_entry_at"] if snapshot.geofence_configured else None
    snapshot.last_site_presence_at = geofence["last_presence_at"] if snapshot.geofence_configured else None
    snapshot.onsite_minutes = int(geofence["onsite_minutes"] or 0) if snapshot.geofence_configured else 0
    snapshot.components_json = json.dumps(result["components"], ensure_ascii=False, sort_keys=True)
    snapshot.flags_json = json.dumps(result["flags"], ensure_ascii=False, sort_keys=True)
    snapshot.source_version = SMART_VERIFICATION_VERSION
    snapshot.generated_at = utc_now()
    db.flush()
    return snapshot


def verification_payload(db: Session, claim: TravelKmClaim) -> dict:
    snapshot = db.scalar(
        select(TravelKmVerificationSnapshot).where(TravelKmVerificationSnapshot.claim_id == claim.id)
    )
    if snapshot is not None and claim.submitted_at is not None:
        return _snapshot_payload(snapshot)
    return build_verification(db, claim)
