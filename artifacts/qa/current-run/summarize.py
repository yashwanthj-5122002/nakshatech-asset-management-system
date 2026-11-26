"""Summarize this QA run without reading credentials or business records."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def read_json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8-sig"))


root = ET.parse(HERE / "backend-results.xml").getroot()
counts = Counter()
modules = {}
failures = []
skipped = []
for case in root.iter("testcase"):
    module = case.get("classname", "")
    failure = case.find("failure")
    if failure is None:
        failure = case.find("error")
    skip = case.find("skipped")
    outcome = "failed" if failure is not None else "skipped" if skip is not None else "passed"
    counts[outcome] += 1
    modules.setdefault(module, Counter())[outcome] += 1
    if failure is not None:
        failures.append({"module": module, "test": case.get("name"),
                         "message": failure.get("message", "")})
    if skip is not None:
        skipped.append({"module": module, "test": case.get("name"),
                        "reason": skip.get("message", "")})

frontend = read_json("frontend-results.json") + read_json("frontend-extra-results.json")
report = {
    "tested_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
    "scope": "All 99 backend test files; frontend type check, production build, 17 verification scripts; local health probes.",
    "backend": {"total": sum(counts.values()), "counts": dict(counts),
                "test_modules": modules, "failures": failures, "skipped": skipped},
    "priority_findings": [
        {"priority": "high", "finding": "Final production completion records the full planned quantity while build_item_rows sums all closed production sessions. Earlier partial quantities are therefore added again.",
         "example": "test_full_file_level_e2e_and_read_model_consistency expected 3.0, got 5.2.",
         "locations": ["backend/app/modules/operations/production_items.py:1018", "backend/app/modules/operations/production_items.py:1383"]},
        {"priority": "high", "finding": "27 tests fail because the completion policy now requires planned quantity, while older file fixtures omit it. Confirm the mandatory-planning contract and align imports, validation, and fixtures.",
         "location": "backend/app/modules/operations/production_items.py:74"},
        {"priority": "medium", "finding": "26 full-run failures hit end <= start. Immediate sequential UTC reads on this Windows interpreter often return the same timestamp. These failures receive a separate rerun using the original SQLite settings.",
         "location": "backend/app/modules/operations/production_items.py:932"},
        {"priority": "medium", "finding": "Legacy end-to-end fixtures conflict with current registration eligibility, approval-recipient fields, validation responses, export filename and replacement approval behavior. Drone import also returns no batch in one test."},
        {"priority": "medium", "finding": "Three sample-request notification tests and the legacy Finance-owned PM-assignment test conflict with newer workflow behavior; review expectations before changing business rules."},
    ],
    "frontend": {"checks": frontend,
                 "passed": sum(check["exitCode"] == 0 for check in frontend),
                 "failed": sum(check["exitCode"] != 0 for check in frontend),
                 "lint": "passed",
                 "build": read_json("frontend-build-exit.json"),
                 "build_warning": "Large JavaScript chunks: main bundle 2,766.60 kB; world geography 1,427.47 kB; three.js 595.30 kB (minified).",
                 "failure_analysis": [
                     {"script": "verify-dashboard-drawer-layout-focus.mjs",
                      "finding": "Requires a literal header class; component now uses a template literal with conditional classes. Source-check mismatch, not demonstrated UI breakage."},
                     {"script": "verify-dashboard-drawer-visual-toggle.mjs",
                      "finding": "Requires a literal header-actions class; component retains it within a template literal. Source-check mismatch, not demonstrated UI breakage."},
                     {"script": "verify-dashboard-drilldown.mjs",
                      "finding": "Forbids every asset-register Link, including the empty-state Open Asset Register action; KPI drawer handlers remain present. Overbroad check."},
                 ]},
    "source_checks": read_json("source-checks.json"),
    "route_inventory": read_json("route-inventory.json"),
    "live_health": read_json("live-health.json"),
    "limitations": [
        "The completed backend run disabled SQLite disk-flush durability only on conftest's UUID-named disposable database in the system temporary directory. Transactions and schema isolation remained active. Crash durability was not tested.",
        "The local Docker Compose status command returned no running services. Default frontend, backend and nginx ports were unavailable.",
        "No interactive browser, visual, mobile, or real PostgreSQL workflow verification was completed.",
        "Frontend source-string verifiers do not establish working browser behavior.",
        "The backend suite uses disposable SQLite databases; external delivery, MinIO, Redis, backup restoration and cPanel deployment are not established by this run.",
        "Line/branch coverage was not measured; coverage.py and pytest-cov are not installed.",
        "Some test modules lack direct imports of application modules; transitive/API coverage requires separate measurement.",
        "The assigned-PM happy-path assertion in test_unassigned_pm_project_access_rejected_at_project_360 ends with 'if False else True', so that assertion does not verify access.",
    ],
    "application_changes": "None. This run only added QA evidence under artifacts/qa/current-run and generated ignored frontend build outputs.",
}
latest = {}
for case in root.iter("testcase"):
    failed = case.find("failure") is not None or case.find("error") is not None
    latest[(case.get("classname"), case.get("name"))] = (
        "failed" if failed else "skipped" if case.find("skipped") is not None else "passed"
    )
retry_path = HERE / "backend-timing-recheck.xml"
if retry_path.exists():
    retry_counts = Counter()
    retry_failures = []
    for case in ET.parse(retry_path).getroot().iter("testcase"):
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        outcome = "failed" if failure is not None else "passed"
        retry_counts[outcome] += 1
        latest[(case.get("classname"), case.get("name"))] = outcome
        if failure is not None:
            retry_failures.append({"module": case.get("classname"), "test": case.get("name"),
                                   "message": failure.get("message", "")})
    report["timing_recheck_original_sqlite_settings"] = {
        "counts": dict(retry_counts), "failures": retry_failures,
        "note": "Same full collection; only the 26 timing failures selected. Four passed, 19 retained equal/invalid-time failures, two exposed quantity differences and one exposed missing planned quantity.",
    }
report["latest_result_per_backend_test"] = {
    "counts": dict(Counter(latest.values())),
    "note": "Combines the complete 636-test run with the latest results for the 26 timing rechecks; this is not a second complete suite run.",
}
patch_path = HERE / "patch-tests.xml"
if patch_path.exists():
    patch_root = ET.parse(patch_path).getroot()
    report["patch_utilities"] = {"total": len(list(patch_root.iter("testcase"))),
                                 "failed": len(list(patch_root.iter("failure"))),
                                 "limitation": "The installer source-snapshot smoke test returns without assertions when the optional repo snapshot directory is absent."}
(HERE / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"backend": dict(counts), "backend_total": sum(counts.values()),
                  "frontend_passed": report["frontend"]["passed"],
                  "frontend_failed": report["frontend"]["failed"],
                  "failing_test_modules": {name: value for name, value in modules.items() if value["failed"]}}, indent=2))
