"""Read-only, stage-based progress rules for NakshaTech management tracking.

These are estimates of workflow stages completed, NOT time/area measurements.
Never treat an unknown state as completed work.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

DONE = {"complete", "completed", "done", "passed", "approved", "delivered", "accepted", "success", "finished"}
STARTED = {"working", "started", "active", "in_progress", "ongoing", "processing", "submitted", "under_review"}
FAIL = {"rework", "returned", "rejected", "failed", "fail", "correction_required", "needs_rework"}


def normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _matches(value: Any, terms: set[str]) -> bool:
    s = normalized(value)
    return s in terms or any(s.startswith(t + "_") or s.endswith("_" + t) for t in terms)


def classify_state(value: Any) -> str:
    s = normalized(value)
    if not s or s in {"none", "pending", "not_started", "unassigned", "not_applicable"}:
        return "pending"
    if _matches(s, FAIL):
        return "rework"
    if _matches(s, DONE) or s in {"ready_for_delivery", "ready", "closed"}:
        return "completed"
    if _matches(s, STARTED) or any(x in s for x in ("progress", "process", "review", "started")):
        return "working"
    return "unknown"


def stage_score(*, production: Any = None, qc: Any = None, qa: Any = None,
                delivered: bool = False, ready: bool = False, fallback: Any = None) -> tuple[int | None, str]:
    """Workflow milestone score: production 45, QC 25, QA 20, delivery 10.

    A failed later stage cannot be called complete; a rework status wins over earlier passes.
    Unknown stages return None unless a known earlier milestone is verified.
    """
    if delivered:
        return 100, "completed"
    stages = [classify_state(production), classify_state(qc), classify_state(qa)]
    if "rework" in stages or classify_state(fallback) == "rework":
        # A rework is visible independently from the numeric milestone score.
        if stages[2] == "rework":
            return 70 if stages[1] == "completed" else 45, "rework"
        if stages[1] == "rework":
            return 45 if stages[0] == "completed" else 0, "rework"
        return 0, "rework"
    if ready:
        return 90, "working"
    if stages[2] == "completed":
        return 90, "working"
    if stages[2] == "working":
        return 70, "working"
    if stages[1] == "completed":
        return 70, "working"
    if stages[1] == "working":
        return 45, "working"
    if stages[0] == "completed":
        return 45, "working"
    if stages[0] == "working":
        return 0, "working"
    s = normalized(fallback)
    if s in {"delivered", "final_delivered"}:
        return 100, "completed"
    if s in {"completed", "operational_completed", "final_completed"}:
        return 90, "working"
    if "ready" in s:
        return 90, "working"
    if "qa" in s:
        return 70, "working"
    if "qc" in s:
        return 45, "working"
    if "production" in s or "processing" in s:
        return 0, "working"
    if s in {"not_started", "pending", "planned", "draft"}:
        return 0, "pending"
    return None, "unknown"


def file_score(status: Any, *, activities: list[Any] | None = None, package_delivered: bool = False) -> tuple[int | None, str]:
    """Use file state and append-only per-file activity, never a made-up percent."""
    state = normalized(status)
    activity_by_stage: dict[str, Any] = {}
    for row in sorted(activities or [], key=lambda a: (getattr(a, "created_at", None) or datetime.min, getattr(a, "id", 0))):
        stage = normalized(getattr(row, "stage", ""))
        if stage in {"production", "qc", "qa", "delivery"}:
            activity_by_stage[stage] = getattr(row, "status", None)
    if classify_state(state) == "rework":
        return stage_score(production=activity_by_stage.get("production"), qc=activity_by_stage.get("qc"),
                           qa=activity_by_stage.get("qa"), fallback="rework")
    if state in {"delivered", "final_delivered"} or package_delivered:
        return 100, "completed"
    if state in {"complete", "completed", "finished"}:
        return 90, "working"
    if activity_by_stage:
        score, color = stage_score(production=activity_by_stage.get("production"),
                                   qc=activity_by_stage.get("qc"), qa=activity_by_stage.get("qa"),
                                   delivered=classify_state(activity_by_stage.get("delivery")) == "completed")
        if score is not None:
            return score, color
    if "ready" in state or "delivery" in state:
        return 90, "working"
    if "qa" in state:
        return (90 if classify_state(state) == "completed" else 70), "working"
    if "qc" in state:
        return (70 if classify_state(state) == "completed" else 45), "working"
    if "production" in state or "processing" in state:
        return (45 if classify_state(state) == "completed" else 0), "working"
    if state in {"not_started", "pending", "planned"}:
        return 0, "pending"
    if package_delivered:
        return 100, "completed"
    return None, "unknown"


def weighted_progress(units: list[dict[str, Any]]) -> int | None:
    """Include unrecognized work units in the denominator, never silently inflate progress."""
    if not units or all(u.get("score") is None for u in units):
        return None
    rows = [(max(0.0, float(u.get("weight") or 1)), u.get("score")) for u in units]
    weight = sum(w for w, _ in rows)
    if weight <= 0:
        return None
    return round(sum(w * float(score if score is not None else 0) for w, score in rows) / weight)


def department_name(code: str) -> str:
    s = normalized(code)
    labels = {
        "software": "Software Development", "software_team": "Software Development",
        "laser_scanning": "Laser Scanning", "mobile_mapping": "Mobile Mapping",
        "lidar": "LiDAR", "ortho": "Ortho / Photogrammetry",
        "civil": "Civil / Survey", "bim": "BIM / 3D Modelling",
        "drone": "Drone Survey", "gis": "GIS",
    }
    return labels.get(s, s.replace("_", " ").title() if s else "Unassigned")


def is_software(department: str) -> bool:
    return normalized(department) in {"software", "software_team", "software_development"}
