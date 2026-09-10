from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.management_access import (
    ADMIN_ACCOUNT,
    ADMIN_ROLE,
    AUTHORIZED_EMAILS_BY_ROLE,
    FIRST_LOGIN_ACCOUNTS_BY_ROLE,
    FINANCE_ROLE,
    HR_ROLE,
    IT_ROLE,
    MANAGEMENT_ROLE,
    SOFTWARE_TEAM_ROLE,
)
from app.core.roles import BD_ROLE, ORTHO_ROLE
from app.core.security import hash_password
from app.models.entities import Asset, Drone, DroneLocation, ReplacementRecord, User, WorkRecord
from app.modules.employee_portal.models import AuthenticatorCredential
from app.services.excel_import_service import import_nakshatech_workbook


def development_users() -> list[tuple[str, str, str, str]]:
    users = [
        (ADMIN_ACCOUNT.email, "NakshaTech Administrator", settings.seed_admin_password, ADMIN_ROLE),
        (settings.seed_drone_email, "Drone Department", settings.seed_drone_password, "drone"),
    ]
    if (
        settings.seed_organization_admin_email.strip()
        and settings.seed_organization_admin_password
        and settings.seed_organization_admin_email.strip().lower() != ADMIN_ACCOUNT.email
    ):
        users.append(
            (
                settings.seed_organization_admin_email.strip(),
                settings.seed_organization_admin_name.strip() or "NakshaTech Administrator",
                settings.seed_organization_admin_password,
                ADMIN_ROLE,
            )
        )
    return users


def _temporary_passwords_by_role() -> dict[str, tuple[str, ...]]:
    return {
        MANAGEMENT_ROLE: (
            settings.seed_management_password,
            settings.seed_management_secondary_password,
        ),
        SOFTWARE_TEAM_ROLE: (settings.seed_software_team_password,),
        IT_ROLE: (settings.seed_it_password,),
        FINANCE_ROLE: (settings.seed_finance_password,),
        HR_ROLE: (settings.seed_hr_password,),
    }


def _ensure_admin_role(db: Session) -> None:
    """Correct the historic Admin/Software-Team collision without changing its password."""
    email = ADMIN_ACCOUNT.email
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        configured_password = settings.seed_admin_password.strip()
        if configured_password:
            db.add(
                User(
                    email=email,
                    full_name=ADMIN_ACCOUNT.full_name,
                    password_hash=hash_password(configured_password),
                    role=ADMIN_ROLE,
                    branch="Head Office",
                    email_verified=True,
                    account_status="active",
                    mfa_required=False,
                    must_change_password=False,
                    is_active=True,
                )
            )
        return

    # Preserve the existing password hash. The screenshot's role-mismatch error
    # proves the credential was valid and only the stored role was wrong.
    user.email = email
    user.role = ADMIN_ROLE
    user.full_name = user.full_name or ADMIN_ACCOUNT.full_name
    user.branch = user.branch or "Head Office"
    user.email_verified = True
    if user.account_status == "disabled_privileged_access":
        user.account_status = "active"
        user.is_active = True
        user.must_change_password = False
        user.mfa_required = False


def ensure_privileged_accounts(db: Session) -> None:
    """Provision authoritative Management, Software Team, and IT accounts.

    Fully activated authoritative accounts retain their permanent password. New,
    converted, or still-pending accounts use the private temporary password from
    environment configuration and must complete one Authenticator verification
    followed by permanent-password creation. Unauthorized accounts holding one of
    these privileged roles are disabled without deleting their audit history.
    """
    _ensure_admin_role(db)
    db.flush()
    passwords_by_role = _temporary_passwords_by_role()

    for role, accounts in FIRST_LOGIN_ACCOUNTS_BY_ROLE.items():
        passwords = passwords_by_role[role]
        if len(accounts) != len(passwords):
            raise RuntimeError(f"Temporary password configuration is incomplete for {role}")

        for account, temporary_password in zip(accounts, passwords, strict=True):
            email = account.email.lower()
            user = db.scalar(select(User).where(func.lower(User.email) == email))
            created_or_converted = user is None or (user is not None and user.role != role)
            confirmed_authenticator = False
            if user is not None:
                confirmed_authenticator = bool(db.scalar(
                    select(AuthenticatorCredential.id).where(
                        AuthenticatorCredential.user_id == user.id,
                        AuthenticatorCredential.is_confirmed.is_(True),
                    )
                ))
            legacy_department_account = role in {SOFTWARE_TEAM_ROLE, IT_ROLE, FINANCE_ROLE, HR_ROLE} and not confirmed_authenticator
            if user is None:
                user = User(
                    email=email,
                    full_name=account.full_name,
                    password_hash=hash_password(temporary_password),
                    role=role,
                    branch="Head Office",
                    email_verified=True,
                    account_status="pending_mfa",
                    mfa_required=True,
                    must_change_password=True,
                    is_active=False,
                )
                db.add(user)
                continue

            user.email = email
            user.full_name = account.full_name
            user.role = role
            user.branch = user.branch or "Head Office"
            user.email_verified = True

            if created_or_converted or legacy_department_account or user.account_status in {
                "disabled_management_access",
                "disabled_privileged_access",
            }:
                user.password_hash = hash_password(temporary_password)
                user.account_status = "pending_mfa"
                user.mfa_required = True
                user.must_change_password = True
                user.is_active = False
                user.token_version = (user.token_version or 0) + 1
            elif user.must_change_password:
                # Preserve a completed Authenticator step across restarts. Before
                # that step, refresh the temporary-password hash from protected
                # environment configuration so deployment remains authoritative.
                if user.account_status == "pending_password_change":
                    user.mfa_required = False
                    user.is_active = False
                else:
                    user.password_hash = hash_password(temporary_password)
                    user.account_status = "pending_mfa"
                    user.mfa_required = True
                    user.is_active = False

    privileged_roles = tuple(FIRST_LOGIN_ACCOUNTS_BY_ROLE)
    privileged_users = db.scalars(select(User).where(User.role.in_(privileged_roles))).all()
    for user in privileged_users:
        normalized_email = user.email.strip().lower()
        if normalized_email in AUTHORIZED_EMAILS_BY_ROLE.get(user.role, frozenset()):
            continue
        user.is_active = False
        user.account_status = "disabled_privileged_access"
        user.mfa_required = False
        user.must_change_password = False
        user.token_version = (user.token_version or 0) + 1

    db.commit()


def ensure_management_accounts(db: Session) -> None:
    """Backward-compatible alias used by existing tests and deployments."""
    ensure_privileged_accounts(db)


_OBSOLETE_OPERATIONS_TEST_EMPLOYEE_IDS = {
    "TEST-BD-EMP",
    "TEST-ORTHO-TL",
    "TEST-ORTHO-PROD",
    "TEST-ORTHO-QC",
    "TEST-ORTHO-QA",
}


def _operations_test_account_specs() -> list[tuple[str, str, str, str, str, str, str]]:
    """Return only the three V7.0.7 test identities requested by the workflow owner.

    BD and Ortho each use one manager login. The normal employee fixture stays
    an ordinary employee account for tickets/expenses and never receives an
    Ortho or BD role.
    """
    return [
        (settings.seed_bd_manager_email, "BD Manager Test", settings.seed_bd_manager_password, BD_ROLE, "Business Development", "Manager", "TEST-BD-MGR"),
        (settings.seed_ortho_pm_email, "Ortho Project Manager Test", settings.seed_ortho_pm_password, ORTHO_ROLE, "Ortho", "Project Manager", "TEST-ORTHO-PM"),
        (settings.seed_employee_test_email, "Employee Test", settings.seed_employee_test_password, "employee", "Employee", "Employee", "TEST-EMPLOYEE-001"),
    ]


def ensure_operations_test_accounts(db: Session) -> None:
    """Provision the local/UAT BD manager, Ortho PM, and normal employee logins.

    Clear-text credentials are supplied only through environment-backed
    settings. PostgreSQL stores password hashes. This helper is disabled by
    default and production configuration rejects enabling it.

    The V7.0.7 permission model intentionally has no separate TL/Production/QC/QA
    login roles. Those people are assignees recorded by the Project Manager; the
    Project Manager performs all Ortho workflow updates in the single /ortho
    dashboard.
    """
    if not settings.seed_operations_test_users_enabled:
        return

    allowed_domains = set(settings.allowed_email_domain_list)
    specs = _operations_test_account_specs()
    configured_emails = {email.strip().lower() for email, *_ in specs}

    # If the superseded V7.0.5 seven-account test design ever ran, keep its
    # extra fixtures from remaining active. These IDs were reserved exclusively
    # for generated test users.
    obsolete = db.scalars(select(User).where(User.employee_id.in_(_OBSOLETE_OPERATIONS_TEST_EMPLOYEE_IDS))).all()
    for user in obsolete:
        if user.email.strip().lower() == settings.seed_employee_test_email.strip().lower() and user.employee_id == "TEST-BD-EMP":
            # Migrate the exact old employee1 fixture into the requested normal
            # employee account instead of leaving it as a BD user.
            user.employee_id = "TEST-EMPLOYEE-001"
            user.role = "employee"
            user.department = "Employee"
            user.designation = "Employee"
            continue
        if user.email.strip().lower() not in configured_emails:
            user.is_active = False
            user.account_status = "disabled_superseded_test_fixture"
            user.mfa_required = False
            user.must_change_password = False
            user.token_version = (user.token_version or 0) + 1

    for configured_email, full_name, password, role, department, designation, employee_id in specs:
        email = configured_email.strip().lower()
        if not email or not password:
            raise RuntimeError(f"BD/Ortho/employee test credential configuration is incomplete for {designation}")
        if "@" not in email or email.rsplit("@", 1)[1] not in allowed_domains:
            raise RuntimeError(f"Test account must use an allowed organization email: {email}")
        if len(password) < 10:
            raise RuntimeError(f"Test password must be at least 10 characters for {email}")

        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.employee_id not in {employee_id, "TEST-BD-EMP" if employee_id == "TEST-EMPLOYEE-001" else employee_id}:
            raise RuntimeError(
                f"Refusing to repurpose existing user {email}: the address is not a managed V7 test fixture"
            )
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role=role,
                branch="Head Office",
                employee_id=employee_id,
                department=department,
                designation=designation,
                email_verified=True,
                account_status="active",
                mfa_required=False,
                must_change_password=False,
                is_active=True,
            )
            db.add(user)
            continue

        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.role = role
        user.employee_id = employee_id
        user.branch = user.branch or "Head Office"
        user.department = department
        user.designation = designation
        user.email_verified = True
        user.account_status = "active"
        user.mfa_required = False
        user.must_change_password = False
        user.is_active = True

    db.commit()


def seed_database(db: Session) -> None:
    if not db.scalar(select(User.id).limit(1)):
        db.add_all(
            [
                User(
                    email=email,
                    full_name=name,
                    password_hash=hash_password(password),
                    role=role,
                    branch="Head Office",
                    email_verified=True,
                    account_status="active",
                    mfa_required=False,
                    must_change_password=False,
                )
                for email, name, password, role in development_users()
            ]
        )
        db.commit()

    if not db.scalar(select(Asset.id).limit(1)):
        excel_path = Path(settings.seed_excel_path)
        if excel_path.exists():
            import_nakshatech_workbook(db, excel_path)

    if not db.scalar(select(Drone.id).limit(1)):
        drone = Drone(
            asset_code="NT-DR-0001",
            name="Survey Drone 01",
            model="Trinity F90+",
            serial_number="TR-001",
            pilot="Drone Team",
            project="Davangere Urban Survey",
            status="deployed",
            battery_percent=78,
        )
        db.add(drone)
        db.flush()
        db.add(
            DroneLocation(
                drone_id=drone.id,
                latitude=14.4644,
                longitude=75.9218,
                altitude=112.0,
                speed=0.0,
                heading=45.0,
                battery_percent=78,
                source="seed",
            )
        )

    if not db.scalar(select(WorkRecord.id).limit(1)):
        sample_asset = db.scalar(select(Asset).order_by(Asset.id).limit(1))
        db.add_all(
            [
                WorkRecord(
                    work_code="ITW-0001",
                    module="it",
                    asset_id=sample_asset.id if sample_asset else None,
                    title="Initial hardware verification",
                    work_type="Inspection",
                    assigned_to=sample_asset.used_by if sample_asset else "IT Team",
                    technician="IT Department",
                    priority="medium",
                    issue_description="Verify the imported hardware and assignment record.",
                    status="in_progress",
                    approval_status="not_required",
                ),
                WorkRecord(
                    work_code="DRW-0001",
                    module="drone",
                    title="Complete project flight plan",
                    work_type="Flight Planning",
                    project="Davangere Urban Survey",
                    assigned_to="Drone Team",
                    technician="Drone Department",
                    priority="high",
                    status="open",
                    approval_status="pending",
                ),
            ]
        )

    db.commit()
