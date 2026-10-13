from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import random

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.departments import (
    DEPARTMENT_LABELS,
    DEPARTMENT_PM_ROLE,
    SUPPORTED_DEPARTMENTS,
    user_department_matches,
)
from app.models.entities import Asset, Drone, DroneLocation, User, WorkRecord
from app.modules.drone import models as drone_models  # noqa: F401 - registers drone_survey_assets metadata
from app.modules.commercial.models import (
    ProjectBillingBasis,
    ProjectCommercialEstimateRevision,
    ProjectExpense,
    ProjectVendorInvoice,
)
from app.modules.finance.models import (
    ExpenseClaim,
    ExpenseClaimItem,
    ExpenseClaimPayment,
    FinanceClient,
    FinanceClientMasterProfile,
    FinanceProject,
    FinanceProjectAssignment,
    FinanceProjectMasterProfile,
    FinanceRevenueTarget,
)
from app.modules.operations.lifecycle_models import (
    ProjectChangeRequest,
    ProjectFeedbackRequest,
    ProjectFeedbackResponse,
    ProjectInvoice,
    ProjectInvoicePayment,
    ProjectReworkCycle,
)
from app.modules.travel_km.models import TravelKmClaim
from app.modules.operations.models import (
    OrthoDailyUpdate,
    OrthoDelivery,
    OrthoProjectMember,
    OrthoProjectProfile,
    OrthoWorkPackage,
    ProjectWorkflow,
    ProjectWorkflowEvent,
)

TAG = "UAT_YEAR_SIMULATION_2026"
CLIENT_PREFIX = "UAT26-CLI-"
PROJECT_PREFIX = "UAT26-PRJ-"
INVOICE_PREFIX = "UAT26-INV-"
PAYMENT_PREFIX = "UAT26-PAY-"
EXPENSE_PREFIX = "UAT26-EXP-"
CLAIM_PREFIX = "UAT26-CLM-"
FEEDBACK_PREFIX = "UAT26-FB-"
CHANGE_PREFIX = "UAT26-CR-"

TARGET_REALIZED_REVENUE_INR = Decimal("40000000.00")
DEFAULT_CLIENTS = 50
DEFAULT_PROJECTS = 200
DEFAULT_SEED = 2026

# 25-state cycle -> 200 projects gives exact, repeatable coverage.
# 80 fully realized projects, plus open Sales and operational edge states.
ARCHETYPES: tuple[str, ...] = (
    "closed", "closed", "closed", "closed", "closed",
    "closed", "closed", "closed", "closed", "closed",
    "paid_open", "paid_open",
    "partial", "partial",
    "overdue",
    "payment_pending",
    "invoice_raised",
    "ready_for_billing",
    "feedback",
    "rework",
    "change_request",
    "qa",
    "production",
    "finance_returned",
    "draft",
)

CURRENCY_PATTERN: tuple[str, ...] = (
    "INR", "INR", "INR", "INR", "INR", "INR", "INR",
    "USD", "INR", "GBP", "INR", "AED", "INR", "INR", "INR",
    "USD", "INR", "GBP", "INR", "AED",
)

FX_TO_INR: dict[str, Decimal] = {
    "INR": Decimal("1"),
    "USD": Decimal("83.50"),
    "GBP": Decimal("106.00"),
    "AED": Decimal("22.75"),
}


@dataclass(frozen=True)
class PlannedProject:
    ordinal: int
    client_ordinal: int
    project_number: int
    department_code: str
    archetype: str
    currency: str
    award_date: date
    start_date: date
    end_date: date
    projected_payment_date: date
    gross_inr: Decimal


@dataclass
class SeedSummary:
    clients: int = 0
    projects: int = 0
    commercial_revisions: int = 0
    work_packages: int = 0
    invoices: int = 0
    payments: int = 0
    closed_invoices: int = 0
    revenue_inr: Decimal = Decimal("0")
    expenses: int = 0
    vendor_invoices: int = 0
    expense_claims: int = 0
    feedback_requests: int = 0
    rework_cycles: int = 0
    change_requests: int = 0
    travel_km_claims: int = 0
    assets: int = 0
    work_records: int = 0
    drones: int = 0
    revenue_targets: int = 0


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def at_noon(day: date) -> datetime:
    return datetime.combine(day, time(hour=12))


def clamp_2026(day: date) -> date:
    return min(max(day, date(2026, 1, 1)), date(2026, 12, 28))


def _raw_weight(index: int, rng: random.Random) -> Decimal:
    # Stable but non-flat values create useful charts and concentration patterns.
    return Decimal(260000 + ((index * 7919 + rng.randint(0, 180000)) % 520000))


def build_plan(
    *,
    clients: int = DEFAULT_CLIENTS,
    projects: int = DEFAULT_PROJECTS,
    seed: int = DEFAULT_SEED,
    target_realized_revenue_inr: Decimal = TARGET_REALIZED_REVENUE_INR,
) -> list[PlannedProject]:
    if clients <= 0 or projects <= 0:
        raise ValueError("clients and projects must be positive")
    if projects < clients:
        raise ValueError("projects must be greater than or equal to clients")

    rng = random.Random(seed)
    raw: list[Decimal] = [_raw_weight(i, rng) for i in range(projects)]
    closed_indexes = [i for i in range(projects) if ARCHETYPES[i % len(ARCHETYPES)] == "closed"]
    closed_weight = sum((raw[i] for i in closed_indexes), Decimal("0"))
    factor = target_realized_revenue_inr / closed_weight

    gross_values = [
        (raw[i] * factor).quantize(Decimal("1000"), rounding=ROUND_HALF_UP)
        for i in range(projects)
    ]
    # Make the realized total exact after rounding.
    realized = sum((gross_values[i] for i in closed_indexes), Decimal("0"))
    if closed_indexes:
        gross_values[closed_indexes[-1]] += target_realized_revenue_inr - realized

    rows: list[PlannedProject] = []
    departments = tuple(SUPPORTED_DEPARTMENTS)
    for i in range(projects):
        ordinal = i + 1
        client_ordinal = (i % clients) + 1
        project_number = (i // clients) + 1
        month = (i % 12) + 1
        day = 3 + ((i * 7) % 20)
        award = date(2026, month, day)
        start = clamp_2026(award + timedelta(days=5))
        end = clamp_2026(start + timedelta(days=35 + (i % 35)))
        projected = clamp_2026(end + timedelta(days=30))
        rows.append(PlannedProject(
            ordinal=ordinal,
            client_ordinal=client_ordinal,
            project_number=project_number,
            department_code=departments[i % len(departments)],
            archetype=ARCHETYPES[i % len(ARCHETYPES)],
            currency=CURRENCY_PATTERN[i % len(CURRENCY_PATTERN)],
            award_date=award,
            start_date=start,
            end_date=end,
            projected_payment_date=projected,
            gross_inr=money(gross_values[i]),
        ))
    return rows


def _active_users(db: Session, role: str) -> list[User]:
    return list(db.scalars(
        select(User)
        .where(
            func.lower(User.role) == role.lower(),
            User.is_active.is_(True),
            User.account_status == "active",
        )
        .order_by(User.id)
    ).all())


def _staff_context(db: Session) -> tuple[list[User], list[User], dict[str, User], dict[str, list[User]]]:
    bd_users = _active_users(db, "bd")
    finance_users = _active_users(db, "finance")
    if not bd_users:
        raise RuntimeError("2026 UAT seed needs at least one active BD user")
    if not finance_users:
        raise RuntimeError("2026 UAT seed needs at least one active Finance user")

    pms: dict[str, User] = {}
    employees: dict[str, list[User]] = {}
    all_active = list(db.scalars(
        select(User).where(User.is_active.is_(True), User.account_status == "active").order_by(User.id)
    ).all())

    for department in SUPPORTED_DEPARTMENTS:
        pm_role = DEPARTMENT_PM_ROLE[department]
        pm = next((u for u in all_active if (u.role or "").lower() == pm_role and user_department_matches(u.department, department)), None)
        if pm is None:
            pm = next((u for u in all_active if (u.role or "").lower() == pm_role), None)
        if pm is None:
            raise RuntimeError(f"2026 UAT seed needs an active {DEPARTMENT_LABELS[department]} Project Manager")
        pms[department] = pm

        pool = [
            u for u in all_active
            if (u.role or "").lower() == "employee" and user_department_matches(u.department, department)
        ]
        if len(pool) < 4:
            raise RuntimeError(
                f"2026 UAT seed needs at least 4 active Employees in {DEPARTMENT_LABELS[department]}; found {len(pool)}"
            )
        employees[department] = pool
    return bd_users, finance_users, pms, employees


def _optional_staff(db: Session, role: str, fallback: User) -> User:
    rows = _active_users(db, role)
    return rows[0] if rows else fallback


def _ensure_not_production() -> None:
    if settings.is_production:
        raise RuntimeError(f"{TAG} seed/cleanup is forbidden while APP_ENV/ENVIRONMENT is production")


def uat_project_ids(db: Session) -> list[int]:
    return list(db.scalars(
        select(FinanceProject.id).where(FinanceProject.project_code.like(f"{PROJECT_PREFIX}%"))
    ).all())


def uat_client_ids(db: Session) -> list[int]:
    return list(db.scalars(
        select(FinanceClient.id).where(FinanceClient.client_code.like(f"{CLIENT_PREFIX}%"))
    ).all())


def existing_counts(db: Session) -> dict[str, int]:
    return {
        "clients": int(db.scalar(select(func.count()).select_from(FinanceClient).where(FinanceClient.client_code.like(f"{CLIENT_PREFIX}%"))) or 0),
        "projects": int(db.scalar(select(func.count()).select_from(FinanceProject).where(FinanceProject.project_code.like(f"{PROJECT_PREFIX}%"))) or 0),
    }


def _commercial_amounts(gross_inr: Decimal, currency: str) -> dict[str, Decimal]:
    rate = FX_TO_INR[currency]
    base_inr = money(gross_inr / Decimal("1.18"))
    tax_inr = money(gross_inr - base_inr)
    gross_original = money(gross_inr / rate)
    base_original = money(base_inr / rate)
    tax_original = money(gross_original - base_original)
    return {
        "rate": rate,
        "base_inr": base_inr,
        "tax_inr": tax_inr,
        "gross_inr": money(gross_inr),
        "gross_original": gross_original,
        "base_original": base_original,
        "tax_original": tax_original,
    }


def _workflow_status(archetype: str, ordinal: int) -> str:
    if archetype == "closed":
        return "CLOSED" if ordinal % 2 == 0 else "INVOICE_CLOSED"
    return {
        "paid_open": "PAYMENT_RECEIVED",
        "partial": "PARTIALLY_PAID",
        "overdue": "PAYMENT_OVERDUE",
        "payment_pending": "PAYMENT_PENDING",
        "invoice_raised": "INVOICE_RAISED",
        "ready_for_billing": "READY_FOR_BILLING",
        "feedback": "AWAITING_CLIENT_FEEDBACK",
        "rework": "REWORK_OPEN",
        "change_request": "CHANGE_REQUEST_PENDING",
        "qa": "in_progress",
        "production": "in_progress",
        "finance_returned": "finance_returned",
        "draft": "draft",
    }[archetype]


def _package_state(archetype: str) -> tuple[str, str, str, str]:
    if archetype == "production":
        return "production", "in_progress", "not_started", "not_started"
    if archetype == "qa":
        return "qa", "completed", "approved", "pending"
    if archetype in {"draft", "finance_returned"}:
        return "not_started", "not_started", "not_started", "not_started"
    if archetype == "rework":
        return "delivered", "completed", "approved", "approved"
    return "delivered", "completed", "approved", "approved"


def _make_client(
    db: Session,
    *,
    ordinal: int,
    bd: User,
    created_day: date,
) -> FinanceClient:
    code = f"{CLIENT_PREFIX}{ordinal:03d}"
    row = FinanceClient(
        client_code=code,
        client_name=f"UAT 2026 Client {ordinal:03d}",
        primary_phone=f"9000{ordinal:06d}",
        client_email=f"accounts.client{ordinal:03d}@example.com",
        contact_person_name=f"UAT Contact {ordinal:03d}",
        contact_person_phone=f"9100{ordinal:06d}",
        address=f"UAT testing address {ordinal:03d}, India",
        description=f"[{TAG}] Deterministic synthetic client for full-year ERP UAT.",
        country="India" if ordinal % 5 else "United Arab Emirates",
        gst_number=f"29UAT{ordinal:05d}Z1" if ordinal % 5 else None,
        source_team="bd",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=bd.id,
        updated_by_id=bd.id,
        created_at=at_noon(created_day),
        updated_at=at_noon(created_day),
    )
    db.add(row)
    db.flush()
    db.add(FinanceClientMasterProfile(
        client_id=row.id,
        client_type="client",
        task="Synthetic full-year ERP validation",
        bd_name=bd.full_name,
        organization_email=f"finance.client{ordinal:03d}@example.com",
        contact_person_email=f"contact.client{ordinal:03d}@example.com",
        import_source=TAG,
        imported_at=at_noon(created_day),
        created_by_id=bd.id,
        updated_by_id=bd.id,
        created_at=at_noon(created_day),
        updated_at=at_noon(created_day),
    ))
    return row


def seed_year_2026(
    db: Session,
    *,
    clients: int = DEFAULT_CLIENTS,
    projects: int = DEFAULT_PROJECTS,
    seed: int = DEFAULT_SEED,
    target_realized_revenue_inr: Decimal = TARGET_REALIZED_REVENUE_INR,
) -> SeedSummary:
    _ensure_not_production()
    counts = existing_counts(db)
    if counts["clients"] or counts["projects"]:
        raise RuntimeError(
            f"{TAG} already exists (clients={counts['clients']}, projects={counts['projects']}). "
            "Run cleanup_2026_uat_data.py first instead of creating duplicates."
        )

    bd_users, finance_users, pms, employees = _staff_context(db)
    plan = build_plan(
        clients=clients,
        projects=projects,
        seed=seed,
        target_realized_revenue_inr=target_realized_revenue_inr,
    )
    summary = SeedSummary()
    admin_user = _optional_staff(db, "admin", finance_users[0])
    hr_user = _optional_staff(db, "hr", finance_users[0])

    # Representative non-project-master modules: Asset/IT work and Drone inventory.
    # Codes are UAT26-prefixed so cleanup can target them without touching real inventory.
    for asset_no in range(1, 21):
        department = DEPARTMENT_LABELS[SUPPORTED_DEPARTMENTS[(asset_no - 1) % len(SUPPORTED_DEPARTMENTS)]]
        asset = Asset(
            asset_code=f"UAT26-AST-{asset_no:03d}",
            source_sheet=TAG,
            source_row=asset_no,
            used_by=f"UAT Employee {asset_no:03d}",
            workstation_no=f"UAT-WS-{asset_no:03d}",
            department=department,
            system_name=f"UAT-SYS-{asset_no:03d}",
            brand="UAT Brand",
            model="Synthetic Workstation",
            serial_number=f"UAT26-SERIAL-{asset_no:03d}",
            ownership="company",
            device_type="desktop" if asset_no % 2 else "laptop",
            processor="Synthetic CPU",
            memory_gb="16",
            ssd="512 GB",
            operating_system="Windows 11",
            antivirus="Managed",
            network_type="LAN",
            performed_by="UAT 2026 Generator",
            approved_by=admin_user.full_name,
            price=65000.0 + asset_no * 250.0,
            remarks=f"[{TAG}] Synthetic asset inventory fixture",
            asset_date=date(2026, ((asset_no - 1) % 12) + 1, 5),
            original_asset_date=date(2026, ((asset_no - 1) % 12) + 1, 5),
            location="Head Office",
            work_mode="office",
            status="assigned" if asset_no % 3 else "available",
            created_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 5)),
            updated_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 5)),
        )
        db.add(asset)
        db.flush()
        summary.assets += 1
        db.add(WorkRecord(
            work_code=f"UAT26-WRK-{asset_no:03d}",
            module="it",
            asset_id=asset.id,
            title=f"UAT preventive maintenance {asset_no:03d}",
            work_type="Inspection",
            project=None,
            assigned_to=asset.used_by,
            technician="IT Department",
            priority="high" if asset_no % 5 == 0 else "medium",
            issue_description=f"[{TAG}] Synthetic IT maintenance request",
            details="Validate asset work, approval, reporting and history.",
            status="completed" if asset_no % 2 else "in_progress",
            root_cause="Routine UAT validation",
            resolution="Verified synthetic asset" if asset_no % 2 else None,
            cost=500.0 + asset_no * 10,
            approval_status="approved",
            submitted_by_user_id=admin_user.id,
            submitted_by_name=admin_user.full_name,
            submitted_by_email=admin_user.email,
            submitted_by_role=admin_user.role,
            submitted_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 6)),
            approved_by_user_id=admin_user.id,
            approved_by_name=admin_user.full_name,
            approved_by_email=admin_user.email,
            approved_by_role=admin_user.role,
            approved_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 7)),
            approval_comments=f"[{TAG}] Synthetic approval",
            start_date=date(2026, ((asset_no - 1) % 12) + 1, 7),
            expected_completion_date=date(2026, ((asset_no - 1) % 12) + 1, 10),
            completed_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 9)) if asset_no % 2 else None,
            reporting_month=f"2026-{((asset_no - 1) % 12) + 1:02d}",
            created_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 6)),
            updated_at=at_noon(date(2026, ((asset_no - 1) % 12) + 1, 9)),
        ))
        summary.work_records += 1

    for drone_no in range(1, 6):
        drone = Drone(
            asset_code=f"UAT26-DRN-{drone_no:03d}",
            name=f"UAT Survey Drone {drone_no:02d}",
            model="Synthetic UAV",
            serial_number=f"UAT26-DRONE-SN-{drone_no:03d}",
            pilot=f"UAT Pilot {drone_no:02d}",
            project=f"{PROJECT_PREFIX}{drone_no:04d}",
            status="deployed" if drone_no % 2 else "available",
            battery_percent=float(60 + drone_no * 5),
        )
        db.add(drone)
        db.flush()
        db.add(DroneLocation(
            drone_id=drone.id,
            latitude=12.9716 + drone_no * 0.01,
            longitude=77.5946 + drone_no * 0.01,
            altitude=100.0 + drone_no * 10,
            speed=0.0,
            heading=float(drone_no * 30),
            battery_percent=float(60 + drone_no * 5),
            source="uat_2026",
            recorded_at=at_noon(date(2026, drone_no, 15)),
        ))
        summary.drones += 1

    client_rows: dict[int, FinanceClient] = {}
    for ordinal in range(1, clients + 1):
        first_project = next(row for row in plan if row.client_ordinal == ordinal)
        bd = bd_users[(ordinal - 1) % len(bd_users)]
        client_rows[ordinal] = _make_client(
            db,
            ordinal=ordinal,
            bd=bd,
            created_day=first_project.award_date,
        )
        summary.clients += 1

    for spec in plan:
        client = client_rows[spec.client_ordinal]
        bd = bd_users[(spec.ordinal - 1) % len(bd_users)]
        finance = finance_users[(spec.ordinal - 1) % len(finance_users)]
        pm = pms[spec.department_code]
        staff_pool = employees[spec.department_code]
        tl = staff_pool[(spec.ordinal + 0) % len(staff_pool)]
        production = staff_pool[(spec.ordinal + 1) % len(staff_pool)]
        qc = staff_pool[(spec.ordinal + 2) % len(staff_pool)]
        qa = staff_pool[(spec.ordinal + 3) % len(staff_pool)]
        status = _workflow_status(spec.archetype, spec.ordinal)
        values = _commercial_amounts(spec.gross_inr, spec.currency)

        project = FinanceProject(
            project_code=f"{PROJECT_PREFIX}{spec.ordinal:04d}",
            project_name=f"{DEPARTMENT_LABELS[spec.department_code]} UAT Project {spec.ordinal:04d}",
            client_id=client.id,
            client_name=client.client_name,
            project_number=spec.project_number,
            project_source_team="bd",
            project_source_person_name=bd.full_name,
            client_awarded_by_name=client.contact_person_name,
            project_award_date=spec.award_date,
            description=f"[{TAG}] {spec.archetype} synthetic project for end-to-end ERP validation.",
            start_date=spec.start_date,
            end_date=spec.end_date,
            is_active=True,
            created_by_id=bd.id,
            created_at=at_noon(spec.award_date),
            updated_at=at_noon(spec.award_date),
        )
        db.add(project)
        db.flush()
        summary.projects += 1

        progressed = spec.archetype not in {"draft", "finance_returned"}
        db.add(FinanceProjectMasterProfile(
            project_id=project.id,
            task=f"{TAG} / {spec.archetype}",
            project_status="closed" if status == "CLOSED" else "active",
            project_manager_id=pm.id if progressed else None,
            reporting_manager_id=None,
            created_by_id=bd.id,
            updated_by_id=bd.id,
            created_at=at_noon(spec.award_date),
            updated_at=at_noon(spec.award_date),
        ))

        workflow = ProjectWorkflow(
            project_id=project.id,
            bd_owner_user_id=bd.id,
            status=status,
            performing_department_code=spec.department_code,
            scope_text=f"[{TAG}] Synthetic {DEPARTMENT_LABELS[spec.department_code]} scope",
            quantity=Decimal(str(10 + spec.ordinal % 90)),
            quantity_unit="sq_km" if spec.department_code in {"ortho", "lidar"} else "unit",
            priority=("high" if spec.ordinal % 5 == 0 else "medium"),
            commercial_value=values["gross_original"],
            currency=spec.currency,
            po_wo_number=f"UAT26-PO-{spec.ordinal:04d}",
            attachment_references=None,
            finance_feedback="Synthetic Finance return for UAT" if spec.archetype == "finance_returned" else None,
            submission_count=1 if spec.archetype != "draft" else 0,
            finance_reviewer_id=finance.id if spec.archetype != "draft" else None,
            finance_reviewed_at=at_noon(clamp_2026(spec.award_date + timedelta(days=2))) if spec.archetype != "draft" else None,
            submitted_at=at_noon(spec.award_date) if spec.archetype != "draft" else None,
            returned_at=at_noon(clamp_2026(spec.award_date + timedelta(days=2))) if spec.archetype == "finance_returned" else None,
            approved_at=at_noon(clamp_2026(spec.award_date + timedelta(days=2))) if progressed else None,
            pm_assigned_at=at_noon(clamp_2026(spec.award_date + timedelta(days=3))) if progressed else None,
            team_assigned_at=at_noon(clamp_2026(spec.award_date + timedelta(days=4))) if progressed else None,
            operational_completed_at=at_noon(spec.end_date) if spec.archetype not in {"draft", "finance_returned", "production", "qa"} else None,
            completion_date=spec.end_date if spec.archetype not in {"draft", "finance_returned", "production", "qa"} else None,
            final_delivery_reference=f"UAT26-DEL-{spec.ordinal:04d}" if spec.archetype not in {"draft", "finance_returned", "production", "qa"} else None,
            completion_remarks=f"[{TAG}] Synthetic operational completion" if progressed else None,
            finance_closed_at=at_noon(spec.projected_payment_date) if status == "CLOSED" else None,
            finance_closure_remarks=f"[{TAG}] Synthetic Finance closure" if status == "CLOSED" else None,
            created_by_id=bd.id,
            updated_by_id=finance.id if progressed else bd.id,
            created_at=at_noon(spec.award_date),
            updated_at=at_noon(spec.projected_payment_date if progressed else spec.award_date),
        )
        db.add(workflow)
        db.add(ProjectWorkflowEvent(
            project_id=project.id,
            event_type=f"uat_2026_{spec.archetype}",
            from_status=None,
            to_status=status,
            comments=f"[{TAG}] Deterministic lifecycle fixture",
            actor_user_id=finance.id if progressed else bd.id,
            created_at=at_noon(spec.projected_payment_date if progressed else spec.award_date),
        ))

        estimate_status = "APPROVED" if progressed else ("RETURNED" if spec.archetype == "finance_returned" else "DRAFT")
        revision = ProjectCommercialEstimateRevision(
            project_id=project.id,
            revision_no=1,
            is_baseline=True,
            status=estimate_status,
            is_locked=progressed,
            quotation_reference=f"UAT26-SALES-{spec.ordinal:04d}",
            po_wo_reference=f"UAT26-PO-{spec.ordinal:04d}",
            scope_description=f"[{TAG}] Commercial scope for project {spec.ordinal:04d}",
            billing_type="fixed_price",
            payment_terms="30 days from Finance invoice",
            expected_billing_milestone="Final client acceptance",
            projected_payment_date=spec.projected_payment_date,
            notes=f"[{TAG}] BD Sales / Commercial Revision 1",
            currency_code=spec.currency,
            estimated_amount=values["base_original"],
            taxable_base_amount=values["base_original"],
            tax_percent=Decimal("18.00"),
            expected_tax=values["tax_original"],
            expected_gross=values["gross_original"],
            estimated_direct_cost_inr=money(values["base_inr"] * Decimal("0.38")),
            unit_rate=None,
            estimated_quantity=None,
            quantity_unit=None,
            fx_snapshot_id=None,
            fx_rate_to_inr=values["rate"],
            fx_rate_date=spec.award_date,
            fx_rate_source="UAT_2026_FIXED_RATE",
            fx_rate_mode="MANUAL_OVERRIDE",
            estimated_inr=values["base_inr"],
            base_inr=values["base_inr"],
            tax_inr=values["tax_inr"],
            gross_inr=values["gross_inr"],
            estimate_date=spec.award_date,
            reason=f"[{TAG}] initial synthetic commercial baseline",
            created_by_id=bd.id,
            created_at=at_noon(spec.award_date),
            submitted_at=at_noon(spec.award_date) if spec.archetype != "draft" else None,
            approved_by_id=finance.id if progressed else None,
            approved_at=at_noon(clamp_2026(spec.award_date + timedelta(days=2))) if progressed else None,
            decision_comments="Approved synthetic UAT baseline" if progressed else None,
        )
        db.add(revision)
        db.flush()
        summary.commercial_revisions += 1

        if progressed:
            db.add(OrthoProjectProfile(
                project_id=project.id,
                total_area=Decimal(str(5 + spec.ordinal % 95)),
                area_unit="sq_km",
                scope_text=f"[{TAG}] Shared technical operations profile",
                planned_hours=Decimal(str(40 + spec.ordinal % 120)),
                target_value=None,
                project_manager_user_id=pm.id,
                status="completed" if spec.archetype in {"closed", "paid_open", "partial", "overdue", "payment_pending", "invoice_raised", "ready_for_billing", "feedback", "rework", "change_request"} else "active",
                final_delivery_at=at_noon(spec.end_date) if spec.archetype not in {"production", "qa"} else None,
                final_delivery_by_id=pm.id if spec.archetype not in {"production", "qa"} else None,
                final_delivery_remarks=f"[{TAG}] Synthetic final delivery" if spec.archetype not in {"production", "qa"} else None,
                created_by_id=pm.id,
                created_at=at_noon(clamp_2026(spec.award_date + timedelta(days=3))),
                updated_at=at_noon(spec.end_date),
            ))
            for role, user in (
                ("team_leader", tl),
                ("production", production),
                ("qc", qc),
                ("qa", qa),
            ):
                db.add(OrthoProjectMember(
                    project_id=project.id,
                    user_id=user.id,
                    member_role=role,
                    is_active=True,
                    assigned_by_id=pm.id,
                    created_at=at_noon(clamp_2026(spec.award_date + timedelta(days=4))),
                    updated_at=at_noon(clamp_2026(spec.award_date + timedelta(days=4))),
                ))
                db.add(FinanceProjectAssignment(
                    project_id=project.id,
                    user_id=user.id,
                    assigned_by_id=pm.id,
                    is_active=True,
                    created_at=at_noon(clamp_2026(spec.award_date + timedelta(days=4))),
                    updated_at=at_noon(clamp_2026(spec.award_date + timedelta(days=4))),
                ))

            stage, production_state, qc_state, qa_state = _package_state(spec.archetype)
            for package_no in (1, 2):
                package = OrthoWorkPackage(
                    project_id=project.id,
                    package_code=f"UAT26-WP-{spec.ordinal:04d}-{package_no}",
                    package_name=f"UAT Work Package {package_no}",
                    area=Decimal(str(2 + ((spec.ordinal + package_no) % 20))),
                    area_unit="sq_km",
                    target_hours=Decimal(str(12 + ((spec.ordinal + package_no) % 30))),
                    target_date=spec.end_date,
                    instructions=f"[{TAG}] Validate Production -> QC -> QA -> Delivery",
                    current_stage=stage,
                    production_state=production_state,
                    qc_state=qc_state,
                    qa_state=qa_state,
                    team_leader_user_id=tl.id,
                    production_user_id=production.id,
                    qc_user_id=qc.id,
                    qa_user_id=qa.id,
                    production_completed_at=at_noon(clamp_2026(spec.end_date - timedelta(days=7))) if production_state == "completed" else None,
                    qc_submitted_at=at_noon(clamp_2026(spec.end_date - timedelta(days=5))) if qc_state in {"pending", "approved"} else None,
                    qa_submitted_at=at_noon(clamp_2026(spec.end_date - timedelta(days=3))) if qa_state in {"pending", "approved"} else None,
                    delivery_ready_at=at_noon(clamp_2026(spec.end_date - timedelta(days=1))) if stage in {"delivery_ready", "delivered"} else None,
                    delivered_at=at_noon(spec.end_date) if stage == "delivered" else None,
                    created_by_id=tl.id,
                    created_at=at_noon(clamp_2026(spec.start_date + timedelta(days=2))),
                    updated_at=at_noon(spec.end_date),
                )
                db.add(package)
                db.flush()
                summary.work_packages += 1
                db.add(OrthoDailyUpdate(
                    work_package_id=package.id,
                    update_date=clamp_2026(spec.start_date + timedelta(days=10 + package_no)),
                    work_type="Synthetic UAT production",
                    achieved_area=Decimal("1.5"),
                    progress_percent=Decimal("50.00") if stage == "production" else Decimal("100.00"),
                    files_completed=package_no * 2,
                    hours_spent=Decimal("6.50"),
                    status="on_track",
                    blockers=None,
                    remarks=f"[{TAG}] Daily progress sample",
                    updated_by_id=production.id,
                    created_at=at_noon(clamp_2026(spec.start_date + timedelta(days=10 + package_no))),
                ))

            if stage == "delivered":
                db.add(OrthoDelivery(
                    project_id=project.id,
                    delivered_by_id=pm.id,
                    package_count=2,
                    remarks=f"[{TAG}] Synthetic technical delivery",
                    delivered_at=at_noon(spec.end_date),
                ))

        if spec.archetype in {"ready_for_billing", "invoice_raised", "payment_pending", "partial", "overdue", "paid_open", "closed"}:
            basis_day = clamp_2026(spec.end_date + timedelta(days=1))
            basis = ProjectBillingBasis(
                project_id=project.id,
                entry_no=1,
                estimate_revision_id=revision.id,
                billing_type="fixed_price",
                cumulative_billable_quantity=None,
                quantity_unit=None,
                milestone_id=None,
                milestone_name="Final client acceptance",
                completion_percent=Decimal("100.00"),
                delivery_accepted=True,
                acceptance_reference=f"UAT26-ACC-{spec.ordinal:04d}",
                pm_remarks=f"[{TAG}] Synthetic billing readiness",
                billing_readiness_date=basis_day,
                confirmed_by_id=pm.id,
                confirmed_at=at_noon(basis_day),
            )
            db.add(basis)
            db.flush()

        if spec.archetype in {"invoice_raised", "payment_pending", "partial", "overdue", "paid_open", "closed"}:
            invoice_day = clamp_2026(spec.end_date + timedelta(days=3))
            due_day = clamp_2026(invoice_day + timedelta(days=30))
            invoice_status = {
                "invoice_raised": "INVOICE_RAISED",
                "payment_pending": "PAYMENT_PENDING",
                "partial": "PARTIALLY_PAID",
                "overdue": "PAYMENT_OVERDUE",
                "paid_open": "PAYMENT_RECEIVED",
                "closed": "INVOICE_CLOSED",
            }[spec.archetype]
            invoice = ProjectInvoice(
                project_id=project.id,
                invoice_number=f"{INVOICE_PREFIX}{spec.ordinal:04d}",
                status=invoice_status,
                invoice_date=invoice_day,
                due_date=due_day,
                amount=values["base_original"],
                tax_amount=values["tax_original"],
                currency=spec.currency,
                notes=f"[{TAG}] Finance-generated synthetic invoice",
                created_by_id=finance.id,
                raised_by_id=finance.id,
                raised_at=at_noon(invoice_day),
                closed_by_id=finance.id if spec.archetype == "closed" else None,
                closed_at=at_noon(spec.projected_payment_date) if spec.archetype == "closed" else None,
                tax_percent=Decimal("18.00"),
                fx_snapshot_id=None,
                fx_rate_to_inr=values["rate"],
                fx_rate_date=invoice_day,
                fx_rate_source="UAT_2026_FIXED_RATE",
                fx_rate_mode="MANUAL_OVERRIDE",
                base_inr=values["base_inr"],
                tax_inr=values["tax_inr"],
                total_inr=values["gross_inr"],
                fx_locked=True,
                payment_terms="30 days",
                po_wo_reference=f"UAT26-PO-{spec.ordinal:04d}",
                estimate_revision_id=revision.id,
                created_at=at_noon(invoice_day),
                updated_at=at_noon(spec.projected_payment_date if spec.archetype == "closed" else invoice_day),
            )
            db.add(invoice)
            db.flush()
            summary.invoices += 1

            fractions: list[Decimal] = []
            if spec.archetype == "partial":
                fractions = [Decimal("0.35"), Decimal("0.20")]
            elif spec.archetype == "overdue" and spec.ordinal % 2 == 0:
                fractions = [Decimal("0.20")]
            elif spec.archetype in {"paid_open", "closed"}:
                fractions = [Decimal("0.25"), Decimal("0.35"), Decimal("0.40")]

            paid_original = Decimal("0")
            paid_inr = Decimal("0")
            for payment_no, fraction in enumerate(fractions, start=1):
                if payment_no == len(fractions) and spec.archetype in {"paid_open", "closed"}:
                    amount_original = money(values["gross_original"] - paid_original)
                    amount_inr = money(values["gross_inr"] - paid_inr)
                else:
                    amount_original = money(values["gross_original"] * fraction)
                    amount_inr = money(values["gross_inr"] * fraction)
                payment_day = clamp_2026(invoice_day + timedelta(days=8 * payment_no))
                payment = ProjectInvoicePayment(
                    project_id=project.id,
                    invoice_id=invoice.id,
                    payment_reference=f"{PAYMENT_PREFIX}{spec.ordinal:04d}-{payment_no}",
                    payment_date=payment_day,
                    amount=amount_original,
                    payment_mode="bank_transfer",
                    comments=f"[{TAG}] Synthetic client payment {payment_no}",
                    recorded_by_id=finance.id,
                    created_at=at_noon(payment_day),
                    payment_currency=spec.currency,
                    fx_snapshot_id=None,
                    fx_rate_to_inr=values["rate"],
                    fx_rate_date=payment_day,
                    fx_rate_source="UAT_2026_FIXED_RATE",
                    fx_rate_mode="BANK_REALIZATION_RATE",
                    inr_equivalent=amount_inr,
                    invoice_inr_equivalent=amount_inr,
                    fx_gain_loss_inr=Decimal("0.00"),
                )
                db.add(payment)
                paid_original += amount_original
                paid_inr += amount_inr
                summary.payments += 1

            if spec.archetype == "closed":
                summary.closed_invoices += 1
                summary.revenue_inr += values["gross_inr"]

        if spec.archetype in {"feedback", "rework", "change_request"}:
            request_day = clamp_2026(spec.end_date + timedelta(days=2))
            request_code = f"{FEEDBACK_PREFIX}{spec.ordinal:04d}"
            awaiting_feedback = spec.archetype == "feedback"
            response_day = clamp_2026(request_day + timedelta(days=2))
            request = ProjectFeedbackRequest(
                project_id=project.id,
                request_code=request_code,
                cycle_number=1,
                recipient_email=client.client_email or f"client{spec.client_ordinal:03d}@example.com",
                token_hash=hashlib.sha256(f"{TAG}:{request_code}".encode("utf-8")).hexdigest(),
                message_thread_id=f"uat-2026-thread-{spec.ordinal:04d}",
                status="sent" if awaiting_feedback else "responded",
                message=f"[{TAG}] Please review synthetic delivery.",
                expires_at=at_noon(clamp_2026(request_day + timedelta(days=14))),
                sent_by_id=bd.id,
                sent_at=at_noon(request_day),
                reminder_count=0,
                responded_at=None if awaiting_feedback else at_noon(response_day),
                created_at=at_noon(request_day),
            )
            db.add(request)
            db.flush()
            summary.feedback_requests += 1
            response = None
            if not awaiting_feedback:
                response = ProjectFeedbackResponse(
                    project_id=project.id,
                    feedback_request_id=request.id,
                    response_type="correction_requested" if spec.archetype == "rework" else "additional_scope",
                    comments=f"[{TAG}] Synthetic client response",
                    correction_description=f"[{TAG}] Correct synthetic deliverable area" if spec.archetype == "rework" else None,
                    client_name=client.contact_person_name,
                    client_email=client.client_email,
                    external_message_id=f"uat-2026-msg-{spec.ordinal:04d}",
                    classification_status="confirmed",
                    classified_as="correction_rework" if spec.archetype == "rework" else "additional_scope",
                    classified_by_id=bd.id,
                    classified_at=at_noon(response_day),
                    responded_at=at_noon(response_day),
                    created_at=at_noon(response_day),
                )
                db.add(response)
                db.flush()

            if spec.archetype == "rework" and response is not None:
                cycle = ProjectReworkCycle(
                    project_id=project.id,
                    cycle_number=1,
                    source_feedback_response_id=response.id,
                    cycle_type="CORRECTION_REWORK",
                    status="REWORK_OPEN",
                    correction_scope=f"[{TAG}] Client correction rework",
                    project_manager_user_id=pm.id,
                    team_leader_user_id=tl.id,
                    opened_by_id=bd.id,
                    opened_at=at_noon(clamp_2026(request_day + timedelta(days=3))),
                    team_mode="reuse",
                    created_at=at_noon(clamp_2026(request_day + timedelta(days=3))),
                    updated_at=at_noon(clamp_2026(request_day + timedelta(days=3))),
                )
                db.add(cycle)
                summary.rework_cycles += 1
            elif spec.archetype == "change_request" and response is not None:
                change = ProjectChangeRequest(
                    project_id=project.id,
                    request_code=f"{CHANGE_PREFIX}{spec.ordinal:04d}",
                    source_feedback_response_id=response.id,
                    description=f"[{TAG}] Synthetic client additional scope",
                    status="pending",
                    commercial_impact=money(values["gross_original"] * Decimal("0.10")),
                    currency=spec.currency,
                    created_by_id=bd.id,
                    created_at=at_noon(clamp_2026(request_day + timedelta(days=3))),
                    updated_at=at_noon(clamp_2026(request_day + timedelta(days=3))),
                )
                db.add(change)
                summary.change_requests += 1

        # Project expenses every third project; vendor invoice every fifth.
        if spec.ordinal % 3 == 0 and progressed:
            expense_day = clamp_2026(spec.start_date + timedelta(days=12))
            reimbursed = spec.archetype in {"closed", "paid_open"}
            expense = ProjectExpense(
                expense_code=f"{EXPENSE_PREFIX}{spec.ordinal:04d}",
                project_id=project.id,
                employee_id=production.id,
                expense_date=expense_day,
                category="travel",
                purpose=f"[{TAG}] Synthetic field travel and project expense",
                amount=money(1200 + (spec.ordinal % 10) * 175),
                approved_amount=money(1200 + (spec.ordinal % 10) * 175),
                payment_source="EMPLOYEE_PAID",
                status="REIMBURSED" if reimbursed else "APPROVED",
                remarks=f"[{TAG}] Expense fixture",
                phase_key="ORIGINAL",
                finance_reviewer_id=finance.id,
                finance_reviewed_at=at_noon(clamp_2026(expense_day + timedelta(days=3))),
                finance_comments="Synthetic UAT approval",
                submitted_at=at_noon(clamp_2026(expense_day + timedelta(days=1))),
                reimbursed_at=at_noon(clamp_2026(expense_day + timedelta(days=5))) if reimbursed else None,
                reimbursement_reference=f"UAT26-REIM-{spec.ordinal:04d}" if reimbursed else None,
                created_at=at_noon(expense_day),
                updated_at=at_noon(clamp_2026(expense_day + timedelta(days=5))),
            )
            db.add(expense)
            summary.expenses += 1

        if spec.ordinal % 5 == 0 and progressed:
            vendor_day = clamp_2026(spec.start_date + timedelta(days=18))
            taxable = money(10000 + (spec.ordinal % 15) * 800)
            tax = money(taxable * Decimal("0.18"))
            paid_vendor = spec.archetype in {"closed", "paid_open"}
            db.add(ProjectVendorInvoice(
                project_id=project.id,
                vendor_name=f"UAT Vendor {(spec.ordinal % 8) + 1}",
                vendor_gstin=None,
                invoice_number=f"UAT26-VND-{spec.ordinal:04d}",
                invoice_date=vendor_day,
                due_date=clamp_2026(vendor_day + timedelta(days=30)),
                po_wo_reference=f"UAT26-VPO-{spec.ordinal:04d}",
                category="subcontract",
                description=f"[{TAG}] Synthetic subcontractor cost",
                hsn_sac=None,
                quantity=Decimal("1"),
                rate=taxable,
                currency_code="INR",
                taxable_amount=taxable,
                cgst=money(tax / 2),
                sgst=money(tax / 2),
                igst=Decimal("0.00"),
                other_tax=Decimal("0.00"),
                gross_amount=money(taxable + tax),
                fx_snapshot_id=None,
                fx_rate_to_inr=Decimal("1"),
                fx_rate_date=vendor_day,
                fx_rate_source="BASE_CURRENCY",
                fx_rate_mode="BASE_CURRENCY",
                taxable_inr=taxable,
                tax_inr=tax,
                gross_inr=money(taxable + tax),
                payment_status="PAID" if paid_vendor else "UNPAID",
                payment_source="COMPANY_PAID",
                status="ACTIVE",
                remarks=f"[{TAG}] Vendor invoice fixture",
                created_by_id=finance.id,
                created_at=at_noon(vendor_day),
                updated_at=at_noon(vendor_day),
            ))
            summary.vendor_invoices += 1

        if spec.ordinal % 4 == 0 and progressed:
            claim_day = clamp_2026(spec.start_date + timedelta(days=15))
            claim_amount = money(1800 + (spec.ordinal % 12) * 125)
            paid_claim = spec.archetype in {"closed", "paid_open"}
            claim = ExpenseClaim(
                claim_code=f"{CLAIM_PREFIX}{spec.ordinal:04d}",
                requester_id=production.id,
                project_id=project.id,
                claim_type="reimbursement",
                purpose_description=f"[{TAG}] Synthetic employee reimbursement",
                currency="INR",
                total_amount=claim_amount,
                settlement_status="not_required",
                status="paid" if paid_claim else "finance_approved",
                admin_decision_by_id=finance.id,
                admin_decision_at=at_noon(clamp_2026(claim_day + timedelta(days=1))),
                admin_comments="Synthetic UAT admin verification",
                finance_decision_by_id=finance.id,
                finance_decision_at=at_noon(clamp_2026(claim_day + timedelta(days=2))),
                finance_comments="Synthetic UAT Finance approval",
                finance_approved_amount=claim_amount,
                payment_reference=f"UAT26-CLMPAY-{spec.ordinal:04d}" if paid_claim else None,
                paid_amount=claim_amount if paid_claim else None,
                paid_at=at_noon(clamp_2026(claim_day + timedelta(days=4))) if paid_claim else None,
                submitted_at=at_noon(claim_day),
                created_at=at_noon(claim_day),
                updated_at=at_noon(clamp_2026(claim_day + timedelta(days=4))),
            )
            db.add(claim)
            db.flush()
            db.add(ExpenseClaimItem(
                claim_id=claim.id,
                category="travel",
                description=f"[{TAG}] Local travel reimbursement",
                amount=claim_amount,
                payment_mode="upi",
                expense_date=claim_day,
                created_at=at_noon(claim_day),
            ))
            if paid_claim:
                db.add(ExpenseClaimPayment(
                    claim_id=claim.id,
                    payment_reference=f"UAT26-CLMPAY-{spec.ordinal:04d}",
                    payment_mode="bank_transfer",
                    amount=claim_amount,
                    payment_date=clamp_2026(claim_day + timedelta(days=4)),
                    recorded_by_id=finance.id,
                    comments=f"[{TAG}] Synthetic claim payment",
                    created_at=at_noon(clamp_2026(claim_day + timedelta(days=4))),
                ))
            summary.expense_claims += 1

        if spec.ordinal % 5 == 0 and progressed:
            travel_day = clamp_2026(spec.start_date + timedelta(days=20))
            km = Decimal(str(18 + (spec.ordinal % 22)))
            allowance = money(km * Decimal("5.00"))
            travel_statuses = ("submitted", "admin_approved", "hr_approved", "finance_approved")
            travel_status = travel_statuses[(spec.ordinal // 5) % len(travel_statuses)]
            db.add(TravelKmClaim(
                claim_code=f"UAT26-KM-{spec.ordinal:04d}",
                requester_id=production.id,
                project_id=project.id,
                project_code_snapshot=project.project_code,
                project_name_snapshot=project.project_name,
                client_name_snapshot=client.client_name,
                travel_date=travel_day,
                purpose_description=f"[{TAG}] Synthetic project travel",
                start_km=Decimal("1000.00"),
                end_km=money(Decimal("1000.00") + km),
                odometer_km=money(km),
                start_latitude=12.9716,
                start_longitude=77.5946,
                start_accuracy_m=8.0,
                start_captured_at=at_noon(travel_day),
                end_latitude=12.9716 + 0.03,
                end_longitude=77.5946 + 0.03,
                end_accuracy_m=9.0,
                end_captured_at=at_noon(travel_day) + timedelta(hours=2),
                gps_straight_line_km=Decimal("4.200"),
                distance_variance_km=money(km - Decimal("4.2")),
                distance_variance_percent=Decimal("10.00"),
                rate_per_km=Decimal("5.00"),
                calculated_allowance=allowance,
                admin_eligible_km=money(km) if travel_status in {"admin_approved", "hr_approved", "finance_approved"} else None,
                hr_eligible_km=money(km) if travel_status in {"hr_approved", "finance_approved"} else None,
                final_eligible_km=money(km) if travel_status in {"hr_approved", "finance_approved"} else None,
                final_allowance=allowance if travel_status in {"hr_approved", "finance_approved"} else None,
                status=travel_status,
                admin_decision_by_id=admin_user.id if travel_status in {"admin_approved", "hr_approved", "finance_approved"} else None,
                admin_decision_at=at_noon(clamp_2026(travel_day + timedelta(days=1))) if travel_status in {"admin_approved", "hr_approved", "finance_approved"} else None,
                admin_comments=f"[{TAG}] Synthetic Admin verification" if travel_status in {"admin_approved", "hr_approved", "finance_approved"} else None,
                hr_decision_by_id=hr_user.id if travel_status in {"hr_approved", "finance_approved"} else None,
                hr_decision_at=at_noon(clamp_2026(travel_day + timedelta(days=2))) if travel_status in {"hr_approved", "finance_approved"} else None,
                hr_comments=f"[{TAG}] Synthetic HR verification" if travel_status in {"hr_approved", "finance_approved"} else None,
                finance_decision_by_id=finance.id if travel_status == "finance_approved" else None,
                finance_decision_at=at_noon(clamp_2026(travel_day + timedelta(days=3))) if travel_status == "finance_approved" else None,
                finance_comments=f"[{TAG}] Approved for monthly salary" if travel_status == "finance_approved" else None,
                payment_reference=None,
                payment_mode=None,
                paid_amount=None,
                paid_at=None,
                submitted_at=at_noon(travel_day),
                created_at=at_noon(travel_day),
                updated_at=at_noon(clamp_2026(travel_day + timedelta(days=3))),
            ))
            summary.travel_km_claims += 1

    # Monthly Revenue targets let Finance test target-vs-actual visualization across the full year.
    # These rows are tagged so production cleanup can remove only synthetic planning values.
    target_actor = finance_users[0]
    for month_no in range(1, 13):
        for dept_index, department_code in enumerate(SUPPORTED_DEPARTMENTS):
            target_value = money(650000 + month_no * 35000 + dept_index * 50000)
            db.add(FinanceRevenueTarget(
                month_start=date(2026, month_no, 1),
                department_code=department_code,
                target_amount_inr=target_value,
                source_tag=TAG,
                created_by_id=target_actor.id,
                updated_by_id=target_actor.id,
                created_at=at_noon(date(2026, month_no, 1)),
                updated_at=at_noon(date(2026, month_no, 1)),
            ))
            summary.revenue_targets += 1

    # Flush before exact revenue assertion; commit only if the whole fixture is internally consistent.
    db.flush()
    expected = money(target_realized_revenue_inr)
    actual = money(summary.revenue_inr)
    if actual != expected:
        raise RuntimeError(f"UAT revenue planning error: expected INR {expected}, generated INR {actual}")
    db.commit()
    return summary


def cleanup_year_2026(db: Session) -> dict[str, int]:
    """Delete only records attached to UAT26 project/client prefixes.

    The function intentionally removes known RESTRICT children first, then relies on the
    application's existing project/client cascades for workflow, commercial, billing and
    technical-operational children. If another module later creates a non-cascading FK to
    a UAT project, the transaction fails instead of broad-deleting unrelated data.
    """
    _ensure_not_production()
    project_ids = uat_project_ids(db)
    client_ids = uat_client_ids(db)
    if project_ids:
        # Explicit non-cascading / RESTRICT children.
        claim_ids = list(db.scalars(select(ExpenseClaim.id).where(ExpenseClaim.project_id.in_(project_ids))).all())
        if claim_ids:
            db.execute(delete(ExpenseClaimPayment).where(ExpenseClaimPayment.claim_id.in_(claim_ids)))
            db.execute(delete(ExpenseClaimItem).where(ExpenseClaimItem.claim_id.in_(claim_ids)))
            db.execute(delete(ExpenseClaim).where(ExpenseClaim.id.in_(claim_ids)))
        db.execute(delete(TravelKmClaim).where(TravelKmClaim.project_id.in_(project_ids)))
        db.execute(delete(ProjectExpense).where(ProjectExpense.project_id.in_(project_ids)))
        db.execute(delete(ProjectVendorInvoice).where(ProjectVendorInvoice.project_id.in_(project_ids)))
        db.execute(delete(FinanceProject).where(FinanceProject.id.in_(project_ids)))

    # Non-project inventory fixtures are also removed strictly by UAT26 prefixes.
    uat_asset_ids = list(db.scalars(select(Asset.id).where(Asset.asset_code.like("UAT26-AST-%"))).all())
    if uat_asset_ids:
        db.execute(delete(WorkRecord).where(WorkRecord.asset_id.in_(uat_asset_ids)))
        db.execute(delete(Asset).where(Asset.id.in_(uat_asset_ids)))
    uat_drone_ids = list(db.scalars(select(Drone.id).where(Drone.asset_code.like("UAT26-DRN-%"))).all())
    if uat_drone_ids:
        db.execute(delete(DroneLocation).where(DroneLocation.drone_id.in_(uat_drone_ids)))
        db.execute(delete(Drone).where(Drone.id.in_(uat_drone_ids)))

    db.execute(delete(FinanceRevenueTarget).where(FinanceRevenueTarget.source_tag == TAG))
    if client_ids:
        db.execute(delete(FinanceClient).where(FinanceClient.id.in_(client_ids)))
    db.commit()
    return {"projects": len(project_ids), "clients": len(client_ids)}


def validate_year_2026(db: Session) -> dict:
    project_ids = uat_project_ids(db)
    client_ids = uat_client_ids(db)
    if not project_ids:
        return {
            "tag": TAG,
            "clients": len(client_ids),
            "projects": 0,
            "departments": {},
            "workflow_statuses": {},
            "invoices": 0,
            "payments": 0,
            "closed_invoices": 0,
            "realized_revenue_inr": 0.0,
            "revenue_targets": int(db.scalar(select(func.count()).select_from(FinanceRevenueTarget).where(FinanceRevenueTarget.source_tag == TAG)) or 0),
        }

    departments = {
        code: int(db.scalar(
            select(func.count()).select_from(ProjectWorkflow).where(
                ProjectWorkflow.project_id.in_(project_ids),
                ProjectWorkflow.performing_department_code == code,
            )
        ) or 0)
        for code in SUPPORTED_DEPARTMENTS
    }
    status_rows = db.execute(
        select(ProjectWorkflow.status, func.count())
        .where(ProjectWorkflow.project_id.in_(project_ids))
        .group_by(ProjectWorkflow.status)
        .order_by(ProjectWorkflow.status)
    ).all()
    invoices = list(db.scalars(select(ProjectInvoice).where(ProjectInvoice.project_id.in_(project_ids))).all())
    invoice_ids = [row.id for row in invoices]
    payments = list(db.scalars(
        select(ProjectInvoicePayment).where(ProjectInvoicePayment.invoice_id.in_(invoice_ids))
    ).all()) if invoice_ids else []
    closed_ids = {row.id for row in invoices if row.status == "INVOICE_CLOSED"}
    revenue = sum(
        (money(row.inr_equivalent or 0) for row in payments if row.invoice_id in closed_ids),
        Decimal("0"),
    )

    return {
        "tag": TAG,
        "clients": len(client_ids),
        "projects": len(project_ids),
        "departments": departments,
        "workflow_statuses": {status: int(count) for status, count in status_rows},
        "invoices": len(invoices),
        "payments": len(payments),
        "closed_invoices": len(closed_ids),
        "realized_revenue_inr": float(money(revenue)),
        "expense_claims": int(db.scalar(select(func.count()).select_from(ExpenseClaim).where(ExpenseClaim.project_id.in_(project_ids))) or 0),
        "project_expenses": int(db.scalar(select(func.count()).select_from(ProjectExpense).where(ProjectExpense.project_id.in_(project_ids))) or 0),
        "vendor_invoices": int(db.scalar(select(func.count()).select_from(ProjectVendorInvoice).where(ProjectVendorInvoice.project_id.in_(project_ids))) or 0),
        "work_packages": int(db.scalar(select(func.count()).select_from(OrthoWorkPackage).where(OrthoWorkPackage.project_id.in_(project_ids))) or 0),
        "rework_cycles": int(db.scalar(select(func.count()).select_from(ProjectReworkCycle).where(ProjectReworkCycle.project_id.in_(project_ids))) or 0),
        "change_requests": int(db.scalar(select(func.count()).select_from(ProjectChangeRequest).where(ProjectChangeRequest.project_id.in_(project_ids))) or 0),
        "travel_km_claims": int(db.scalar(select(func.count()).select_from(TravelKmClaim).where(TravelKmClaim.project_id.in_(project_ids))) or 0),
        "uat_assets": int(db.scalar(select(func.count()).select_from(Asset).where(Asset.asset_code.like("UAT26-AST-%"))) or 0),
        "uat_work_records": int(db.scalar(select(func.count()).select_from(WorkRecord).where(WorkRecord.work_code.like("UAT26-WRK-%"))) or 0),
        "uat_drones": int(db.scalar(select(func.count()).select_from(Drone).where(Drone.asset_code.like("UAT26-DRN-%"))) or 0),
        "revenue_targets": int(db.scalar(select(func.count()).select_from(FinanceRevenueTarget).where(FinanceRevenueTarget.source_tag == TAG)) or 0),
    }
