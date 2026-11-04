"""Build a credential-free summary from the saved QA evidence."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def junit(filename):
    root = ET.parse(HERE / filename).getroot()
    counts = Counter()
    modules = {}
    failures = []
    skipped = []
    for case in root.iter("testcase"):
        module = case.get("classname", "")
        name = case.get("name", "")
        error = case.find("failure")
        if error is None:
            error = case.find("error")
        skip = case.find("skipped")
        outcome = "failed" if error is not None else "skipped" if skip is not None else "passed"
        counts[outcome] += 1
        module_counts = modules.setdefault(module, Counter())
        module_counts[outcome] += 1
        if error is not None:
            failures.append({"module": module, "test": name,
                             "message": error.get("message", "")})
        if skip is not None:
            skipped.append({"module": module, "test": name,
                            "reason": skip.get("message", "")})
    return {"counts": dict(counts), "total": sum(counts.values()),
            "modules": modules, "failures": failures, "skipped": skipped}


deep_pass = (HERE / "deep-final-results.xml").exists()
frontend = json.loads((HERE / ("deep-frontend-results.json" if deep_pass else "frontend-results.json")).read_text())
live = json.loads((HERE / "live-smoke-results.json").read_text())
report = {
    "tested_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
    "overall": "Not fully passing; automated failures and browser verification gaps remain.",
    "scope": "Local Docker deployment and isolated backend SQLite regression tests.",
    "backend_final": junit("deep-final-results.xml" if deep_pass else "backend-final-results.xml"),
    "backend_baseline": junit("backend-baseline-results.xml")["counts"],
    "registration_fix_verification": junit("registration-results.xml")["counts"],
    "frontend": {"passed": sum(row["passed"] for row in frontend),
                 "total": len(frontend), "checks": frontend},
    "live_smoke": {"passed": sum(row["passed"] for row in live),
                   "total": len(live), "checks": live},
    "fixes": [
        {"issue": "Asset assignment, vendor return and handover dates defaulted to yesterday before 05:30 IST.",
         "change": "Use an explicit Asia/Kolkata calendar date for these form defaults.",
         "verification": "Six midnight, month, year and leap-day boundary checks; production build and type checks passed."},
        {"issue": "The frontend lint command targeted a root TypeScript config with no source files.",
         "change": "Type-check both the app and Vite configuration explicitly.",
         "verification": "Corrected lint command passed."},
        {"issue": "The existing local test-mode MFA confirmation activated the user but left Employee Master pending.",
         "change": "Set the linked Employee Master account status to active in the same activation transaction.",
         "verification": "All seven registration checks passed, including explicit normal and local test-mode activation."},
    ],
    "remaining_failure_analysis": [
        {"group": "Legacy end-to-end tests", "count": 27,
         "evidence": "Login fixtures fail with 401, registration fixtures lack eligible Employee Master records, and local-backup configuration differs. These failures block the workflows from reaching their assertions.",
         "next_step": "Make seed settings and application initialization function-scoped; create eligible employee fixtures and explicitly configure optional modules."},
        {"group": "Privileged authentication tests", "count": 2,
         "evidence": "Tests expect pending_mfa while the existing deployment enables local test authentication bypass.",
         "next_step": "Set the intended authentication mode explicitly in each test instead of inheriting Docker configuration."},
        {"group": "Legacy project manager ownership test", "count": 1,
         "evidence": "V6 test expects Finance project creation to set a PM. Current service deliberately reserves PM assignment for BD.",
         "next_step": "Update the legacy test setup to assign the PM through the current authorized BD workflow."},
        {"group": "QC/QA correction workflow expectations", "count": 7,
         "evidence": "Some tests omit production correction before repeated review; others date correction sessions in October but record rejection at the current November time. The service rejects these with a correction-required error.",
         "next_step": "Use chronological rejection/correction/review timestamps and exercise the correction-completion step before repeating review; retain the current workflow guard."},
        {"group": "Time-dependent allocation/reporting fixtures", "count": 3,
         "evidence": "Fixtures use October 2026 targets with real current completion timestamps in November, but expect on-time completion.",
         "next_step": "Use explicit completion timestamps or a fixed test clock, then recheck deadline and productivity exports."},
        {"group": "Retired sample notifications", "count": 3,
         "evidence": "Older tests expect sample notifications that the current obsolete-sample retirement behavior suppresses.",
         "next_step": "Align legacy notification expectations with the documented current workflow and retain retirement regression coverage."},
    ],
    "limitations": [
        "Browser access host was unavailable. Visual layout, interactive clicks, mobile layouts and browser console errors were not verified.",
        "Frontend source-verification scripts do not substitute for interactive browser tests.",
        "SMTP delivery, real external integrations, backup restore and deployment to cPanel were not exercised.",
        "Backend mutation tests used isolated SQLite databases, not the live PostgreSQL database. Live smoke checks only read business data after login.",
        "Vite still reports large JavaScript chunks; the main chunk is approximately 2.68 MB minified. Performance was not measured.",
    ],
    "commands": {
        "backend": "docker compose exec -T -e TMPDIR=/dev/shm -e PYTHONUNBUFFERED=1 backend python -m pytest tests -q --tb=short",
        "frontend": "Run npm run lint, npm run build, and every test:* script from frontend/.",
        "live_smoke": "backend/.venv/Scripts/python.exe artifacts/qa/live_smoke.py",
    },
}
if deep_pass:
    source = json.loads((HERE / "source-inventory.json").read_text(encoding="utf-8"))
    runtime = json.loads((HERE / "runtime-route-inventory.json").read_text(encoding="utf-8"))
    source_modules = {}
    for item in source["files"]:
        parts = item["path"].split("/")
        group = "/".join(parts[:4]) if "/modules/" in item["path"] or "/features/" in item["path"] else "/".join(parts[:3])
        module = source_modules.setdefault(group, {"files": 0, "lines": 0})
        module["files"] += 1
        module["lines"] += item["lines"]
    report["source_audit"] = {
        "files_scanned": len(source["files"]),
        "lines_scanned": sum(item["lines"] for item in source["files"]),
        "python_syntax_errors": source["syntax_errors"],
        "flagged_eval_exec_pickle_or_shell_calls": source["dangerous_call_review"],
        "source_by_module": source_modules,
        "effective_http_operations": runtime["operations"],
        "method": "Every source file read for inventory and automated scan; Python AST parsing, strict TypeScript checks, route registration/authentication tests, and targeted manual review of critical handlers and workflow transitions.",
        "limits": "This is not a manual correctness proof of every line, nor a measurement of executed-line coverage.",
    }
    report["previous_backend_final"] = junit("backend-final-results.xml")["counts"]
    report["new_fix_verification"] = junit("deep-fix-results.xml")
    report["fixes"].extend([
        {"issue": "Business financial history was readable by an ordinary employee who supplied another record ID.",
         "change": "Enforce overview-equivalent role, project-manager ownership and hidden-project restrictions before returning history.",
         "verification": "Reproduced a 200 financial-data response for an employee before the fix; all ten new role/ownership checks pass after the fix."},
        {"issue": "A duplicate Payables vendor bill raised an unhandled IntegrityError and returned HTTP 500.",
         "change": "Rollback and return HTTP 409 for uniqueness failures during flush, as well as commit.",
         "verification": "Reproduced the 500 before the fix. Added duplicate-bill and dual-approval/partial-payment lifecycle regressions."},
        {"issue": "Software Team could open IT Work but could not edit it despite having Admin-equivalent permission.",
         "change": "Apply the shared role permission helper to IT Work updates.",
         "verification": "Reproduced the 403 before the fix. IT, Admin and Software Team can edit; Management remains read-only."},
        {"issue": "UTC-based date defaults remained in seventeen additional frontend files.",
         "change": "Use India calendar dates in finance, commercial, travel, drone, asset, profile, procurement and work forms; correct current-month defaults in both finance dashboards.",
         "verification": "All frontend scripts, strict type checks, production build and six date-boundary checks passed."},
        {"issue": "Regression tests inherited deployment secrets and auth/demo settings, and cached startup state after resetting their database.",
         "change": "Pin test-only secrets, disable optional demo seeding/background tasks for tests, reset initialization with each schema, and use explicit function-scoped end-to-end settings.",
         "verification": "The end-to-end suite now gets past login and reaches real workflow assertions; production settings are unchanged."},
    ])
    def category(failure):
        module, message = failure["module"], failure["message"]
        if "test_end_to_end" in module:
            return "Legacy end-to-end workflow assertions and remaining fixture gaps"
        if "correction before review" in message:
            return "Correction/review ordering expectations and chronological test timestamps"
        if "test_production_master_excel" in module:
            return "Date-dependent allocation and productivity expectations"
        if "test_client_project_master_v6" in module:
            return "Legacy Finance-owned PM assignment expectation"
        if "test_sample_requests" in module or "test_technical_routing" in module:
            return "Retired sample notification expectations"
        return "Requires further investigation"
    grouped = Counter(category(failure) for failure in report["backend_final"]["failures"])
    report["remaining_failure_analysis"] = [
        {"group": name, "count": count,
         "next_step": "Review the exact failure evidence against the current authorized workflow; repair obsolete fixtures and investigate any remaining product defect without weakening access or transition guards."}
        for name, count in grouped.items()
    ]
    report["limitations"].append("The full suite and focused fix checks are reported separately; four additional IT Work role cases are covered in the focused verification run.")
(HERE / "test-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"backend": report["backend_final"]["counts"],
                  "frontend": report["frontend"]["passed"],
                  "live": report["live_smoke"]["passed"]}))
