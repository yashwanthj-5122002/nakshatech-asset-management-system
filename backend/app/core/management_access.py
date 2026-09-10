from __future__ import annotations

from dataclasses import dataclass


MANAGEMENT_ROLE = "management"
SOFTWARE_TEAM_ROLE = "software_team"
IT_ROLE = "it"
FINANCE_ROLE = "finance"
HR_ROLE = "hr"
ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class PrivilegedAccountSpec:
    role: str
    display_name: str
    full_name: str
    email: str


MANAGEMENT_ACCOUNTS: tuple[PrivilegedAccountSpec, ...] = (
    PrivilegedAccountSpec(
        role=MANAGEMENT_ROLE,
        display_name="Vinod Kumar CS",
        full_name="Vinod Kumar CS",
        email="vinod@nakshatech.com",
    ),
    PrivilegedAccountSpec(
        role=MANAGEMENT_ROLE,
        display_name="Chethan Kumar KG",
        full_name="Chethan Kumar KG",
        email="chethan@nakshatech.com",
    ),
)

SOFTWARE_TEAM_ACCOUNTS: tuple[PrivilegedAccountSpec, ...] = (
    PrivilegedAccountSpec(
        role=SOFTWARE_TEAM_ROLE,
        display_name="Software Team",
        full_name="Software Team",
        email="software.team@nakshatech.com",
    ),
)

IT_ACCOUNTS: tuple[PrivilegedAccountSpec, ...] = (
    PrivilegedAccountSpec(
        role=IT_ROLE,
        display_name="IT Support",
        full_name="IT Department",
        email="it-support@nakshatech.com",
    ),
)

FINANCE_ACCOUNTS: tuple[PrivilegedAccountSpec, ...] = (
    PrivilegedAccountSpec(
        role=FINANCE_ROLE,
        display_name="Finance Team",
        full_name="Finance Department",
        email="finance@nakshatech.com",
    ),
)
HR_ACCOUNTS: tuple[PrivilegedAccountSpec, ...] = (
    PrivilegedAccountSpec(
        role=HR_ROLE,
        display_name="HR Team",
        full_name="HR Department",
        email="hr@nakshatech.com",
    ),
)

ADMIN_ACCOUNT = PrivilegedAccountSpec(
    role=ADMIN_ROLE,
    display_name="Administrator",
    full_name="NakshaTech Administrator",
    email="admin@nakshatech.com",
)

FIRST_LOGIN_ACCOUNTS_BY_ROLE: dict[str, tuple[PrivilegedAccountSpec, ...]] = {
    MANAGEMENT_ROLE: MANAGEMENT_ACCOUNTS,
    SOFTWARE_TEAM_ROLE: SOFTWARE_TEAM_ACCOUNTS,
    IT_ROLE: IT_ACCOUNTS,
    FINANCE_ROLE: FINANCE_ACCOUNTS,
    HR_ROLE: HR_ACCOUNTS,
}
FIRST_LOGIN_PRIVILEGED_ROLES = frozenset(FIRST_LOGIN_ACCOUNTS_BY_ROLE)
AUTHORIZED_EMAILS_BY_ROLE = {
    role: frozenset(account.email for account in accounts)
    for role, accounts in FIRST_LOGIN_ACCOUNTS_BY_ROLE.items()
}

MANAGEMENT_EMAILS = AUTHORIZED_EMAILS_BY_ROLE[MANAGEMENT_ROLE]
SOFTWARE_TEAM_EMAILS = AUTHORIZED_EMAILS_BY_ROLE[SOFTWARE_TEAM_ROLE]
IT_EMAILS = AUTHORIZED_EMAILS_BY_ROLE[IT_ROLE]
FINANCE_EMAILS = AUTHORIZED_EMAILS_BY_ROLE[FINANCE_ROLE]
HR_EMAILS = AUTHORIZED_EMAILS_BY_ROLE[HR_ROLE]


def normalize_privileged_email(value: str) -> str:
    return value.strip().lower()


def normalize_management_email(value: str) -> str:
    return normalize_privileged_email(value)


def is_authorized_privileged_email(role: str, value: str) -> bool:
    normalized_role = role.strip().lower()
    return normalize_privileged_email(value) in AUTHORIZED_EMAILS_BY_ROLE.get(normalized_role, frozenset())


def is_authorized_management_email(value: str) -> bool:
    return is_authorized_privileged_email(MANAGEMENT_ROLE, value)


def privileged_account_payload(role: str) -> list[dict[str, str]]:
    normalized_role = role.strip().lower()
    return [
        {
            "display_name": account.display_name,
            "full_name": account.full_name,
            "email": account.email,
        }
        for account in FIRST_LOGIN_ACCOUNTS_BY_ROLE.get(normalized_role, ())
    ]


def management_account_payload() -> list[dict[str, str]]:
    return privileged_account_payload(MANAGEMENT_ROLE)


def is_first_login_privileged_role(role: str) -> bool:
    return role.strip().lower() in FIRST_LOGIN_PRIVILEGED_ROLES
