from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User
from app.modules.operations.technical_directory_models import TechnicalDepartmentMember
from app.modules.operations.technical_directory_schemas import (
    TechnicalDirectoryMemberCreate,
    TechnicalDirectoryMemberUpdate,
)
from app.modules.operations.technical_directory_service import (
    LIVE_TECHNICAL_ROUTING_ENABLED,
    TECHNICAL_ROUTING_MODE,
    add_directory_member,
    directory_dashboard_payload,
    update_directory_member,
)


def _user(db, *, email: str, role: str, employee_id: str, name: str = "Test User") -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash=hash_password("TestingOnly@2026!"),
        role=role,
        employee_id=employee_id,
        account_status="active",
        is_active=True,
        email_verified=True,
    )
    db.add(row)
    db.flush()
    return row


def test_phase6_is_uat_locked_and_lists_six_peer_departments():
    with SessionLocal() as db:
        payload = directory_dashboard_payload(db, effective_role="admin")
        assert payload["routing_mode"] == "uat_demo_locked"
        assert payload["live_technical_routing_enabled"] is False
        assert payload["go_live_activation_available"] is False
        assert {item["department_code"] for item in payload["departments"]} == {
            "ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"
        }
        assert LIVE_TECHNICAL_ROUTING_ENABLED is False
        assert TECHNICAL_ROUTING_MODE == "uat_demo_locked"


def test_admin_directory_accepts_real_exact_role_user_and_rejects_wrong_role():
    with SessionLocal() as db:
        admin = _user(db, email="admin.v720@nakshatech.com", role="admin", employee_id="ADM-V720")
        lidar = _user(db, email="real.lidar.v720@nakshatech.com", role="lidar", employee_id="LIDAR-V720")
        civil = _user(db, email="real.civil.v720@nakshatech.com", role="civil", employee_id="CIVIL-V720")
        row = add_directory_member(
            db,
            department_code="lidar",
            actor=admin,
            payload=TechnicalDirectoryMemberCreate(user_id=lidar.id),
        )
        assert row.department_code == "lidar"
        assert row.user_id == lidar.id
        try:
            add_directory_member(
                db,
                department_code="lidar",
                actor=admin,
                payload=TechnicalDirectoryMemberCreate(user_id=civil.id),
            )
        except ValueError as exc:
            assert "exact LiDAR role" in str(exc)
        else:
            raise AssertionError("Cross-department directory assignment should be rejected")


def test_demo_account_cannot_be_added_to_real_directory():
    with SessionLocal() as db:
        admin = _user(db, email="admin.demo.guard.v720@nakshatech.com", role="admin", employee_id="ADM-V720-G")
        demo = _user(
            db,
            email="bim.demo@nakshatech.com",
            role="bim",
            employee_id="DEMO-V715-BIM-PM",
            name="BIM Demo PM",
        )
        try:
            add_directory_member(
                db,
                department_code="bim",
                actor=admin,
                payload=TechnicalDirectoryMemberCreate(user_id=demo.id),
            )
        except ValueError as exc:
            assert "Reserved UAT demo accounts" in str(exc)
        else:
            raise AssertionError("Reserved demo account should not enter the real production directory")


def test_technical_login_sees_only_its_own_department_directory():
    with SessionLocal() as db:
        admin = _user(db, email="admin.visible.v720@nakshatech.com", role="admin", employee_id="ADM-V720-V")
        lidar = _user(db, email="lidar.visible.v720@nakshatech.com", role="lidar", employee_id="LID-V720-V")
        bim = _user(db, email="bim.visible.v720@nakshatech.com", role="bim", employee_id="BIM-V720-V")
        add_directory_member(db, department_code="lidar", actor=admin, payload=TechnicalDirectoryMemberCreate(user_id=lidar.id))
        add_directory_member(db, department_code="bim", actor=admin, payload=TechnicalDirectoryMemberCreate(user_id=bim.id))
        db.commit()

        lidar_view = directory_dashboard_payload(db, effective_role="lidar")
        assert lidar_view["viewer_mode"] == "department_read_only"
        assert [item["department_code"] for item in lidar_view["departments"]] == ["lidar"]
        assert lidar_view["departments"][0]["eligible_users"] == []


def test_directory_row_is_additive_and_soft_state_can_be_preserved():
    with SessionLocal() as db:
        admin = _user(db, email="admin.row.v720@nakshatech.com", role="admin", employee_id="ADM-V720-R")
        ortho = _user(db, email="ortho.real.v720@nakshatech.com", role="ortho", employee_id="ORTHO-V720-R")
        add_directory_member(db, department_code="ortho", actor=admin, payload=TechnicalDirectoryMemberCreate(user_id=ortho.id))
        assert db.scalar(select(TechnicalDepartmentMember.id).where(TechnicalDepartmentMember.user_id == ortho.id)) is not None


def test_admin_can_configure_future_use_flags_and_readiness_recalculates():
    with SessionLocal() as db:
        admin = _user(db, email="admin.flags.v720@nakshatech.com", role="admin", employee_id="ADM-V720-F")
        mobile = _user(db, email="mobile.real.v720@nakshatech.com", role="mobile_mapping", employee_id="MOB-V720-F")
        row = add_directory_member(
            db,
            department_code="mobile_mapping",
            actor=admin,
            payload=TechnicalDirectoryMemberCreate(user_id=mobile.id),
        )
        db.commit()

        before = directory_dashboard_payload(db, effective_role="admin")
        mobile_before = next(item for item in before["departments"] if item["department_code"] == "mobile_mapping")
        assert mobile_before["readiness"]["live_ready"] is True

        update_directory_member(
            db,
            row=row,
            actor=admin,
            payload=TechnicalDirectoryMemberUpdate(receive_handover_notifications=False),
        )
        db.commit()
        after = directory_dashboard_payload(db, effective_role="admin")
        mobile_after = next(item for item in after["departments"] if item["department_code"] == "mobile_mapping")
        assert mobile_after["readiness"]["handover_recipients"] == 0
        assert mobile_after["readiness"]["live_ready"] is False


def test_management_and_bd_are_read_only_dashboard_viewers():
    with SessionLocal() as db:
        management = directory_dashboard_payload(db, effective_role="management")
        bd = directory_dashboard_payload(db, effective_role="bd")
        assert management["viewer_mode"] == "read_only"
        assert bd["viewer_mode"] == "read_only"
        assert len(management["departments"]) == 6
        assert len(bd["departments"]) == 6
        assert all(item["eligible_users"] == [] for item in management["departments"])
        assert all(item["eligible_users"] == [] for item in bd["departments"])
