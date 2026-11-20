"""Explicit local/UAT creation of exactly FIVE BD Employee test accounts.

Usage inside the running backend container (interactive terminal):
    python -m app.modules.bd_employee.seed_test_accounts

The operator chooses each password via a non-echoing prompt. Plaintext passwords
are neither logged nor written to files. Existing accounts remain untouched
unless --reset-passwords is explicitly supplied.
"""
from __future__ import annotations

import argparse
import re
from getpass import getpass

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User


TEST_USERS = tuple((f"BD{i:02d}", f"bd{i:02d}@nakshatech.com") for i in range(1, 6))
LEGACY_USERS = tuple((f"BD{i:03d}", f"bd{i:03d}@nakshatech.com") for i in range(1, 6))


def _get_password(label: str) -> str:
    """Read a user-chosen password without showing or persisting its plaintext."""
    while True:
        first = getpass(f"Enter password for {label}: ")
        second = getpass("Confirm password: ")
        if first != second:
            print("Passwords did not match. Try again.")
            continue
        if (
            len(first) < 12
            or not re.search(r"[A-Za-z]", first)
            or not re.search(r"[0-9]", first)
            or not re.search(r"[^A-Za-z0-9]", first)
        ):
            print("Use at least 12 characters, including a letter, number and symbol.")
            continue
        return first


def main() -> None:
    parser = argparse.ArgumentParser(description="Local/UAT BD01-BD05 account provisioning")
    parser.add_argument(
        "--shared-password", action="store_true",
        help="Prompt once for a shared TEST password; individual passwords are safer",
    )
    parser.add_argument(
        "--reset-passwords", action="store_true",
        help="Explicitly replace passwords ONLY for existing BD01-BD05 accounts",
    )
    args = parser.parse_args()

    if any(
        (value or "").strip().lower() in {"production", "prod", "live"}
        for value in (settings.environment, settings.app_env)
    ):
        raise SystemExit("Refusing to create test accounts in a production environment.")
    if "nakshatech.com" not in settings.allowed_email_domain_list:
        raise SystemExit("The organization email-domain configuration does not permit these test emails.")

    with SessionLocal() as db:
        # A previous bd001-bd005 seed should not silently create a second set.
        for legacy_id, legacy_email in LEGACY_USERS:
            old = db.scalar(select(User.id).where(
                (func.lower(User.email) == legacy_email)
                | (func.lower(User.employee_id) == legacy_id.lower())
            ).limit(1))
            if old is not None:
                raise SystemExit(
                    "Old BD001-BD005 test account identifiers already exist. "
                    "Stop and review them before creating BD01-BD05; nothing changed."
                )

        pending: list[tuple[str, str, User | None]] = []
        for employee_id, email in TEST_USERS:
            by_email = db.scalar(select(User).where(func.lower(User.email) == email))
            by_id = db.scalar(select(User).where(
                func.lower(User.employee_id) == employee_id.lower()
            ))
            if by_email is not None or by_id is not None:
                if not (
                    by_email is not None
                    and by_id is not None
                    and by_email.id == by_id.id
                    and by_email.role == "bd_employee"
                    and by_email.is_active
                    and by_email.account_status == "active"
                ):
                    raise SystemExit(
                        f"Account collision for {employee_id}. No changes were made."
                    )
                if args.reset_passwords:
                    pending.append((employee_id, email, by_email))
            else:
                pending.append((employee_id, email, None))

        if not pending:
            print("All 5 BD01-BD05 test accounts already exist. Passwords were not changed.")
            print("To choose new passwords later, explicitly run with --reset-passwords.")
            return

        new_count = sum(user is None for _, _, user in pending)
        reset_count = len(pending) - new_count
        print(f"Will create {new_count} new account(s) and reset {reset_count} password(s).")
        print("Passwords will NOT be displayed, recorded in the command or saved in a file.")
        if args.shared_password:
            print("WARNING: A shared password is only suitable for temporary local testing.")
        confirmation = "RESET" if args.reset_passwords else "CREATE"
        if input(f"Type {confirmation} to continue: ").strip() != confirmation:
            print("Cancelled. No database changes were made.")
            return

        selected: list[tuple[str, str, User | None, str]] = []
        shared = _get_password("all five BD test accounts") if args.shared_password else None
        for employee_id, email, existing in pending:
            password = shared if shared is not None else _get_password(email)
            selected.append((employee_id, email, existing, password))

        # One transaction; all prompts/eligibility checks finish before writing.
        for employee_id, email, existing, password in selected:
            if existing is not None:
                existing.password_hash = hash_password(password)
                existing.token_version = (existing.token_version or 0) + 1
            else:
                db.add(User(
                    employee_id=employee_id,
                    email=email,
                    full_name=f"BD Test Employee {employee_id[-2:]}",
                    password_hash=hash_password(password),
                    role="bd_employee",
                    branch="Head Office",
                    department="Business Development",
                    designation="BD Employee",
                    email_verified=True,
                    account_status="active",
                    is_active=True,
                    mfa_required=False,
                    must_change_password=False,
                    token_version=0,
                ))
        db.commit()

    print(f"SUCCESS: Created {new_count} BD account(s); reset {reset_count} password(s).")
    for employee_id, email in TEST_USERS:
        print(f"  {employee_id}  {email}")
    print("Passwords were not printed. Store your chosen passwords securely.")


if __name__ == "__main__":
    main()
