from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class TravelKmClaim(Base):
    __tablename__ = "travel_km_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), index=True)
    project_code_snapshot: Mapped[str] = mapped_column(String(80), index=True)
    project_name_snapshot: Mapped[str] = mapped_column(String(255))
    client_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    travel_date: Mapped[date] = mapped_column(Date, index=True)
    purpose_description: Mapped[str] = mapped_column(Text)

    start_km: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    end_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    start_latitude: Mapped[float] = mapped_column(Float)
    start_longitude: Mapped[float] = mapped_column(Float)
    start_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    gps_straight_line_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    distance_variance_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    distance_variance_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)

    rate_per_km: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("5.00"))
    calculated_allowance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    admin_eligible_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    hr_eligible_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_eligible_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_allowance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)

    admin_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    admin_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    admin_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    hr_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    hr_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    hr_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    finance_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    finance_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    payment_mode: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    attachments: Mapped[list["TravelKmAttachment"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="TravelKmAttachment.id"
    )
    events: Mapped[list["TravelKmEvent"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="TravelKmEvent.id"
    )
    email_routing: Mapped["TravelKmEmailRouting | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )
    email_deliveries: Mapped[list["TravelKmEmailDelivery"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="TravelKmEmailDelivery.id"
    )
    verification_snapshot: Mapped["TravelKmVerificationSnapshot | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )


class TravelKmAttachment(Base):
    __tablename__ = "travel_km_attachments"
    __table_args__ = (UniqueConstraint("claim_id", "phase", name="uq_travel_km_claim_phase"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    phase: Mapped[str] = mapped_column(String(20), index=True)  # start/end
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)

    device_latitude: Mapped[float] = mapped_column(Float)
    device_longitude: Mapped[float] = mapped_column(Float)
    device_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    device_captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    exif_gps_present: Mapped[bool] = mapped_column(Boolean, default=False)
    exif_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    exif_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    exif_captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exif_device_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_flag: Mapped[str] = mapped_column(String(80), default="live_gps_captured", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    claim: Mapped[TravelKmClaim] = relationship(back_populates="attachments")


class TravelKmEvent(Base):
    __tablename__ = "travel_km_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(255))
    actor_email: Mapped[str] = mapped_column(String(255))
    actor_role: Mapped[str] = mapped_column(String(50), index=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    claim: Mapped[TravelKmClaim] = relationship(back_populates="events")

class TravelKmTrackPoint(Base):
    __tablename__ = "travel_km_track_points"
    __table_args__ = (UniqueConstraint("claim_id", "captured_at", name="uq_travel_km_track_claim_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    source: Mapped[str] = mapped_column(String(40), default="browser_watch", index=True)

class TravelKmEmailRouting(Base):
    __tablename__ = "travel_km_email_routing"
    __table_args__ = (UniqueConstraint("claim_id", name="uq_travel_km_email_routing_claim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    reporting_manager_email: Mapped[str] = mapped_column(String(255), index=True)
    to_emails_json: Mapped[str] = mapped_column(Text)
    cc_emails_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    claim: Mapped[TravelKmClaim] = relationship(back_populates="email_routing")


class TravelKmEmailDelivery(Base):
    __tablename__ = "travel_km_email_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), default="submission", index=True)
    subject: Mapped[str] = mapped_column(String(255))
    to_emails_json: Mapped[str] = mapped_column(Text)
    cc_emails_json: Mapped[str] = mapped_column(Text, default="[]")
    delivery_mode: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    claim: Mapped[TravelKmClaim] = relationship(back_populates="email_deliveries")



class TravelKmProjectGeofence(Base):
    __tablename__ = "travel_km_project_geofences"
    __table_args__ = (UniqueConstraint("project_id", name="uq_travel_km_project_geofence_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    site_name: Mapped[str] = mapped_column(String(255))
    center_latitude: Mapped[float] = mapped_column(Float)
    center_longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float, default=500.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    configured_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class TravelKmVerificationSnapshot(Base):
    __tablename__ = "travel_km_verification_snapshots"
    __table_args__ = (UniqueConstraint("claim_id", name="uq_travel_km_verification_claim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("travel_km_claims.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(50), index=True)
    route_distance_km: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    odometer_km: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    route_variance_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    route_variance_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)
    point_count: Mapped[int] = mapped_column(Integer, default=0)
    max_gap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    discarded_segments: Mapped[int] = mapped_column(Integer, default=0)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    geofence_configured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_center_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_center_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_radius_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_entered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    nearest_site_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_site_entry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_site_presence_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    onsite_minutes: Mapped[int] = mapped_column(Integer, default=0)
    components_json: Mapped[str] = mapped_column(Text, default="[]")
    flags_json: Mapped[str] = mapped_column(Text, default="[]")
    source_version: Mapped[str] = mapped_column(String(40), default="v5.0")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    claim: Mapped[TravelKmClaim] = relationship(back_populates="verification_snapshot")
