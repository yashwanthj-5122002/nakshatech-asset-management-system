
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Save this script in the ERP project root.
ROOT = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

FILES = {
    "models": ROOT / "backend/app/modules/management_clients/models.py",
    "router": ROOT / "backend/app/modules/management_clients/router.py",
    "management": ROOT / "frontend/src/features/management/ManagementClientRegisterPage.tsx",
    "finance": ROOT / "frontend/src/features/finance/pages/FinanceManagementProjectsPage.tsx",
    "css": ROOT / "frontend/src/features/management/management-project-tracking.css",
}


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 match, found {count}. "
            "No ERP source files changed."
        )
    return text.replace(old, new, 1)


def region(text, start, end, label):
    if text.count(start) != 1:
        raise RuntimeError(f"{label}: expected exactly one start marker")
    a = text.index(start)
    b = text.find(end, a + len(start))
    if b < 0:
        raise RuntimeError(f"{label}: end marker missing")
    return a, b, text[a:b]


def patch_models(text):
    a, b, part = region(
        text,
        "class ManagementAdditionalProjectRequest(Base):",
        "\nclass ",
        "Management request model",
    ) if "\nclass " in text.split(
        "class ManagementAdditionalProjectRequest(Base):", 1
    )[1] else (None, None, None)

    if part is None:
        a = text.index("class ManagementAdditionalProjectRequest(Base):")
        part = text[a:]
        b = len(text)

    if "project_type" not in part or "pilot_payment_type" not in part:
        raise RuntimeError(
            "Pilot classification columns are missing from the model."
        )

    part = replace_once(
        part,
        "project_name: Mapped[str] = mapped_column(String(255))",
        "project_name: Mapped[str | None] = "
        "mapped_column(String(255), nullable=True)",
        "Optional request project name",
    )

    part = replace_once(
        part,
        "scope_text: Mapped[str] = mapped_column(Text)",
        "scope_text: Mapped[str | None] = "
        "mapped_column(Text, nullable=True)",
        "Optional request scope",
    )

    return text[:a] + part + text[b:]


def patch_router(text):
    if "class ManagementClientRegistrationInput" in text:
        raise RuntimeError("Registration patch is already present")

    # No Literal import is needed.
    marker = '@router.post("", response_model=ManagementClientResponse'

    registration_schema = '''
class ManagementClientRegistrationInput(ManagementClientInput):
    project_type: str = Field(pattern="^(regular|pilot)$")


'''

    text = replace_once(
        text, marker, registration_schema + marker,
        "Registration schema",
    )

    a, b, part = region(
        text,
        marker,
        '@router.put("/{client_id}"',
        "Create Management client endpoint",
    )

    part = replace_once(
        part,
        "payload: ManagementClientInput, request: Request,",
        "payload: ManagementClientRegistrationInput, request: Request,",
        "Registration payload type",
    )

    part = replace_once(
        part,
        "**_values(payload),",
        '**payload.model_dump(exclude={"project_type"}),',
        "Exclude project type from client master",
    )

    initial_request_code = '''
        initial_request = ManagementAdditionalProjectRequest(
            management_client_id=row.id,
            requested_by_id=auth.user.id,
            project_name=None,
            scope_text=payload.work_description,
            project_type=payload.project_type,
            pilot_payment_type=(
                "free" if payload.project_type == "pilot" else None
            ),
            status="PENDING",
        )
        db.add(initial_request)
        db.flush()

        record_audit(
            db,
            event_type="MANAGEMENT_INITIAL_PROJECT_REQUESTED",
            request=request,
            user=auth.user,
            module="management",
            target_type="management_additional_project_request",
            target_id=str(initial_request.id),
            details={
                "management_client_id": row.id,
                "project_type": payload.project_type,
            },
        )

        create_global_notification(
            db,
            event_type="management.additional_project.requested",
            category="approval",
            title=(
                "New Free Pilot Request"
                if payload.project_type == "pilot"
                else "New Regular Project Request"
            ),
            message=(
                f"{row.client_code} - {row.client_name}: "
                f"{payload.project_type.title()} project request "
                f"from {auth.user.full_name}."
            ),
            target_url="/finance/management-projects",
            recipient_roles=["finance"],
            dedupe_key=f"mgmt_add_project_request_{initial_request.id}",
            severity="info",
            requires_action=True,
            metadata={
                "request_id": initial_request.id,
                "client_id": row.id,
                "project_type": payload.project_type,
            },
        )
'''

    part = replace_once(
        part,
        "        db.add(row)\n        db.flush()\n",
        "        db.add(row)\n        db.flush()\n"
        + initial_request_code,
        "Atomic registration and pending request",
    )

    text = text[:a] + part + text[b:]

    # Keep existing frontend API string fields compatible,
    # while allowing NULL values in the database.
    a, b, part = region(
        text,
        "def _additional_request_payload(",
        '@router.get("/additional-project-requests")',
        "Project request response",
    )

    for field in ("project_name", "scope_text"):
        pattern = rf'"{field}":\s*row\.{field}\b'
        replacement = f'"{field}": row.{field} or ""'
        part, count = re.subn(pattern, replacement, part, count=1)

        if count != 1:
            raise RuntimeError(
                f"Cannot update response field: {field}"
            )

    text = text[:a] + part + text[b:]
    return text


def patch_management(text):
    text = replace_once(
        text,
        "  const [form, setForm] = useState<ClientForm>(emptyForm)",
        """  const [form, setForm] = useState<ClientForm>(emptyForm)
  const [registrationProjectType, setRegistrationProjectType] =
    useState<'regular' | 'pilot'>('regular')""",
        "Project Type state",
    )

    text = replace_once(
        text,
        "    setForm({ ...emptyForm })",
        """    setForm({ ...emptyForm })
    setRegistrationProjectType('regular')""",
        "Reset project type on new registration",
    )

    text = replace_once(
        text,
        "        gst_number: form.gst_number.trim().toUpperCase(),",
        """        gst_number: form.gst_number.trim().toUpperCase(),
        ...(editingId === null
          ? { project_type: registrationProjectType }
          : {}),""",
        "Submit new registration project type",
    )

    # Keep the existing CountrySelect component intact.
    country_marker = "<CountrySelect"
    '''gst_marker = (
        '<label className="operations-field">'
        '<span>GST / VAT / SUT</span>'
    )

    if text.count(country_marker) != 1:
        raise RuntimeError("CountrySelect field is not unique")

    a = text.index(country_marker)
    gst_start = text.find(gst_marker, a)

    if gst_start < 0:
        raise RuntimeError("GST field not found after Country"'''
    if text.count(country_marker) != 1:
        raise RuntimeError("CountrySelect field is not unique")

    a = text.index(country_marker)

# Find the GSTIN input using its actual form binding.
    gst_binding = "value={form.gst_number}"
    gst_position = text.find(gst_binding, a)

    if gst_position < 0:
        raise RuntimeError("GSTIN input binding not found after Country")

# Locate the label containing this GSTIN input.
    gst_start = text.rfind("<label", a, gst_position)

    if gst_start < a:
        raise RuntimeError("GSTIN opening label not found")

    gst_end = text.find("</label>", gst_start)
    if gst_end < 0:
        raise RuntimeError("GST closing label not found")
    gst_end += len("</label>")

    original_fields = text[a:gst_end]

    project_type_field = '''
        {editingId === null && (
          <label className="operations-field">
            <span>Project Type *</span>
            <select
              required
              value={registrationProjectType}
              onChange={event =>
                setRegistrationProjectType(
                  event.target.value as 'regular' | 'pilot'
                )
              }
            >
              <option value="regular">Regular Project</option>
              <option value="pilot">Pilot Project</option>
            </select>
          </label>
        )}
'''

    replacement = '''
        <div className={
          editingId === null
            ? 'operations-span-2 mct-country-gst-row'
            : 'operations-span-2 mct-country-gst-row mct-country-gst-row--editing'
        }>
''' + original_fields + project_type_field + '''
        </div>'''

    text = text[:a] + replacement + text[gst_end:]

    text = text.replace(
        "This registration does not create a project or assign a department.",
        "Registration creates a pending Finance request. "
        "Finance creates and assigns the project.",
    )

    text = text.replace(
        "BD, project creation, and Finance approval workflows are not triggered.",
        "A pending project request is sent to Finance automatically. "
        "No actual project is created at registration.",
    )

    return text


def patch_finance(text):
    match = re.search(r"(?m)^type MainTab\s*=.*$", text)

    if match is None:
        raise RuntimeError("Finance MainTab type not found")

    declaration = match.group(0)

    if "'pilot'" in declaration:
        raise RuntimeError("Pilot tab already exists in MainTab")

    semicolon = declaration.rstrip().endswith(";")
    new_declaration = declaration.rstrip().rstrip(";")
    new_declaration += " | 'pilot'"
    if semicolon:
        new_declaration += ";"

    text = replace_once(
        text, declaration, new_declaration,
        "Finance tab type",
    )

    request_tab = (
        "{ id: 'requests', label: 'Project Requests', "
        "icon: FilePlus2 },"
    )

    text = replace_once(
        text,
        request_tab,
        request_tab + "\n"
        "    { id: 'pilot', label: 'Pilot Projects', icon: Layers3 },",
        "Finance Pilot Projects tab",
    )

    helpers = '''
  function pendingForTab(tab: MainTab) {
    return additionalRequests.filter(row =>
      row.status === 'PENDING' &&
      (tab === 'pilot'
        ? row.project_type === 'pilot'
        : row.project_type !== 'pilot')
    ).length
  }

  const requestsForActiveTab = additionalRequests.filter(row =>
    activeTab === 'pilot'
      ? row.project_type === 'pilot'
      : row.project_type !== 'pilot'
  )

'''

    text = replace_once(
        text,
        "  const tabs: Array<{ id: MainTab;",
        helpers + "  const tabs: Array<{ id: MainTab;",
        "Finance request filters",
    )

    text = replace_once(
        text,
        "id === 'requests' && additionalRequests.filter("
        "r => r.status === 'PENDING').length > 0",
        "(id === 'requests' || id === 'pilot') "
        "&& pendingForTab(id) > 0",
        "Finance pending badge condition",
    )

    text = replace_once(
        text,
        "{additionalRequests.filter("
        "r => r.status === 'PENDING').length}</span>",
        "{pendingForTab(id)}</span>",
        "Finance pending badge number",
    )

    a, b, part = region(
        text,
        "{activeTab === 'requests' && <section",
        "{activeTab !== 'requests' && <>",
        "Finance requests panel",
    )

    part = replace_once(
        part,
        "{activeTab === 'requests' && <section",
        "{(activeTab === 'requests' || activeTab === 'pilot') && <section",
        "Regular and Pilot request panels",
    )

    part = part.replace(
        "additionalRequests.filter",
        "requestsForActiveTab.filter",
    )
    part = part.replace(
        "additionalRequests.length",
        "requestsForActiveTab.length",
    )
    part = part.replace(
        "Existing Client – Project Requests",
        "{activeTab === 'pilot' "
        "? 'Pilot Project Requests' : 'Regular Project Requests'}",
    )
    part = part.replace(
        "<strong>{row.project_name}</strong>",
        "<strong>{row.project_name || "
        "'Project details pending Finance'}</strong>",
    )
    part = part.replace(
        "No additional project requests yet.",
        "No matching project requests.",
    )

    pilot_projects = '''
    {activeTab === 'pilot' && (
      <section className="mp-panel">
        <div className="mp-panel-heading">
          <h2>Created Pilot Projects</h2>
          <span>
            {data.projects.filter(row =>
              row.project_type === 'pilot'
            ).length} projects
          </span>
        </div>
        <div className="mp-table-scroll">
          <table className="mp-table">
            <thead>
              <tr>
                <th>Project Code</th>
                <th>Project Name</th>
                <th>Client</th>
                <th>Department</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data.projects
                .filter(row => row.project_type === 'pilot')
                .map(row => (
                  <tr key={row.id}>
                    <td>{row.project_code}</td>
                    <td>{row.project_name}</td>
                    <td>
                      {clientById.get(row.management_client_id)
                        ?.client_name || 'Management Client'}
                    </td>
                    <td>{row.department_label}</td>
                    <td>{row.workflow_status}</td>
                    <td>
                      <button
                        type="button"
                        className="mp-button mp-button-primary mp-button-small"
                        onClick={() => openDetails(row)}
                      >
                        View Project
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    )}

'''

    text = text[:a] + part + pilot_projects + text[b:]

    text = replace_once(
        text,
        "{activeTab !== 'requests' && <>",
        "{activeTab !== 'requests' && activeTab !== 'pilot' && <>",
        "Exclude Pilot tab from regular register",
    )

    text = replace_once(
        text,
        "requests: 'Project Requests' })[activeTab]",
        "requests: 'Project Requests', "
        "pilot: 'Pilot Projects' })[activeTab]",
        "Finance panel heading",
    )

    # Make sure Finance uses the classification of a selected request.
    a, b, part = region(
        text,
        "  function openCreate(client?: ManagementClient",
        "  function openDetails(",
        "Finance project creation setup",
    )

    if "setProjectType(" not in part:
        part = replace_once(
            part,
            "    setCommercial(emptyCommercialForm())",
            """    setProjectType(
      requestRow?.project_type === 'pilot' ? 'pilot' : 'regular'
    )
    setCommercial(emptyCommercialForm())""",
            "Set project type from request",
        )

    if "setPilotPaymentType(" not in part:
        part = replace_once(
            part,
            "    setCommercial(emptyCommercialForm())",
            """    setPilotPaymentType('free')
    setCommercial(emptyCommercialForm())""",
            "Enforce Free Pilot selection",
        )

    text = text[:a] + part + text[b:]

    # Paid Pilot is not an allowed business option.
    text = text.replace(
        '<option value="paid">Paid Pilot</option>',
        "",
    )

    return text


def patch_css(text):
    if ".mct-country-gst-row" in text:
        raise RuntimeError("Country/GST/Project Type CSS already exists")

    return text.rstrip() + """

/* Management Client Registration: aligned Country, GSTIN, Project Type */
.mct-country-gst-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: end;
  grid-column: 1 / -1;
}

.mct-country-gst-row--editing {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mct-country-gst-row > * {
  min-width: 0;
}

.mct-country-gst-row .operations-field input,
.mct-country-gst-row .operations-field select {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: 42px;
}

@media (max-width: 900px) {
  .mct-country-gst-row,
  .mct-country-gst-row--editing {
    grid-template-columns: 1fr;
  }
}
"""


PATCHERS = {
    "models": patch_models,
    "router": patch_router,
    "management": patch_management,
    "finance": patch_finance,
    "css": patch_css,
}


def read_source(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in raw else "\n"

    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    return text, newline, bom


def main():
    changes = {}

    migration = ROOT / "pilot_initial_registration_migration.sql"

    if migration.exists():
        raise RuntimeError(
            "Migration file already exists. "
            "Review the previous patch before applying again."
        )

    # First validate every file without modifying the ERP.
    for key, path in FILES.items():
        source, newline, bom = read_source(path)
        updated = PATCHERS[key](source)

        if updated == source:
            raise RuntimeError(f"No changes produced for {key}")

        if path.suffix == ".py":
            compile(updated, str(path), "exec")

        changes[path] = updated, newline, bom
        print("CHECK OK:", path.relative_to(ROOT))

    if not APPLY:
        print("\nDRY RUN PASSED. No ERP files changed.")
        print("Use --apply only after reviewing this result.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"management_routing_{stamp}"

    # Back up all originals before modifying any source file.
    for path in changes:
        destination = backup / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    try:
        for path, (updated, newline, bom) in changes.items():
            raw = updated.replace("\n", newline).encode("utf-8")
            if bom:
                raw = b"\xef\xbb\xbf" + raw
            path.write_bytes(raw)

        migration.write_text(
            "BEGIN;\n"
            "ALTER TABLE management_additional_project_requests "
            "ALTER COLUMN project_name DROP NOT NULL;\n"
            "ALTER TABLE management_additional_project_requests "
            "ALTER COLUMN scope_text DROP NOT NULL;\n"
            "COMMIT;\n",
            encoding="utf-8",
        )

    except Exception:
        for path in changes:
            shutil.copy2(backup / path.relative_to(ROOT), path)

        if migration.exists():
            migration.unlink()

        raise

    print("\nSOURCE PATCH INSTALLED")
    print("Backup:", backup)
    print("Migration:", migration)
    print("DATABASE MIGRATION NOT EXECUTED.")
    print("Validate frontend build before deploying.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP:", exc, file=sys.stderr)
        sys.exit(1)
