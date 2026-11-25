
from __future__ import annotations

import asyncio
import logging
import re

from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO

from fastapi import (
    APIRouter, Depends, File, Form,
    HTTPException, Request, UploadFile,
)
from fastapi.responses import Response

from pydantic import BaseModel, Field

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer,
    LargeBinary, String, Text, UniqueConstraint,
    select, update, text,
)
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import Base, SessionLocal, get_db
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import record_audit
from app.modules.notifications.models import GlobalNotification
from app.modules.notifications.service import create_global_notification


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/organisation-policies",
    tags=["Organisation Policies"],
)

MAX_PDF_SIZE = 20 * 1024 * 1024
MAX_BATCH_SIZE = 100 * 1024 * 1024

DECLARATION = (
    "I confirm that I have read and acknowledged the current "
    "version of this organisation policy. I understand that "
    "I am responsible for following the applicable requirements "
    "and may contact HR if I require clarification."
)

PUBLISHED_EVENT = "organisation_policy.published"
REMINDER_EVENT = "organisation_policy.reminder"
INITIAL_EVENT = "organisation_policy.initial"

# Serializes policy changes, acknowledgement and reminder
# generation across PostgreSQL backend workers.
LOCK_ID = 684201935


# ============================================================
# DATABASE MODELS
# ============================================================

class OrganisationPolicy(Base):
    __tablename__ = "organisation_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seed_key: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True
    )
    current_version_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    archived_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class OrganisationPolicyVersion(Base):
    __tablename__ = "organisation_policy_versions"

    __table_args__ = (
        UniqueConstraint(
            "policy_id", "number",
            name="uq_org_policy_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    policy_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_policies.id"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)

    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))

    content: Mapped[str] = mapped_column(Text, default="")
    revision_notes: Mapped[str] = mapped_column(Text, default="")

    pdf_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    pdf_data: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )

    effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class OrganisationPolicyAcknowledgement(Base):
    __tablename__ = "organisation_policy_acknowledgements"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("organisation_policy_versions.id"),
        primary_key=True,
    )
    declaration: Mapped[str] = mapped_column(Text)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )


class OrganisationPolicyReminderState(Base):
    __tablename__ = "organisation_policy_reminder_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    last_sent_at: Mapped[datetime] = mapped_column(DateTime)


class OrganisationPolicySettings(Base):
    __tablename__ = "organisation_policy_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_hours: Mapped[int] = mapped_column(
        Integer, default=24
    )


Policy = OrganisationPolicy
Version = OrganisationPolicyVersion
Ack = OrganisationPolicyAcknowledgement
ReminderState = OrganisationPolicyReminderState
PolicySettings = OrganisationPolicySettings


# ============================================================
# EXACT ROLE SECURITY
# ============================================================

def policy_actor(
    auth: CurrentAuth = Depends(get_current_auth),
) -> User:
    user = auth.user

    if (
        user.role not in {"hr", "employee"}
        or auth.effective_role != user.role
        or not user.is_active
        or user.account_status != "active"
    ):
        raise HTTPException(
            status_code=403,
            detail="Organisation Policies access denied.",
        )

    return user


def hr_only(
    user: User = Depends(policy_actor),
) -> User:
    if user.role != "hr":
        raise HTTPException(
            status_code=403,
            detail="Only HR can manage organisation policies.",
        )
    return user


def employee_only(
    user: User = Depends(policy_actor),
) -> User:
    if user.role != "employee":
        raise HTTPException(
            status_code=403,
            detail="Only employees can acknowledge policies.",
        )
    return user


def acquire_lock(db: Session):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": LOCK_ID},
        )


def active_employees(db: Session):
    return db.scalars(
        select(User).where(
            User.role == "employee",
            User.is_active.is_(True),
            User.account_status == "active",
        ).order_by(User.full_name)
    ).all()


def audit(db, request, user, action, target_id, details=None):
    record_audit(
        db,
        request=request,
        user=user,
        event_type=f"organisation_policy_{action}",
        result="success",
        module="organisation_policies",
        target_type="organisation_policy",
        target_id=str(target_id),
        details=details or {},
    )


# ============================================================
# POLICY AND DOCUMENT HELPERS
# ============================================================

def stamp(value):
    if value is None:
        return None
    return value.isoformat() + ("Z" if value.tzinfo is None else "")


def get_policy(db: Session, policy_id: int):
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(404, "Policy not found.")
    return policy


def get_current(db: Session, policy):
    if policy.current_version_id is None:
        return None
    return db.scalar(
        select(Version).where(
            Version.id == policy.current_version_id,
            Version.policy_id == policy.id,
            Version.published_at.is_not(None),
        )
    )


def get_draft(db: Session, policy):
    return db.scalar(
        select(Version).where(
            Version.policy_id == policy.id,
            Version.published_at.is_(None),
        ).order_by(Version.number.desc()).limit(1)
    )


def ensure_editable(policy):
    if policy.archived_at is not None:
        raise HTTPException(409, "Archived policies cannot be edited.")


def version_data(version):
    if version is None:
        return None

    return {
        "id": version.id,
        "number": version.number,
        "revision": version.revision,
        "title": version.title,
        "category": version.category,
        "content": version.content,
        "revision_notes": version.revision_notes,
        "has_pdf": bool(version.pdf_name),
        "pdf_name": version.pdf_name,
        "effective_date": (
            version.effective_date.isoformat()
            if version.effective_date else None
        ),
        "published_at": stamp(version.published_at),
    }


def current_versions(db: Session):
    return db.scalars(
        select(Version)
        .join(
            Policy,
            Policy.current_version_id == Version.id,
        )
        .where(
            Policy.archived_at.is_(None),
            Version.policy_id == Policy.id,
            Version.published_at.is_not(None),
        )
        .order_by(Version.title)
    ).all()


def policy_data(db, policy, user):
    current = get_current(db, policy)

    acknowledged_at = None

    if user.role == "employee":
        if policy.archived_at or current is None:
            raise HTTPException(404, "Policy not found.")

        ack = db.get(Ack, (user.id, current.id))
        if ack:
            acknowledged_at = stamp(ack.acknowledged_at)

    return {
        "id": policy.id,
        "archived": policy.archived_at is not None,
        "published": version_data(current),
        "draft": (
            version_data(get_draft(db, policy))
            if user.role == "hr" else None
        ),
        "acknowledged_at": acknowledged_at,
    }


def safe_filename(name):
    name = (name or "policy.pdf").replace("\\", "/")
    return name.rsplit("/", 1)[-1][:255]


def read_pdf(upload: UploadFile):
    name = safe_filename(upload.filename)

    if not name.lower().endswith(".pdf"):
        raise HTTPException(422, "Only PDF documents are allowed.")

    raw = upload.file.read(MAX_PDF_SIZE + 1)

    if len(raw) > MAX_PDF_SIZE:
        raise HTTPException(413, "Maximum PDF size is 20 MB.")

    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF document.")

    return name, raw


@dataclass
class DraftInput:
    title: str
    category: str
    content: str
    effective_date: date | None
    revision_notes: str
    pdf_name: str | None
    pdf_data: bytes | None
    remove_pdf: bool
    expected_version_id: int | None
    expected_revision: int | None


def draft_input(
    title: str = Form(..., min_length=1, max_length=200),
    category: str = Form(..., min_length=1, max_length=100),
    content: str = Form("", max_length=100000),
    effective_date: str = Form(""),
    revision_notes: str = Form("", max_length=2000),
    pdf: UploadFile | None = File(None),
    remove_pdf: bool = Form(False),
    expected_version_id: int | None = Form(None),
    expected_revision: int | None = Form(None),
):
    title = title.strip()
    category = category.strip()

    if not title or not category:
        raise HTTPException(422, "Title and category are required.")

    try:
        effective = (
            date.fromisoformat(effective_date)
            if effective_date else None
        )
    except ValueError:
        raise HTTPException(422, "Invalid effective date.")

    name, raw = read_pdf(pdf) if pdf else (None, None)

    return DraftInput(
        title, category, content.strip(), effective,
        revision_notes.strip(), name, raw, remove_pdf,
        expected_version_id, expected_revision,
    )


def write_draft(db, policy, data, user):
    ensure_editable(policy)

    draft = get_draft(db, policy)
    current = get_current(db, policy)
    base = draft or current

    if base is not None:
        if (
            data.expected_version_id != base.id
            or data.expected_revision != base.revision
        ):
            raise HTTPException(
                409, "Policy was changed. Refresh and reopen it."
            )

    name = base.pdf_name if base else None
    raw = base.pdf_data if base else None

    if data.remove_pdf:
        name, raw = None, None

    if data.pdf_data is not None:
        name, raw = data.pdf_name, data.pdf_data

    if not data.content and raw is None:
        raise HTTPException(
            422, "Enter policy text or upload a PDF."
        )

    if draft is None:
        draft = Version(
            policy_id=policy.id,
            number=(current.number + 1) if current else 1,
            revision=1,
            created_by=user.id,
        )
        db.add(draft)
    else:
        draft.revision += 1

    draft.title = data.title
    draft.category = data.category
    draft.content = data.content
    draft.effective_date = data.effective_date
    draft.revision_notes = data.revision_notes
    draft.pdf_name = name
    draft.pdf_data = raw

    db.flush()
    return draft


# ============================================================
# NOTIFICATIONS AND REMINDERS
# ============================================================

def reminder_hours(db):
    row = db.get(PolicySettings, 1)
    return row.reminder_hours if row else 24


def publication_key(version_id):
    return f"organisation-policy:version:{version_id}"


def retire_notifications(
    db,
    events,
    user_id=None,
    dedupe_key=None,
):
    conditions = [
        GlobalNotification.event_type.in_(events),
        GlobalNotification.is_read.is_(False),
    ]

    if user_id is not None:
        conditions.append(
            GlobalNotification.recipient_user_id == user_id
        )

    if dedupe_key is not None:
        conditions.append(
            GlobalNotification.dedupe_key == dedupe_key
        )

    db.execute(
        update(GlobalNotification)
        .where(*conditions)
        .values(is_read=True, read_at=utc_now())
    )


def set_reminder_clock(db, user_id, now):
    row = db.get(ReminderState, user_id)

    if row:
        row.last_sent_at = now
    else:
        db.add(
            ReminderState(
                user_id=user_id,
                last_sent_at=now,
            )
        )


def pending_versions(db, user_id):
    versions = current_versions(db)

    acknowledged = set(
        db.scalars(
            select(Ack.version_id).where(Ack.user_id == user_id)
        ).all()
    )

    return [v for v in versions if v.id not in acknowledged]


def clear_completed_reminders(db, user_id):
    if not pending_versions(db, user_id):
        retire_notifications(
            db,
            [REMINDER_EVENT, INITIAL_EVENT],
            user_id=user_id,
        )


def publish_version(db, policy, version, user, notify=True):
    ensure_editable(policy)

    if version.published_at is not None:
        raise HTTPException(409, "This version is already published.")

    previous_id = policy.current_version_id
    now = utc_now()

    version.published_at = now
    version.published_by = user.id
    policy.current_version_id = version.id

    db.flush()

    if previous_id:
        retire_notifications(
            db,
            [PUBLISHED_EVENT],
            dedupe_key=publication_key(previous_id),
        )

    if notify:
        create_global_notification(
            db,
            event_type=PUBLISHED_EVENT,
            title="Organisation Policy Published",
            message=(
                f"HR has published {version.title}, "
                f"version {version.number}. Please read and acknowledge it."
            ),
            category="system",
            target_url=f"/organisation-policies?policy={policy.id}",
            recipient_roles=["employee"],
            dedupe_key=publication_key(version.id),
        )

        for employee in active_employees(db):
            set_reminder_clock(db, employee.id, now)


def run_policy_reminders():
    """
    Runs on the backend independently of whether employees
    are logged in. Every run checks the current acknowledgement
    records before creating any reminder.
    """
    with SessionLocal() as db:
        acquire_lock(db)

        now = utc_now()
        interval = timedelta(hours=reminder_hours(db))

        versions = current_versions(db)
        version_ids = {v.id for v in versions}

        acknowledged = set()

        if version_ids:
            acknowledged = set(
                db.execute(
                    select(Ack.user_id, Ack.version_id)
                    .where(Ack.version_id.in_(version_ids))
                ).all()
            )

        for employee in active_employees(db):
            pending_count = sum(
                (employee.id, v_id) not in acknowledged
                for v_id in version_ids
            )

            if pending_count == 0:
                retire_notifications(
                    db,
                    [REMINDER_EVENT, INITIAL_EVENT],
                    user_id=employee.id,
                )
                continue

            state = db.get(ReminderState, employee.id)

            if state and now < state.last_sent_at + interval:
                continue

            # Retire previous unread reminder to avoid spam.
            retire_notifications(
                db,
                [REMINDER_EVENT],
                user_id=employee.id,
            )

            create_global_notification(
                db,
                event_type=REMINDER_EVENT,
                title="Policy Acknowledgement Pending",
                message=(
                    "You have organisation policies awaiting "
                    "acknowledgement. Please open Organisation Policies "
                    "and review all pending documents."
                ),
                category="system",
                target_url="/organisation-policies",
                recipient_user_ids=[employee.id],
                dedupe_key=(
                    "organisation-policy:reminder:"
                    + now.strftime("%Y%m%d%H%M%S")
                ),
                is_reminder=True,
            )

            set_reminder_clock(db, employee.id, now)

        db.commit()


async def policy_reminder_watcher():
    while True:
        try:
            await asyncio.to_thread(run_policy_reminders)
        except Exception:
            logger.exception("Organisation policy reminder check failed.")

        await asyncio.sleep(60)


def with_policy_lifespan(original_lifespan):
    """
    Extend the existing ERP lifespan without replacing its
    startup, shutdown or background jobs.
    """
    @asynccontextmanager
    async def combined_lifespan(app):
        async with original_lifespan(app) as state:
            task = asyncio.create_task(policy_reminder_watcher())

            try:
                yield state
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return combined_lifespan


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class PublishRequest(BaseModel):
    version_id: int
    revision: int


class AcknowledgeRequest(BaseModel):
    version_id: int
    confirmed: bool


class ReminderSettingsRequest(BaseModel):
    reminder_hours: int = Field(ge=1, le=168)


# ============================================================
# DEFAULT POLICIES: ORIGINAL UPLOADED DOCUMENTS
# ============================================================

DEFAULT_POLICIES = [
    (
        "mobile-usage",
        "NakshaTech-Mobileusage.pdf",
        "Mobile Phone & Workplace Discipline Policy",
        "Workplace Discipline",
    ),
    (
        "pip",
        "NakshaTechPIPpolicy.pdf",
        "Performance Improvement Plan (PIP) Policy",
        "Performance Management",
    ),
    (
        "it-asset",
        "IT System policy (1).pdf",
        "Laptop & IT Asset Handover Policy",
        "IT & Security",
    ),
    (
        "off-day-meal",
        "Non-Working Day Meal Policy.pdf",
        "Off-Day Working & Weekend Food Allowance Policy",
        "Employee Benefits",
    ),
    (
        "passport",
        "NakshaTech-Passport Facilitation Benefit.pdf",
        "Global Readiness Program - Passport Facilitation Benefit",
        "Employee Benefits",
    ),
    (
        "working-hours",
        "NakshaTech_Working_Hours_Attendance_Policy.pdf",
        "Working Hours & Attendance Policy",
        "Attendance",
    ),
    (
        "misconduct",
        "NakshaTechMisconductPolicy (1).pdf",
        "Misconduct Policy",
        "Workplace Discipline",
    ),
    (
        "comp-off",
        "NakshaTechCompensatory Off (2).pdf",
        "Compensatory Off Policy",
        "Leave Management",
    ),
    (
        "leave",
        "Nakshatechleavepolicy.pdf",
        "Leave Policy",
        "Leave Management",
    ),
    (
        "regularization",
        "NakshaTechRegularization (1).pdf",
        "Attendance Regularization Policy",
        "Attendance",
    ),
    (
        "holiday",
        "NakshaTechHolidayPolicy.pdf",
        "Holiday Policy",
        "Holidays",
    ),
]


def normalized_filename(name):
    name = safe_filename(name).casefold()
    return re.sub(r"\s*\(\d+\)(?=\.pdf$)", "", name)


@router.post("/defaults/import")
def import_default_policies(
    request: Request,
    documents: list[UploadFile] = File(...),
    confirmed: bool = Form(False),
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(
            422, "Confirm the initial publication of the policies."
        )

    expected = {
        normalized_filename(item[1]): item
        for item in DEFAULT_POLICIES
    }

    if len(documents) != len(expected):
        raise HTTPException(422, "Select all 11 original PDFs.")

    prepared = {}
    total_size = 0

    # Validate all documents before inserting any records.
    for document in documents:
        name, raw = read_pdf(document)
        key = normalized_filename(name)

        if key not in expected or key in prepared:
            raise HTTPException(
                422, f"Unexpected or duplicate PDF: {name}"
            )

        total_size += len(raw)

        if total_size > MAX_BATCH_SIZE:
            raise HTTPException(413, "Maximum batch size is 100 MB.")

        prepared[key] = (name, raw)

    acquire_lock(db)

    created = []
    skipped = []

    for key, item in expected.items():
        seed_key, _, title, category = item

        existing = db.scalar(
            select(Policy).where(Policy.seed_key == seed_key)
        )

        # Includes archived policies. Reimport must never
        # recreate, overwrite or republish a deleted policy.
        if existing:
            skipped.append(title)
            continue

        name, raw = prepared[key]

        policy = Policy(
            seed_key=seed_key,
            created_by=user.id,
        )
        db.add(policy)
        db.flush()

        version = Version(
            policy_id=policy.id,
            number=1,
            revision=1,
            title=title,
            category=category,
            content="",
            pdf_name=name,
            pdf_data=raw,
            effective_date=(
                date(2025, 1, 1)
                if seed_key == "comp-off" else None
            ),
            revision_notes="Initial official policy document.",
            created_by=user.id,
        )

        db.add(version)
        db.flush()

        publish_version(
            db, policy, version, user, notify=False
        )

        created.append(version.id)

    if created:
        create_global_notification(
            db,
            event_type=INITIAL_EVENT,
            title="Organisation Policies Published",
            message=(
                "HR has published official company policies. "
                "Please review and acknowledge the pending policies."
            ),
            category="system",
            target_url="/organisation-policies",
            recipient_roles=["employee"],
            dedupe_key=(
                "organisation-policy:initial:"
                + "-".join(str(v) for v in created)
            ),
        )

        now = utc_now()

        for employee in active_employees(db):
            set_reminder_clock(db, employee.id, now)

        audit(
            db, request, user, "import_defaults", "initial",
            {"created_count": len(created)},
        )

    db.commit()

    return {
        "created": len(created),
        "skipped": len(skipped),
    }


# ============================================================
# LIST, COMPLIANCE, SETTINGS AND HISTORY
# ============================================================

@router.get("")
def list_policies(
    user: User = Depends(policy_actor),
    db: Session = Depends(get_db),
):
    query = select(Policy).order_by(Policy.id)

    if user.role == "employee":
        query = query.where(
            Policy.archived_at.is_(None),
            Policy.current_version_id.is_not(None),
        )

    return {
        "policies": [
            policy_data(db, policy, user)
            for policy in db.scalars(query).all()
        ],
        "reminder_hours": reminder_hours(db),
        "declaration": DECLARATION,
    }


def compliance_rows(db):
    now = utc_now()
    versions = current_versions(db)
    ids = [version.id for version in versions]

    acknowledgements = {}

    if ids:
        acknowledgements = {
            (a.user_id, a.version_id): a
            for a in db.scalars(
                select(Ack).where(Ack.version_id.in_(ids))
            ).all()
        }

    employees = active_employees(db)
    rows = []

    for employee in employees:
        for version in versions:
            ack = acknowledgements.get((employee.id, version.id))

            start = max(
                version.published_at,
                employee.created_at,
            )

            pending_days = max(0, (now - start).days)

            rows.append({
                "user_id": employee.id,
                "employee_id": employee.employee_id or "",
                "employee_name": employee.full_name,
                "department": employee.department or "Not assigned",
                "policy_id": version.policy_id,
                "policy_title": version.title,
                "version": version.number,
                "acknowledged_at": (
                    stamp(ack.acknowledged_at) if ack else None
                ),
                "pending_days": 0 if ack else pending_days,
                "overdue": not ack and pending_days >= 7,
            })

    return rows


@router.get("/compliance")
def compliance(
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    return {"rows": compliance_rows(db)}


@router.get("/compliance/export")
def export_compliance(
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        raise HTTPException(503, "Excel export dependency is missing.")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Policy Compliance"

    sheet.append([
        "Employee ID", "Employee Name", "Department",
        "Policy", "Version", "Status",
        "Acknowledged At (UTC)", "Pending Days", "Overdue",
    ])

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="123D60")

    for row in compliance_rows(db):
        sheet.append([
            row["employee_id"],
            row["employee_name"],
            row["department"],
            row["policy_title"],
            row["version"],
            "Acknowledged" if row["acknowledged_at"] else "Pending",
            row["acknowledged_at"] or "",
            row["pending_days"],
            "Yes" if row["overdue"] else "No",
        ])

        # Prevent spreadsheet formula injection.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    for column, width in {
        "A": 18, "B": 30, "C": 22, "D": 65,
        "E": 12, "F": 18, "G": 32, "H": 18, "I": 14,
    }.items():
        sheet.column_dimensions[column].width = width

    stream = BytesIO()
    workbook.save(stream)

    return Response(
        content=stream.getvalue(),
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition":
                'attachment; filename="organisation_policy_compliance.xlsx"',
            "Cache-Control": "private, no-store",
        },
    )


@router.put("/settings")
def update_settings(
    payload: ReminderSettingsRequest,
    request: Request,
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    acquire_lock(db)

    row = db.get(PolicySettings, 1)

    if row is None:
        row = PolicySettings(id=1)
        db.add(row)

    row.reminder_hours = payload.reminder_hours

    audit(
        db, request, user, "settings", "reminders",
        {"reminder_hours": payload.reminder_hours},
    )

    db.commit()

    return {"reminder_hours": payload.reminder_hours}


@router.get("/my-acknowledgements")
def my_acknowledgements(
    user: User = Depends(employee_only),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Ack, Version)
        .join(Version, Version.id == Ack.version_id)
        .where(Ack.user_id == user.id)
        .order_by(Ack.acknowledged_at.desc())
    ).all()

    return {
        "records": [
            {
                "title": version.title,
                "version": version.number,
                "acknowledged_at": stamp(ack.acknowledged_at),
            }
            for ack, version in rows
        ]
    }


# ============================================================
# HR POLICY MANAGEMENT
# ============================================================

@router.post("", status_code=201)
def create_policy(
    request: Request,
    user: User = Depends(hr_only),
    data: DraftInput = Depends(draft_input),
    db: Session = Depends(get_db),
):
    acquire_lock(db)

    policy = Policy(created_by=user.id)
    db.add(policy)
    db.flush()

    draft = write_draft(db, policy, data, user)

    audit(
        db, request, user, "create_draft", policy.id,
        {"version_id": draft.id},
    )

    result = policy_data(db, policy, user)
    db.commit()
    return result


@router.patch("/{policy_id}/draft")
def edit_policy(
    policy_id: int,
    request: Request,
    user: User = Depends(hr_only),
    data: DraftInput = Depends(draft_input),
    db: Session = Depends(get_db),
):
    acquire_lock(db)

    policy = get_policy(db, policy_id)
    draft = write_draft(db, policy, data, user)

    audit(
        db, request, user, "edit_draft", policy.id,
        {"version_id": draft.id},
    )

    result = policy_data(db, policy, user)
    db.commit()
    return result


@router.post("/{policy_id}/publish")
def publish_policy(
    policy_id: int,
    payload: PublishRequest,
    request: Request,
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    acquire_lock(db)

    policy = get_policy(db, policy_id)
    draft = get_draft(db, policy)

    if (
        draft is None
        or draft.id != payload.version_id
        or draft.revision != payload.revision
    ):
        raise HTTPException(
            409, "Draft has changed. Review the latest draft."
        )

    publish_version(db, policy, draft, user)

    audit(
        db, request, user, "publish", policy.id,
        {"version_id": draft.id, "version": draft.number},
    )

    result = policy_data(db, policy, user)
    db.commit()
    return result


@router.post("/{policy_id}/archive")
def archive_policy(
    policy_id: int,
    request: Request,
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    acquire_lock(db)

    policy = get_policy(db, policy_id)

    if policy.archived_at is None:
        policy.archived_at = utc_now()
        policy.archived_by = user.id

        ids = db.scalars(
            select(Version.id).where(
                Version.policy_id == policy.id
            )
        ).all()

        for version_id in ids:
            retire_notifications(
                db,
                [PUBLISHED_EVENT],
                dedupe_key=publication_key(version_id),
            )

        db.flush()

        for employee in active_employees(db):
            clear_completed_reminders(db, employee.id)

        audit(db, request, user, "archive", policy.id)

    db.commit()

    return {"archived": True}


@router.get("/{policy_id}/versions")
def version_history(
    policy_id: int,
    user: User = Depends(hr_only),
    db: Session = Depends(get_db),
):
    get_policy(db, policy_id)

    versions = db.scalars(
        select(Version)
        .where(Version.policy_id == policy_id)
        .order_by(Version.number.desc())
    ).all()

    return {"versions": [version_data(v) for v in versions]}


# ============================================================
# PROTECTED DOCUMENT VIEWING
# ============================================================

@router.get("/{policy_id}/versions/{version_id}/document")
def view_document(
    policy_id: int,
    version_id: int,
    user: User = Depends(policy_actor),
    db: Session = Depends(get_db),
):
    policy = get_policy(db, policy_id)

    if user.role == "employee":
        if (
            policy.archived_at is not None
            or policy.current_version_id != version_id
        ):
            raise HTTPException(404, "Document not found.")

    version = db.scalar(
        select(Version).where(
            Version.id == version_id,
            Version.policy_id == policy_id,
        )
    )

    if version is None or version.pdf_data is None:
        raise HTTPException(404, "PDF document not found.")

    if user.role == "employee" and version.published_at is None:
        raise HTTPException(404, "Document not found.")

    return Response(
        content=version.pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="policy-{policy_id}-v{version.number}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ============================================================
# EMPLOYEE ACKNOWLEDGEMENT
# ============================================================

@router.post("/{policy_id}/acknowledge")
def acknowledge_policy(
    policy_id: int,
    payload: AcknowledgeRequest,
    request: Request,
    user: User = Depends(employee_only),
    db: Session = Depends(get_db),
):
    if payload.confirmed is not True:
        raise HTTPException(422, "Confirm the acknowledgement checkbox.")

    acquire_lock(db)

    policy = get_policy(db, policy_id)
    current = get_current(db, policy)

    if (
        policy.archived_at is not None
        or current is None
        or current.id != payload.version_id
    ):
        raise HTTPException(
            409, "Policy version has changed. Read the latest version."
        )

    ack = db.get(Ack, (user.id, current.id))

    if ack is None:
        ack = Ack(
            user_id=user.id,
            version_id=current.id,
            declaration=DECLARATION,
            acknowledged_at=utc_now(),
        )
        db.add(ack)
        db.flush()

        audit(
            db, request, user, "acknowledge", policy.id,
            {"version_id": current.id},
        )

    retire_notifications(
        db,
        [PUBLISHED_EVENT],
        user_id=user.id,
        dedupe_key=publication_key(current.id),
    )

    # Once all current policies are acknowledged, retire
    # the outstanding grouped policy reminders as well.
    clear_completed_reminders(db, user.id)

    result = {"acknowledged_at": stamp(ack.acknowledged_at)}

    db.commit()
    return result


@router.get("/{policy_id}")
def policy_detail(
    policy_id: int,
    user: User = Depends(policy_actor),
    db: Session = Depends(get_db),
):
    return policy_data(db, get_policy(db, policy_id), user)
