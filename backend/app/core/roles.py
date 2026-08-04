from __future__ import annotations

ADMIN_ROLE = "admin"
SOFTWARE_TEAM_ROLE = "software_team"
MANAGEMENT_ROLE = "management"
IT_ROLE = "it"
DRONE_ROLE = "drone"
EMPLOYEE_ROLE = "employee"

VALID_ROLES = {
    ADMIN_ROLE,
    SOFTWARE_TEAM_ROLE,
    MANAGEMENT_ROLE,
    IT_ROLE,
    DRONE_ROLE,
    EMPLOYEE_ROLE,
}

ADMIN_EQUIVALENT_ROLES = {ADMIN_ROLE, SOFTWARE_TEAM_ROLE}


def is_admin_equivalent(role: str | None) -> bool:
    return (role or "").strip().lower() in ADMIN_EQUIVALENT_ROLES


def role_is_allowed(user_role: str, allowed_roles: set[str]) -> bool:
    normalized = user_role.strip().lower()
    if normalized in allowed_roles:
        return True
    # Software Team keeps every permission that was previously granted to Admin.
    return normalized == SOFTWARE_TEAM_ROLE and ADMIN_ROLE in allowed_roles


def role_display_name(role: str) -> str:
    normalized = role.strip().lower()
    labels = {
        SOFTWARE_TEAM_ROLE: "Software Team",
        ADMIN_ROLE: "Admin",
        MANAGEMENT_ROLE: "Management",
        IT_ROLE: "IT Department",
        DRONE_ROLE: "Drone Department",
        EMPLOYEE_ROLE: "Employee Support",
    }
    return labels.get(normalized, normalized.replace("_", " ").title())


def backup_role(role: str) -> str:
    """Map full-access Software Team exports to the existing Admin export scope."""
    return ADMIN_ROLE if role.strip().lower() == SOFTWARE_TEAM_ROLE else role.strip().lower()
