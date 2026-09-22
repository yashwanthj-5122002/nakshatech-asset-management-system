"""Centralized Performing Department constants and helpers.

One operational workflow (BD -> Finance -> PM -> Team Lead -> Production/QC/QA ->
Delivery -> Billing) is shared by every technical department. This module is the
single place that maps a project's canonical department code to the technical PM
role that must run it and to the free-text label stored on ``User.department``.
Do not scatter raw department string comparisons outside these helpers.
"""

from __future__ import annotations

from app.core.roles import (
    CIVIL_ROLE,
    LASER_SCANNING_ROLE,
    LIDAR_ROLE,
    MOBILE_MAPPING_ROLE,
    ORTHO_ROLE,
)

DEPARTMENT_ORTHO = "ortho"
DEPARTMENT_LIDAR = "lidar"
DEPARTMENT_MOBILE_MAPPING = "mobile_mapping"
DEPARTMENT_LASER_SCANNING = "laser_scanning"
DEPARTMENT_CIVIL = "civil"

DEFAULT_DEPARTMENT = DEPARTMENT_ORTHO

# The technical PM role expected to operate a project performed by this department.
DEPARTMENT_PM_ROLE: dict[str, str] = {
    DEPARTMENT_ORTHO: ORTHO_ROLE,
    DEPARTMENT_LIDAR: LIDAR_ROLE,
    DEPARTMENT_MOBILE_MAPPING: MOBILE_MAPPING_ROLE,
    DEPARTMENT_LASER_SCANNING: LASER_SCANNING_ROLE,
    DEPARTMENT_CIVIL: CIVIL_ROLE,
}

# Human label, also the exact value written to User.department for seeded staff.
DEPARTMENT_LABELS: dict[str, str] = {
    DEPARTMENT_ORTHO: "Ortho",
    DEPARTMENT_LIDAR: "LiDAR",
    DEPARTMENT_MOBILE_MAPPING: "Mobile Mapping",
    DEPARTMENT_LASER_SCANNING: "Laser Scanning",
    DEPARTMENT_CIVIL: "Civil",
}

SUPPORTED_DEPARTMENTS: tuple[str, ...] = tuple(DEPARTMENT_PM_ROLE)
TECHNICAL_PM_ROLES: set[str] = set(DEPARTMENT_PM_ROLE.values())
DEPARTMENT_FOR_PM_ROLE: dict[str, str] = {role: code for code, role in DEPARTMENT_PM_ROLE.items()}


def _normalize_token(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def normalize_department_code(value: str | None) -> str | None:
    """Return the canonical code for a value, or None if it is not a supported department."""
    token = _normalize_token(value)
    return token if token in DEPARTMENT_PM_ROLE else None


def normalize_department_code_or_default(value: str | None) -> str:
    """Same as normalize_department_code but falls back to ORTHO for legacy/blank data."""
    return normalize_department_code(value) or DEFAULT_DEPARTMENT


def department_label(code: str | None) -> str:
    return DEPARTMENT_LABELS.get(normalize_department_code_or_default(code), "Ortho")


def pm_role_for_department(code: str | None) -> str:
    return DEPARTMENT_PM_ROLE.get(normalize_department_code_or_default(code), ORTHO_ROLE)


def department_for_pm_role(role: str | None) -> str | None:
    return DEPARTMENT_FOR_PM_ROLE.get((role or "").strip().lower())


def is_technical_pm_role(role: str | None) -> bool:
    return (role or "").strip().lower() in TECHNICAL_PM_ROLES


def user_department_matches(user_department: str | None, department_code: str | None) -> bool:
    """Case/spacing-insensitive match between User.department free text and a canonical code."""
    return _normalize_token(user_department) == normalize_department_code_or_default(department_code)


def department_options() -> list[dict[str, str]]:
    return [{"code": code, "label": DEPARTMENT_LABELS[code]} for code in SUPPORTED_DEPARTMENTS]
