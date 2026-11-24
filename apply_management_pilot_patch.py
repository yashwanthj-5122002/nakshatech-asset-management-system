
from __future__ import annotations

import argparse
import ast
import os
import shutil
from datetime import datetime
from pathlib import Path

FILES = {
    "models": "backend/app/modules/management_clients/models.py",
    "clients": "backend/app/modules/management_clients/router.py",
    "projects": "backend/app/modules/management_projects/router.py",
    "management_ui": "frontend/src/features/management/ManagementClientRegisterPage.tsx",
    "finance_ui": "frontend/src/features/finance/pages/FinanceManagementProjectsPage.tsx",
}

parser = argparse.ArgumentParser()
parser.add_argument("--root", default=".")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

root = Path(args.root).resolve()
paths = {key: root / name for key, name in FILES.items()}

original = {}
edited = {}
newline_styles = {}
bom_styles = {}

for key, path in paths.items():
    if not path.is_file():
        raise SystemExit(f"STOP: Missing source file: {path}")

    raw = path.read_bytes()
    bom_styles[key] = raw.startswith(b"\xef\xbb\xbf")
    newline_styles[key] = "\r\n" if b"\r\n" in raw else "\n"
    content = raw.decode("utf-8-sig").replace("\r\n", "\n")

    original[key] = raw
    edited[key] = content

if "class ManagementProjectClassification(" in edited["models"]:
    raise SystemExit("STOP: Pilot patch appears to be installed already.")


def replace(key: str, old: str, new: str) -> None:
    count = edited[key].count(old)
    if count != 1:
        raise RuntimeError(
            f"STOP: {key}: expected one exact anchor, found {count}.\n"
            f"Anchor: {old[:130]!r}\n"
            "No source files have been changed."
        )
    edited[key] = edited[key].replace(old, new, 1)


def after(key: str, anchor: str, addition: str) -> None:
    replace(key, anchor, anchor + addition)


# ============================================================
# 1. PERSISTENT MANAGEMENT CLASSIFICATION
# ============================================================

after(
    "models",
    '    project_name: Mapped[str] = mapped_column(String(255))\n',
    '''    project_type: Mapped[str] = mapped_column(String(16), nullable=False, default="regular")
    pilot_payment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
''',
)

edited["models"] += '''

class ManagementProjectClassification(Base):
    """Permanent classification for a Finance-created Management project."""

    __tablename__ = "management_project_classifications"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    project_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="regular"
    )
    pilot_payment_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
'''


# ============================================================
# 2. MANAGEMENT CLIENT REQUESTS
# ============================================================

after(
    "clients",
    '    remarks: str | None = Field(default=None, max_length=2000)\n',
    '''    project_type: str = Field(default="regular", pattern="^(regular|pilot)$")
    pilot_payment_type: str | None = Field(default=None, pattern="^(free|paid)$")
''',
)

replace(
    "clients",
    'update={"can_request_project": row.created_by_id == auth.user.id and row.is_active}',
    'update={"can_request_project": row.is_active}',
)

replace(
    "clients",
    '''select(ManagementAdditionalProjectRequest).where(
        ManagementAdditionalProjectRequest.requested_by_id == auth.user.id,
    ).order_by(''',
    '''select(ManagementAdditionalProjectRequest).order_by(''',
)

after(
    "clients",
    '        "remarks": row.remarks, "status": row.status,\n',
    '''        "project_type": row.project_type or "regular",
        "pilot_payment_type": row.pilot_payment_type,
''',
)

after(
    "clients",
    '''    _management_only(auth)
    from datetime import date, datetime
''',
    '''    if payload.project_type == "pilot" and payload.pilot_payment_type not in {"free", "paid"}:
        raise HTTPException(status_code=422, detail="Select Free Pilot or Paid Pilot")
    if payload.project_type == "regular" and payload.pilot_payment_type is not None:
        raise HTTPException(status_code=422, detail="Regular projects cannot have a pilot payment type")
''',
)

replace(
    "clients",
    '''        if client.created_by_id != auth.user.id:
            raise HTTPException(status_code=403, detail="Only the original Management source may request a project for this client")
''',
    '''        # Both authorised Management accounts may request projects.
        # The original client source retains post-delivery approval authority.
''',
)

after(
    "clients",
    '''            expected_start_date=date_value, remarks=(payload.remarks or "").strip() or None,
''',
    '''            project_type=payload.project_type,
            pilot_payment_type=payload.pilot_payment_type,
''',
)


# ============================================================
# 3. FINANCE CREATION AND PROJECT READ MODEL
# ============================================================

replace(
    "projects",
    '''from app.modules.management_clients.models import ManagementClientIntake, ManagementAdditionalProjectRequest''',
    '''from app.modules.management_clients.models import (
    ManagementClientIntake, ManagementAdditionalProjectRequest,
    ManagementProjectClassification,
)''',
)

after(
    "projects",
    '''    project_manager_id: int | None = Field(default=None, gt=0)
''',
    '''    project_type: str = Field(default="regular", pattern="^(regular|pilot)$")
    pilot_payment_type: str | None = Field(default=None, pattern="^(free|paid)$")
''',
)

replace(
    "projects",
    '''    def validate_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date")
        return self
''',
    '''    def validate_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date")

        if self.project_type == "regular":
            if self.pilot_payment_type is not None:
                raise ValueError("Regular projects cannot have a pilot payment type")
        else:
            if self.pilot_payment_type not in {"free", "paid"}:
                raise ValueError("Select Free Pilot or Paid Pilot")

            amount = Decimal(str(self.commercial.estimated_amount))

            if self.pilot_payment_type == "free" and amount != 0:
                raise ValueError("A Free Pilot must have zero commercial value")

            if self.pilot_payment_type == "paid" and amount <= 0:
                raise ValueError("A Paid Pilot must have positive commercial value")

        return self
''',
)

after(
    "projects",
    '''    pm = project.master_profile.project_manager if project.master_profile else None
''',
    '''    classification = db.get(ManagementProjectClassification, project.id)
''',
)

after(
    "projects",
    '''        "source_person_name": link.source_person_name,
''',
    '''        "project_type": classification.project_type if classification else "regular",
        "pilot_payment_type": classification.pilot_payment_type if classification else None,
''',
)

replace(
    "projects",
    '''        client = _finance_client_for_intake(db, intake, auth)
''',
    '''        if request_row is not None:
            if (
                (request_row.project_type or "regular") != payload.project_type
                or request_row.pilot_payment_type != payload.pilot_payment_type
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Project classification must match the Management request",
                )

        client = _finance_client_for_intake(db, intake, auth)
''',
)

replace(
    "projects",
    '''        db.flush()
        db.add(ProjectWorkflowEvent(
''',
    '''        db.add(ManagementProjectClassification(
            project_id=project.id,
            project_type=payload.project_type,
            pilot_payment_type=payload.pilot_payment_type,
        ))
        db.flush()
        db.add(ProjectWorkflowEvent(
''',
)


after(
    "projects",
    '''"additional_request_id": request_row.id if request_row else None,
''',
    '''                          "project_type": payload.project_type,
                          "pilot_payment_type": payload.pilot_payment_type,
''',
)


after(
    "projects",
    '''            "remarks": row.remarks, "status": row.status,
''',
    '''            "project_type": row.project_type or "regular",
            "pilot_payment_type": row.pilot_payment_type,
''',
)


# ============================================================
# 4. MANAGEMENT FRONTEND
# ============================================================

after(
    "management_ui",
    '''  expected_start_date: string | null; remarks: string | null
''',
    '''  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
''',
)

after(
    "management_ui",
    '''  can_approve: boolean; source_approved: boolean
''',
    '''  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
''',
)

after(
    "management_ui",
    "  const [requestProjectName, setRequestProjectName] = useState('')\n",
    """  const [requestProjectType, setRequestProjectType] = useState<'regular' | 'pilot'>('regular')
  const [requestPilotPaymentType, setRequestPilotPaymentType] = useState<'free' | 'paid'>('free')
""",
)

after(
    "management_ui",
    """  const [trackingView, setTrackingView] = useState<'clients' | 'projects'>('clients')
""",
    """  const [projectTypeFilter, setProjectTypeFilter] = useState('')
""",
)

after(
    "management_ui",
    "    setRequestProjectName('')\n",
    """    setRequestProjectType('regular')
    setRequestPilotPaymentType('free')
""",
)

after(
    "management_ui",
    '''        project_name: requestProjectName.trim(), scope_text: requestScope.trim(),
''',
    '''        project_type: requestProjectType,
        pilot_payment_type: requestProjectType === 'pilot' ? requestPilotPaymentType : null,
''',
)

replace(
    "management_ui",
    '''    return (!ownerFilter || project.source_person_name === ownerFilter) && (!term ||
''',
    '''    return (!projectTypeFilter || project.project_type === projectTypeFilter) &&
      (!ownerFilter || project.source_person_name === ownerFilter) && (!term ||
''',
)

after(
    "management_ui",
    '''        <label className="operations-field"><span>Registered By</span><select value={ownerFilter} onChange={event => setOwnerFilter(event.target.value)}><option value="">Both Management Users</option>{owners.map(owner => <option key={owner} value={owner}>{owner}</option>)}</select></label>
''',
    '''        {trackingView === 'projects' && <label className="operations-field"><span>Project Type</span><select value={projectTypeFilter} onChange={e => setProjectTypeFilter(e.target.value)}><option value="">All Projects</option><option value="regular">Regular Projects</option><option value="pilot">Pilot Projects</option></select></label>}
''',
)

replace(
    "management_ui",
    '''        <label className="operations-field"><span>Requested Project Name *</span>''',
    '''        <label className="operations-field"><span>Project Type *</span><select value={requestProjectType} onChange={e => setRequestProjectType(e.target.value as 'regular' | 'pilot')}><option value="regular">Regular Project</option><option value="pilot">Pilot Project</option></select></label>
        {requestProjectType === 'pilot' && <label className="operations-field"><span>Pilot Financial Type *</span><select value={requestPilotPaymentType} onChange={e => setRequestPilotPaymentType(e.target.value as 'free' | 'paid')}><option value="free">Free Pilot</option><option value="paid">Paid Pilot</option></select></label>}
        <label className="operations-field"><span>Requested Project Name *</span>''',
)

replace(
    "management_ui",
    '''<td><strong>{project.project_code}</strong></td><td>{project.project_name}</td><td>{project.department_label}</td>''',
    '''<td><strong>{project.project_code}</strong></td><td>{project.project_name}{project.project_type === 'pilot' && <span style={{ marginLeft: 8, fontWeight: 700, color: '#176d79' }}>PILOT</span>}</td><td>{project.department_label}</td>''',
)

replace(
    "management_ui",
    '''<td><strong>{project.project_name}</strong><small>PM: {project.project_manager_name || 'Not assigned'}</small></td>''',
    '''<td><strong>{project.project_name}</strong>{project.project_type === 'pilot' && <small style={{ color: '#176d79', fontWeight: 700 }}>PILOT · {project.pilot_payment_type?.toUpperCase()}</small>}<small>PM: {project.project_manager_name || 'Not assigned'}</small></td>''',
)


# ============================================================
# 5. FINANCE FRONTEND
# ============================================================

after(
    "finance_ui",
    '''  project_value: number | null; currency: string; source_approved: boolean
''',
    '''  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
''',
)

after(
    "finance_ui",
    '''  created_project_id: number | null; created_project_code: string | null; created_at: string
''',
    '''  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
''',
)

after(
    "finance_ui",
    '''  const [project, setProject] = useState<ProjectForm>(emptyProject)
''',
    """  const [projectType, setProjectType] = useState<'regular' | 'pilot'>('regular')
  const [pilotPaymentType, setPilotPaymentType] = useState<'free' | 'paid'>('free')
  const [projectTypeFilter, setProjectTypeFilter] = useState('')
""",
)

after(
    "finance_ui",
    '''    setSelectedRequestId(requestRow?.id ?? null)
''',
    """    setProjectType(requestRow?.project_type ?? 'regular')
    setPilotPaymentType(requestRow?.pilot_payment_type ?? 'free')
""",
)

after(
    "finance_ui",
    '''    const problems = commercialFormProblems(commercial)
    if (problems.length) { setError(problems[0]); return }
''',
    '''    if (projectType === 'pilot') {
      const amount = Number(commercialFormToPayload(commercial).estimated_amount)
      if (!Number.isFinite(amount)) {
        setError('Enter a valid Pilot Project commercial value.'); return
      }
      if (pilotPaymentType === 'free' && amount !== 0) {
        setError('Free Pilot commercial value must be zero.'); return
      }
      if (pilotPaymentType === 'paid' && amount <= 0) {
        setError('Paid Pilot commercial value must be greater than zero.'); return
      }
    }
''',
)

after(
    "finance_ui",
    '''          additional_request_id: selectedRequestId,
''',
    '''          project_type: projectType,
          pilot_payment_type: projectType === 'pilot' ? pilotPaymentType : null,
''',
)


replace(
    "finance_ui",
    '''      (!statusFilter || status === statusFilter) &&
      (!sourceFilter || row.source_person_name === sourceFilter)
''',
    '''      (!statusFilter || status === statusFilter) &&
      (!sourceFilter || row.source_person_name === sourceFilter) &&
      (!projectTypeFilter || row.project_type === projectTypeFilter)
''',
)



replace(
    "finance_ui",
    '''  }), [data.projects, clientById, lifecycleById, search, departmentFilter, statusFilter, sourceFilter])
''',
    '''  }), [data.projects, clientById, lifecycleById, search, departmentFilter, statusFilter, sourceFilter, projectTypeFilter])
''',
)


replace(
    "finance_ui",
    '''}, [search, departmentFilter, statusFilter, sourceFilter])
''',
    '''}, [search, departmentFilter, statusFilter, sourceFilter, projectTypeFilter])
''',
)

after(
    "finance_ui",
    '''      <select aria-label="Management source filter" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="">All Sources</option>{sources.map(s => <option key={s} value={s}>{s}</option>)}</select>
''',
    '''      <select aria-label="Project type filter" value={projectTypeFilter} onChange={e => setProjectTypeFilter(e.target.value)}><option value="">All Project Types</option><option value="regular">Regular Projects</option><option value="pilot">Pilot Projects</option></select>
''',
)

replace(
    "finance_ui",
    '''setStatusFilter(''); setSourceFilter('')''',
    '''setStatusFilter(''); setSourceFilter(''); setProjectTypeFilter('')''',
)

replace(
    "finance_ui",
    '''<td><strong>{row.project_name}</strong><small>PM: {row.project_manager_name || 'Awaiting assignment'}</small></td>''',
    '''<td><strong>{row.project_name}</strong>{row.project_type === 'pilot' && <small style={{ color: '#176d79', fontWeight: 700 }}>PILOT · {row.pilot_payment_type?.toUpperCase()}</small>}<small>PM: {row.project_manager_name || 'Awaiting assignment'}</small></td>''',
)

replace(
    "finance_ui",
    '''<td><strong>{row.project_name}</strong><small>{row.scope_text}</small>''',
    '''<td><strong>{row.project_name}</strong>{row.project_type === 'pilot' && <small style={{ color: '#176d79', fontWeight: 700 }}>PILOT · {row.pilot_payment_type?.toUpperCase()}</small>}<small>{row.scope_text}</small>''',
)

replace(
    "finance_ui",
    '''        <div className="mp-form-section"><h3>2. Project Details</h3>''',
    '''        <div className="mp-form-section"><h3>Project Classification</h3>
          <div className="mp-form-grid">
            <label className="mp-field"><span>Project Type *</span>
              <select value={projectType} disabled={selectedRequestId !== null} onChange={e => setProjectType(e.target.value as 'regular' | 'pilot')}>
                <option value="regular">Regular Project</option>
                <option value="pilot">Pilot Project</option>
              </select>
            </label>
            {projectType === 'pilot' && <label className="mp-field"><span>Pilot Financial Type *</span>
              <select value={pilotPaymentType} disabled={selectedRequestId !== null} onChange={e => setPilotPaymentType(e.target.value as 'free' | 'paid')}>
                <option value="free">Free Pilot</option>
                <option value="paid">Paid Pilot</option>
              </select>
            </label>}
          </div>
          {projectType === 'pilot' && <p className="mp-form-help">{pilotPaymentType === 'free' ? 'Set estimated commercial value to zero. Finance tracks costs, but no customer invoice may be raised.' : 'Enter a positive commercial value. The existing Finance billing process applies.'}</p>}
        </div>
        <div className="mp-form-section"><h3>2. Project Details</h3>''',
)

replace(
    "finance_ui",
    '''  const canOpenInvoices = INVOICE_STATES.has(billingStatus.toUpperCase()) &&
    (Boolean(selectedProject?.source_approved) || selectedFinancial.invoice_count > 0)
''',
    '''  const isFreePilot = selectedProject?.project_type === 'pilot' && selectedProject.pilot_payment_type === 'free'
  const canOpenInvoices = !isFreePilot && INVOICE_STATES.has(billingStatus.toUpperCase()) &&
    (Boolean(selectedProject?.source_approved) || selectedFinancial.invoice_count > 0)
''',
)

replace(
    "finance_ui",
    '''{canOpenInvoices ? <FinanceBillingPage key={selectedProject.id} embeddedProjectId={selectedProject.id}/> :''',
    '''{isFreePilot ? <div className="mp-billing-locked"><ShieldCheck size={27}/><h3>Free Pilot — No Customer Invoice</h3><p>Finance may track legitimate project costs. Customer invoicing is prohibited for free pilots.</p></div> : canOpenInvoices ? <FinanceBillingPage key={selectedProject.id} embeddedProjectId={selectedProject.id}/> :''',
)


# ============================================================
# 6. DATABASE MIGRATION
# ============================================================

migration = r"""
BEGIN;

ALTER TABLE management_additional_project_requests
    ADD COLUMN IF NOT EXISTS project_type VARCHAR(16)
    NOT NULL DEFAULT 'regular';

ALTER TABLE management_additional_project_requests
    ADD COLUMN IF NOT EXISTS pilot_payment_type VARCHAR(16);

CREATE TABLE IF NOT EXISTS management_project_classifications (
    project_id INTEGER PRIMARY KEY
        REFERENCES finance_projects(id) ON DELETE RESTRICT,
    project_type VARCHAR(16) NOT NULL DEFAULT 'regular',
    pilot_payment_type VARCHAR(16),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_mgmt_pilot_classification CHECK (
        (project_type = 'regular' AND pilot_payment_type IS NULL)
        OR
        (project_type = 'pilot' AND pilot_payment_type IN ('free','paid'))
    )
);

CREATE OR REPLACE FUNCTION block_free_management_pilot_invoice()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM management_project_classifications
        WHERE project_id = NEW.project_id
          AND project_type = 'pilot'
          AND pilot_payment_type = 'free'
    ) THEN
        RAISE EXCEPTION
            'Customer invoices are prohibited for Free Pilot projects';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.project_invoices') IS NULL THEN
        RAISE EXCEPTION
            'Expected project_invoices table not found. Migration stopped.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_block_free_management_pilot_invoice'
          AND tgrelid = 'public.project_invoices'::regclass
    ) THEN
        CREATE TRIGGER trg_block_free_management_pilot_invoice
        BEFORE INSERT OR UPDATE ON public.project_invoices
        FOR EACH ROW
        EXECUTE FUNCTION block_free_management_pilot_invoice();
    END IF;
END;
$$;

COMMIT;
"""


# ============================================================
# 7. VALIDATE AND APPLY
# ============================================================

for key in ("models", "clients", "projects"):
    try:
        ast.parse(edited[key], filename=FILES[key])
    except SyntaxError as exc:
        raise RuntimeError(
            f"STOP: Python syntax check failed in {FILES[key]}: {exc}"
        ) from exc

print("PASS: All source anchors found.")
print("PASS: All edited backend Python files parsed.")
print("Files to change:")
for name in FILES.values():
    print("  ", name)

if not args.apply:
    print("\nDRY RUN ONLY. No files changed.")
    print("Run again with --apply to install.")
    raise SystemExit(0)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = root / "backups" / f"management_pilot_{stamp}"
written = []

try:
    for key, path in paths.items():
        backup = backup_root / FILES[key]
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original[key])

    for key, path in paths.items():
        content = edited[key].replace("\n", newline_styles[key])
        encoding = "utf-8-sig" if bom_styles[key] else "utf-8"
        temp = path.with_name(path.name + ".pilot_patch_tmp")
        temp.write_bytes(content.encode(encoding))
        os.replace(temp, path)
        written.append(key)

    sql_path = root / "pilot_management_migration.sql"
    if sql_path.exists():
        raise RuntimeError(
            "Migration file already exists. Stop to avoid overwriting it."
        )
    sql_path.write_text(migration.strip() + "\n", encoding="utf-8")

except Exception:
    for key in written:
        paths[key].write_bytes(original[key])
    raise

print("\nPASS: Management Pilot source patch installed.")
print("BACKUP:", backup_root)
print("SQL MIGRATION:", sql_path)
print("No database changes have been applied yet.")
print("NEXT: Build frontend and apply the SQL migration safely.")
