
from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User, utc_now

from app.modules.bd_ai.schemas import (
    BDAIContext,
    BDAIAnalysis,
    BDAIAnswer,
)

from app.modules.bd_ai.submission_models import (
    BDAISubmission,
    BDAISubmissionRevision,
    BDAISubmissionEvent,
)

from app.modules.notifications.service import (
    create_global_notification,
    resolve_notifications,
)


router = APIRouter(tags=["BD AI Submissions"])


# --------------------------------------------------
# Request validation
# --------------------------------------------------

class SubmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: BDAIContext
    analysis: BDAIAnalysis

    answers: list[BDAIAnswer] = Field(
        default_factory=list,
        max_length=100,
    )

    human_verified: StrictBool
    pending_acknowledged: StrictBool = False

    revision_note: str = Field(
        default="",
        max_length=2000,
    )

    @model_validator(mode="after")
    def validate_submission(self):
        context = self.context

        if not context.client_name.strip():
            raise ValueError("Client name is required")

        if not context.project_reference.strip():
            raise ValueError("Project reference is required")

        if not context.department.strip():
            raise ValueError("Department is required")

        if len(context.requirements.strip()) < 20:
            raise ValueError("Client requirements are incomplete")

        if not self.analysis.project_objective.strip():
            raise ValueError("Project objective is required")

        if not self.analysis.scope_of_work.strip():
            raise ValueError("Scope of work is required")

        if any(
            question.strip()
            for question in self.analysis.clarification_questions
        ):
            raise ValueError(
                "Complete the pending clarification questions"
            )

        if not self.human_verified:
            raise ValueError(
                "Human verification is required"
            )

        if (
            any(
                item.strip()
                for item in self.analysis.missing_information
            )
            and not self.pending_acknowledged
        ):
            raise ValueError(
                "Acknowledge remaining unconfirmed information"
            )

        for value in self.analysis.model_dump().values():
            if isinstance(value, str) and len(value) > 10000:
                raise ValueError("Analysis text is too long")

            if isinstance(value, list):
                if len(value) > 100:
                    raise ValueError("Too many analysis items")

                if any(len(item) > 4000 for item in value):
                    raise ValueError("Analysis item is too long")

        if len(
            self.model_dump_json().encode("utf-8")
        ) > 200000:
            raise ValueError("Submission is too large")

        return self


class ResubmissionInput(SubmissionInput):
    expected_revision: int = Field(ge=1)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    note: str = Field(default="", max_length=2000)


# --------------------------------------------------
# Authorization
# --------------------------------------------------

def _authorized_user(
    auth: CurrentAuth = Depends(get_current_auth),
) -> User:
    user = auth.user

    if (
        not user.is_active
        or user.account_status != "active"
        or auth.effective_role != user.role
        or user.role not in {"bd", "bd_employee"}
    ):
        raise HTTPException(
            403,
            "BD AI submission access denied",
        )

    return user


def _employee(
    user: User = Depends(_authorized_user),
) -> User:
    if user.role != "bd_employee":
        raise HTTPException(
            403,
            "BD Employee access required",
        )

    return user


def _manager(
    user: User = Depends(_authorized_user),
) -> User:
    if user.role != "bd":
        raise HTTPException(
            403,
            "BD Manager access required",
        )

    return user


def _resolve_manager(db: Session, employee: User) -> User:
    # Single-manager routing for the current BD environment.
    # If multiple managers exist, fail closed until an
    # authoritative employee-to-manager mapping is defined.

    managers = db.scalars(
        select(User).where(
            User.role == "bd",
            User.is_active.is_(True),
            User.account_status == "active",
            User.id != employee.id,
        ).order_by(User.id).limit(2)
    ).all()

    if len(managers) != 1:
        raise HTTPException(
            409,
            "A unique active BD Manager could not be "
            "identified. Contact the ERP administrator.",
        )

    return managers[0]


# --------------------------------------------------
# Snapshot and serialization helpers
# --------------------------------------------------

def _snapshot(payload: SubmissionInput) -> dict:
    data = payload.model_dump(
        mode="json",
        exclude={"expected_revision"},
    )

    for key in (
        "client_name",
        "project_reference",
        "department",
        "requirements",
    ):
        data["context"][key] = (
            data["context"][key].strip()
        )

    return data


def _fingerprint(snapshot: dict) -> str:
    canonical = json.dumps(
        snapshot,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _reference(row: BDAISubmission) -> str:
    return f"BDAI-{row.id:06d}"


def _revision(
    db: Session,
    row: BDAISubmission,
    number: int | None = None,
) -> BDAISubmissionRevision:
    result = db.scalar(
        select(BDAISubmissionRevision).where(
            BDAISubmissionRevision.submission_id == row.id,
            BDAISubmissionRevision.revision_number
            == (
                number
                if number is not None
                else row.current_revision
            ),
        )
    )

    if result is None:
        raise HTTPException(404, "Revision not found")

    return result


def _summary(
    row: BDAISubmission,
    revision: BDAISubmissionRevision,
) -> dict:
    context = revision.snapshot["context"]

    return {
        "id": row.id,
        "reference": _reference(row),
        "employee_user_id": row.employee_user_id,
        "employee_name": row.employee_name,
        "employee_code": row.employee_code,
        "manager_user_id": row.manager_user_id,
        "client_name": context["client_name"],
        "project_reference": context["project_reference"],
        "department": context["department"],
        "status": row.status,
        "revision_number": row.current_revision,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "submitted_at": revision.submitted_at,
    }


def _owned_submission(
    db: Session,
    submission_id: int,
    user: User,
    *,
    lock: bool = False,
) -> BDAISubmission:
    owner_column = (
        BDAISubmission.employee_user_id
        if user.role == "bd_employee"
        else BDAISubmission.manager_user_id
    )

    stmt = select(BDAISubmission).where(
        BDAISubmission.id == submission_id,
        owner_column == user.id,
    )

    if lock:
        stmt = stmt.with_for_update()

    row = db.scalar(stmt)

    if row is None:
        raise HTTPException(
            404,
            "Technical requirement submission not found",
        )

    return row


def _add_event(
    db: Session,
    revision: BDAISubmissionRevision,
    actor: User,
    action: str,
    note: str | None = None,
) -> None:
    db.add(
        BDAISubmissionEvent(
            revision_id=revision.id,
            actor_user_id=actor.id,
            actor_name=actor.full_name,
            action=action,
            note=note,
        )
    )


# --------------------------------------------------
# Notifications
# --------------------------------------------------

def _notification_key(
    row: BDAISubmission,
    revision_number: int,
) -> str:
    return (
        f"bd-ai:{row.id}:"
        f"revision:{revision_number}:review"
    )


def _notify_manager(
    db: Session,
    row: BDAISubmission,
) -> None:
    created = create_global_notification(
        db,
        event_type="bd_ai.submitted",
        category="approval",
        title="Technical Requirement Review",
        message=(
            f"BD AI submission {_reference(row)} "
            "requires your review."
        ),
        target_url="/bd-ai",
        recipient_user_ids=[row.manager_user_id],
        dedupe_key=_notification_key(
            row,
            row.current_revision,
        ),
        requires_action=True,
        severity="info",
        metadata={
            "submission_id": row.id,
            "revision": row.current_revision,
        },
    )

    if not created:
        raise HTTPException(
            409,
            "Manager notification could not be created. "
            "The submission was not completed.",
        )


def _notify_employee(
    db: Session,
    row: BDAISubmission,
) -> None:
    employee = db.get(User, row.employee_user_id)

    if (
        employee is None
        or not employee.is_active
        or employee.account_status != "active"
        or employee.role != "bd_employee"
    ):
        # Retain the review decision even when the
        # original employee account is no longer active.
        return

    status_labels = {
        "approved": "Approved",
        "returned": "Returned for Revision",
        "rejected": "Rejected",
    }

    label = status_labels[row.status]

    created = create_global_notification(
        db,
        event_type=f"bd_ai.{row.status}",
        category="system",
        title=f"Technical Brief {label}",
        message=(
            f"Your submission {_reference(row)} "
            f"has been {label.lower()}. "
            "Open BD AI to view the decision."
        ),
        target_url="/bd-ai",
        recipient_user_ids=[row.employee_user_id],
        dedupe_key=(
            f"bd-ai:{row.id}:"
            f"revision:{row.current_revision}:{row.status}"
        ),
        requires_action=False,
        metadata={"submission_id": row.id},
    )

    if not created:
        raise HTTPException(
            409,
            "Employee notification could not be created. "
            "The review was not completed.",
        )


# --------------------------------------------------
# Employee: create submission
# --------------------------------------------------

@router.post("/submissions", status_code=201)
def create_submission(
    payload: SubmissionInput,
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> dict:
    snapshot = _snapshot(payload)
    fingerprint = _fingerprint(snapshot)

    duplicate_query = select(BDAISubmission).where(
        BDAISubmission.employee_user_id == employee.id,
        BDAISubmission.initial_fingerprint == fingerprint,
    )

    existing = db.scalar(duplicate_query)

    if existing is not None:
        return {
            **_summary(existing, _revision(db, existing)),
            "already_submitted": True,
        }

    manager = _resolve_manager(db, employee)

    row = BDAISubmission(
        employee_user_id=employee.id,
        manager_user_id=manager.id,
        employee_name=employee.full_name,
        employee_code=employee.employee_id,
        initial_fingerprint=fingerprint,
        status="pending_review",
        current_revision=1,
    )

    try:
        db.add(row)
        db.flush()

        revision = BDAISubmissionRevision(
            submission_id=row.id,
            revision_number=1,
            snapshot=snapshot,
            fingerprint=fingerprint,
        )

        db.add(revision)
        db.flush()

        _add_event(db, revision, employee, "submitted")
        _notify_manager(db, row)

        db.commit()

        return {
            **_summary(row, revision),
            "already_submitted": False,
        }

    except IntegrityError:
        db.rollback()

        existing = db.scalar(duplicate_query)

        if existing is not None:
            return {
                **_summary(
                    existing,
                    _revision(db, existing),
                ),
                "already_submitted": True,
            }

        raise

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# Employee and Manager: submission lists
# --------------------------------------------------

def _list_submissions(
    db: Session,
    user: User,
    request_status: str,
    limit: int,
    offset: int,
) -> dict:
    owner_column = (
        BDAISubmission.employee_user_id
        if user.role == "bd_employee"
        else BDAISubmission.manager_user_id
    )

    stmt = (
        select(
            BDAISubmission,
            BDAISubmissionRevision,
        )
        .join(
            BDAISubmissionRevision,
            (
                BDAISubmissionRevision.submission_id
                == BDAISubmission.id
            )
            & (
                BDAISubmissionRevision.revision_number
                == BDAISubmission.current_revision
            ),
        )
        .where(owner_column == user.id)
    )

    if request_status != "all":
        stmt = stmt.where(
            BDAISubmission.status == request_status
        )

    rows = db.execute(
        stmt.order_by(
            BDAISubmission.updated_at.desc(),
            BDAISubmission.id.desc(),
        ).offset(offset).limit(limit + 1)
    ).all()

    return {
        "items": [
            _summary(row, revision)
            for row, revision in rows[:limit]
        ],
        "has_more": len(rows) > limit,
        "offset": offset,
    }


SubmissionStatus = Literal[
    "all",
    "pending_review",
    "approved",
    "returned",
    "rejected",
]


@router.get("/submissions/mine")
def my_submissions(
    request_status: SubmissionStatus = "all",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> dict:
    return _list_submissions(
        db,
        employee,
        request_status,
        limit,
        offset,
    )


@router.get("/manager/submissions")
def manager_submissions(
    request_status: SubmissionStatus = "all",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    manager: User = Depends(_manager),
) -> dict:
    return _list_submissions(
        db,
        manager,
        request_status,
        limit,
        offset,
    )


# --------------------------------------------------
# Employee and Manager: submission details
# --------------------------------------------------

@router.get("/submissions/{submission_id}")
def submission_detail(
    submission_id: int,
    revision: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(_authorized_user),
) -> dict:
    row = _owned_submission(
        db,
        submission_id,
        user,
    )

    current = _revision(db, row)
    viewed = _revision(db, row, revision)

    revisions = db.scalars(
        select(BDAISubmissionRevision)
        .where(
            BDAISubmissionRevision.submission_id == row.id
        )
        .order_by(
            BDAISubmissionRevision.revision_number.desc()
        )
    ).all()

    events = db.execute(
        select(
            BDAISubmissionEvent,
            BDAISubmissionRevision.revision_number,
        )
        .join(
            BDAISubmissionRevision,
            BDAISubmissionRevision.id
            == BDAISubmissionEvent.revision_id,
        )
        .where(
            BDAISubmissionRevision.submission_id == row.id
        )
        .order_by(
            BDAISubmissionEvent.created_at.desc(),
            BDAISubmissionEvent.id.desc(),
        )
    ).all()

    manager = db.get(User, row.manager_user_id)

    return {
        **_summary(row, current),
        "manager_name": (
            manager.full_name if manager else None
        ),
        "snapshot": viewed.snapshot,
        "viewed_revision": viewed.revision_number,
        "revisions": [
            {
                "revision_number": item.revision_number,
                "submitted_at": item.submitted_at,
            }
            for item in revisions
        ],
        "events": [
            {
                "action": event.action,
                "actor_name": event.actor_name,
                "revision_number": revision_number,
                "note": event.note,
                "created_at": event.created_at,
            }
            for event, revision_number in events
        ],
    }


# --------------------------------------------------
# Manager: approve, return or reject
# --------------------------------------------------

@router.post(
    "/manager/submissions/{submission_id}/{decision}"
)
def review_submission(
    submission_id: int,
    decision: Literal["approve", "return", "reject"],
    payload: ReviewInput,
    db: Session = Depends(get_db),
    manager: User = Depends(_manager),
) -> dict:
    row = _owned_submission(
        db,
        submission_id,
        manager,
        lock=True,
    )

    if row.employee_user_id == manager.id:
        raise HTTPException(
            403,
            "Self-approval is prohibited",
        )

    if row.status != "pending_review":
        raise HTTPException(
            409,
            "This submission has already been reviewed",
        )

    if row.current_revision != payload.expected_revision:
        raise HTTPException(
            409,
            "The submission revision has changed. Refresh.",
        )

    note = payload.note.strip()

    if decision in {"return", "reject"} and not note:
        raise HTTPException(
            422,
            "Manager remarks are required",
        )

    revision = _revision(db, row)

    status_map = {
        "approve": "approved",
        "return": "returned",
        "reject": "rejected",
    }

    try:
        row.status = status_map[decision]
        row.updated_at = utc_now()

        _add_event(
            db,
            revision,
            manager,
            row.status,
            note or None,
        )

        resolve_notifications(
            db,
            recipient_user_ids=[manager.id],
            event_type="bd_ai.submitted",
            dedupe_key=_notification_key(
                row,
                row.current_revision,
            ),
            resolved_by_id=manager.id,
            resolution_note=row.status,
        )

        _notify_employee(db, row)

        db.commit()

        return _summary(row, revision)

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# Employee: resubmit a returned brief
# --------------------------------------------------

@router.post(
    "/submissions/{submission_id}/resubmit"
)
def resubmit_submission(
    submission_id: int,
    payload: ResubmissionInput,
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> dict:
    row = _owned_submission(
        db,
        submission_id,
        employee,
        lock=True,
    )

    snapshot = _snapshot(payload)
    fingerprint = _fingerprint(snapshot)

    current = _revision(db, row)

    # Handle retries without creating another revision.
    if (
        row.current_revision
        == payload.expected_revision + 1
        and current.fingerprint == fingerprint
    ):
        return {
            **_summary(row, current),
            "already_submitted": True,
        }

    if row.current_revision != payload.expected_revision:
        raise HTTPException(
            409,
            "The submission revision has changed. Refresh.",
        )

    if row.status != "returned":
        raise HTTPException(
            409,
            "Only returned submissions can be resubmitted",
        )

    manager = db.get(User, row.manager_user_id)

    if (
        manager is None
        or manager.role != "bd"
        or not manager.is_active
        or manager.account_status != "active"
    ):
        raise HTTPException(
            409,
            "Assigned BD Manager is unavailable",
        )

    try:
        row.current_revision += 1
        row.status = "pending_review"
        row.updated_at = utc_now()

        revision = BDAISubmissionRevision(
            submission_id=row.id,
            revision_number=row.current_revision,
            snapshot=snapshot,
            fingerprint=fingerprint,
        )

        db.add(revision)
        db.flush()

        _add_event(
            db,
            revision,
            employee,
            "resubmitted",
            payload.revision_note.strip() or None,
        )

        _notify_manager(db, row)

        db.commit()

        return {
            **_summary(row, revision),
            "already_submitted": False,
        }

    except Exception:
        db.rollback()
        raise
