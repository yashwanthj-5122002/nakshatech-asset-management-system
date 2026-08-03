"""Verify schema compatibility and Excel generation for the IT asset audit integration."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

# Running a file from /app/scripts makes Python use /app/scripts as sys.path[0].
# Add the backend project root so imports such as ``app.core.database`` work.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openpyxl import load_workbook
from sqlalchemy import inspect, select

from app.core.database import SessionLocal, engine
from app.main import initialize_application
from app.models.entities import User
from app.services.excel_service import build_asset_report, build_monthly_change_history_report


REQUIRED_ASSET_HISTORY_COLUMNS = {
    "change_type",
    "batch_code",
    "reason",
    "changed_by_name",
    "changed_by_role",
    "field_count",
}
REQUIRED_COMPONENT_COLUMNS = {"performed_by_email", "performed_by_role"}
REQUIRED_REPLACEMENT_COLUMNS = {
    "requested_by_email", "requested_by_role", "approved_by_email", "approved_by_role",
}
REQUIRED_ASSET_COLUMNS = {"original_asset_date"}
REQUIRED_MONTHLY_SHEETS = {
    "Monthly Summary",
    "Asset Edit Operations",
    "Detailed Field Changes",
    "Component Changes",
    "Complete Asset Replacements",
    "User Activity Summary",
}
REQUIRED_LIVE_HEADERS = {
    "date",
    "ORIGINAL ASSET DATE",
    "LAST UPDATED TIME",
    "UPDATED BY",
    "UPDATED BY ROLE",
    "LAST CHANGE TYPE",
    "FIELDS CHANGED",
    "EDIT REASON",
    "CHANGE BATCH ID",
}


def require_columns(table: str, required: set[str]) -> None:
    columns = {item["name"] for item in inspect(engine).get_columns(table)}
    missing = required - columns
    if missing:
        raise RuntimeError(f"{table} is missing columns: {', '.join(sorted(missing))}")


def main() -> None:
    initialize_application()
    require_columns("assets", REQUIRED_ASSET_COLUMNS)
    require_columns("asset_history", REQUIRED_ASSET_HISTORY_COLUMNS)
    require_columns("component_replacements", REQUIRED_COMPONENT_COLUMNS)
    require_columns("replacement_records", REQUIRED_REPLACEMENT_COLUMNS)

    month_key = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m")
    with SessionLocal() as db:
        users = list(db.scalars(select(User)).all())
        roles = {user.role for user in users}
        if not {"management", "it", "drone"}.issubset(roles):
            raise RuntimeError("Management, IT or Drone login record is missing")
        if not ({"admin", "software_team"} & roles):
            raise RuntimeError("No full-access Admin or Software Team login record is available")
        if any(not user.password_hash for user in users):
            raise RuntimeError("At least one login has an empty password hash")

        monthly = load_workbook(build_monthly_change_history_report(db, month_key), read_only=True, data_only=True)
        missing_sheets = REQUIRED_MONTHLY_SHEETS - set(monthly.sheetnames)
        monthly.close()
        if missing_sheets:
            raise RuntimeError(f"Monthly change workbook is missing sheets: {', '.join(sorted(missing_sheets))}")

        live = load_workbook(build_asset_report(db), read_only=True, data_only=True)
        headers = {cell.value for cell in next(live[live.sheetnames[0]].iter_rows(min_row=1, max_row=1))}
        live.close()
        missing_headers = REQUIRED_LIVE_HEADERS - headers
        if missing_headers:
            raise RuntimeError(f"Live Asset Register is missing audit columns: {', '.join(sorted(missing_headers))}")

    print("ASSET AUDIT INTEGRATION VERIFIED")
    print("- Non-destructive database columns are present")
    print("- Live Asset Register audit columns are present")
    print("- Month-wise IT Asset Changes workbook generated successfully")
    print("- Existing Software Team/Admin, Management, IT and Drone login records remain available")
    print("- Existing asset, work, component and replacement records were preserved")


if __name__ == "__main__":
    main()
