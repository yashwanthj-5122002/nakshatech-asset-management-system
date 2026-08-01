from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.entities import Asset, Drone, DroneLocation, ReplacementRecord, User, WorkRecord
from app.services.excel_import_service import import_nakshatech_workbook


DEVELOPMENT_USERS = [
    ("admin@nakshatech.com", "System Administrator", "Admin@123", "admin"),
    ("management@nakshatech.com", "Management User", "Manager@123", "management"),
    ("it@nakshatech.com", "IT Department", "IT@123456", "it"),
    ("drone@nakshatech.com", "Drone Department", "Drone@123", "drone"),
]


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
                )
                for email, name, password, role in DEVELOPMENT_USERS
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
