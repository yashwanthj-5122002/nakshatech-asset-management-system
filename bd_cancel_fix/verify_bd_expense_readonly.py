"""Read-only check: run with docker compose exec -T backend python -."""
from sqlalchemy import select
from app.core.database import get_db
from app.modules.commercial.models import ProjectExpense, ProjectExpenseEvent
from app.modules.commercial.router import router
from app.modules.commercial.service import assert_commercial_closure_ready

code = "PEXP-20261030-4EBCF78F0C"
route = "/commercial/expenses/{expense_id}/cancel"
registered = any(getattr(r, 'path', '') == route and 'POST' in getattr(r, 'methods', set()) for r in router.routes)
print("Authenticated cancel API registered:", registered)
if not registered:
    raise SystemExit('Cancellation route missing: check backend rebuild and registration')

gen = get_db()
db = next(gen)
try:
    expense = db.scalar(select(ProjectExpense).where(ProjectExpense.expense_code == code))
    if expense is None:
        raise SystemExit("Expected project expense not found")
    print("Expense ID:", expense.id)
    print("Project ID:", expense.project_id)
    print("Expense code:", expense.expense_code)
    print("Status:", expense.status)
    print("Employee ID:", expense.employee_id)
    history = db.scalars(select(ProjectExpenseEvent).where(ProjectExpenseEvent.expense_id==expense.id).order_by(ProjectExpenseEvent.id)).all()
    print("History:", [(e.action,e.from_status,e.to_status) for e in history])
    try:
        assert_commercial_closure_ready(db, project_id=expense.project_id)
        print("Commercial Closure Guard: PASSED")
    except ValueError as exc:
        print("Commercial Closure Guard: BLOCKED -", str(exc))
finally:
    db.rollback()
    gen.close()
