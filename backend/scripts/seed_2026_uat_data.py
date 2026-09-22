from __future__ import annotations

from pathlib import Path
import sys

# Running "python scripts/<name>.py" sets sys.path[0] to /app/scripts inside Docker.
# Add the backend project root explicitly so imports such as "app.core.database" work
# consistently both as a direct script and from local development environments.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import json
from decimal import Decimal

from app.core.database import SessionLocal
from app.uat_2026 import (
    DEFAULT_CLIENTS,
    DEFAULT_PROJECTS,
    DEFAULT_SEED,
    TAG,
    TARGET_REALIZED_REVENUE_INR,
    existing_counts,
    seed_year_2026,
    validate_year_2026,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create the deterministic Nakshatech full-year 2026 ERP UAT dataset.")
    p.add_argument("--clients", type=int, default=DEFAULT_CLIENTS)
    p.add_argument("--projects", type=int, default=DEFAULT_PROJECTS)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--target-revenue-inr", type=Decimal, default=TARGET_REALIZED_REVENUE_INR)
    p.add_argument("--dry-run", action="store_true", help="Show requested configuration and existing UAT counts without writing.")
    return p


def main() -> int:
    args = parser().parse_args()
    with SessionLocal() as db:
        before = existing_counts(db)
        if args.dry_run:
            print(json.dumps({
                "tag": TAG,
                "mode": "dry-run",
                "requested_clients": args.clients,
                "requested_projects": args.projects,
                "seed": args.seed,
                "target_realized_revenue_inr": float(args.target_revenue_inr),
                "existing": before,
            }, indent=2))
            return 0

        summary = seed_year_2026(
            db,
            clients=args.clients,
            projects=args.projects,
            seed=args.seed,
            target_realized_revenue_inr=args.target_revenue_inr,
        )
        validation = validate_year_2026(db)
        print(json.dumps({
            "tag": TAG,
            "seeded": {
                "clients": summary.clients,
                "projects": summary.projects,
                "commercial_revisions": summary.commercial_revisions,
                "work_packages": summary.work_packages,
                "invoices": summary.invoices,
                "payments": summary.payments,
                "closed_invoices": summary.closed_invoices,
                "realized_revenue_inr": float(summary.revenue_inr),
                "expenses": summary.expenses,
                "vendor_invoices": summary.vendor_invoices,
                "expense_claims": summary.expense_claims,
                "feedback_requests": summary.feedback_requests,
                "rework_cycles": summary.rework_cycles,
                "change_requests": summary.change_requests,
                "travel_km_claims": summary.travel_km_claims,
                "assets": summary.assets,
                "work_records": summary.work_records,
                "drones": summary.drones,
            },
            "validation": validation,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
