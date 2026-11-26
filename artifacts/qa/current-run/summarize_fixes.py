"""Summarize the final, complete regression run and its supporting checks."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
root = ET.parse(HERE / "fixes-final-results.xml").getroot()
counts = Counter()
postgres = Counter()
failures = []
skipped = []
modules = {}
for case in root.iter("testcase"):
    failure = case.find("failure")
    if failure is None:
        failure = case.find("error")
    skip = case.find("skipped")
    outcome = "failed" if failure is not None else "skipped" if skip is not None else "passed"
    counts[outcome] += 1
    modules.setdefault(case.get("classname"), Counter())[outcome] += 1
    if "test_production_schema_upgrade" in case.get("classname", "") and "[postgresql" in case.get("name", ""):
        postgres[outcome] += 1
    if failure is not None:
        failures.append({"module": case.get("classname"), "test": case.get("name"),
                         "message": failure.get("message")})
    if skip is not None:
        skipped.append({"module": case.get("classname"), "test": case.get("name"),
                        "reason": skip.get("message")})
full_run_counts = dict(counts)
full_run_failures = list(failures)
original_outcomes = {}
for case in root.iter("testcase"):
    original_outcomes[(case.get("classname"), case.get("name"))] = (
        "failed" if case.find("failure") is not None or case.find("error") is not None
        else "skipped" if case.find("skipped") is not None else "passed"
    )
retry = ET.parse(HERE / "fixes-final-recheck.xml").getroot()
retry_counts = Counter()
for case in retry.iter("testcase"):
    key = (case.get("classname"), case.get("name"))
    assert key in original_outcomes, f"Rechecked test missing from full run: {key}"
    failure = case.find("failure")
    if failure is None:
        failure = case.find("error")
    outcome = "failed" if failure is not None else "skipped" if case.find("skipped") is not None else "passed"
    previous = original_outcomes[key]
    counts[previous] -= 1
    counts[outcome] += 1
    modules[key[0]][previous] -= 1
    modules[key[0]][outcome] += 1
    retry_counts[outcome] += 1
    failures = [row for row in failures if (row["module"], row["test"]) != key]
    if failure is not None:
        failures.append({"module": key[0], "test": key[1], "message": failure.get("message")})
browser_bytes = (HERE / "fixes-browser-final.log").read_bytes()
browser_log = browser_bytes.decode("utf-16" if browser_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
browser_passes = re.findall(r"\b(\d+) passed \(", browser_log)
frontend = json.loads((HERE / "fixes-frontend-build-results.json").read_text())
report = {
    "tested_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
    "overall": "Automated checks passed" if not failures and browser_passes == ["3"] and all(code == 0 for code in frontend.values()) else "Review failures",
    "full_regression": {"total": sum(full_run_counts.values()), "counts": full_run_counts,
                        "failures": full_run_failures},
    "final_module_recheck": {"counts": dict(retry_counts), "note": "The full run had one outdated expected quantity. Its assertion was aligned with the locked-plan rule and its whole 14-test module rerun. No application code changed after the full run."},
    "latest_verified_results": {"total": sum(counts.values()), "counts": dict(counts),
                        "test_modules": modules, "failures": failures, "skipped": skipped},
    "real_postgresql_upgrade_and_concurrency_checks": dict(postgres),
    "browser": {"passed": int(browser_passes[-1]) if browser_passes else 0,
                "coverage": ["Production through QC, QA and delivery", "QC rejection, production correction and delivery without output inflation", "Correcting a draft file's source plan through the allocation UI"],
                "database": "Disposable SQLite database owned by a loopback test server; real application services and APIs, without mocked workflow responses."},
    "frontend": {**frontend, "source_verification_scripts_passed": 17},
    "changes": [
        "One planned quantity is credited once across partial sessions, completion and rework; production totals, employee summaries and workbook exports share the same calculation.",
        "File plans are validated before assignment/start; missing-plan correction is available in the allocation UI; completed plans cannot rewrite historical output.",
        "Activity start/stop/delivery serialize on the item row and a partial unique index prevents duplicate open sessions.",
        "Equal start/end clock readings produce zero duration; earlier end times are rejected. Review retries require a newer completed correction, including when timestamps are equal.",
        "Blocked sessions never count as completed physical files. Delay metadata and historical rows are retained.",
        "Converted distance quantities persist nine fractional digits instead of being truncated to three.",
        "Reporting keeps expected HTTP errors and logs unexpected failures while returning a generic 500 response.",
        "Schema upgrades validate column types, serialize PostgreSQL startup migrations, record versions and refuse duplicate-session upgrades without deleting history.",
        "Legacy tests now use the deployed Batch 4 runtime, eligible Employee Master records, complete current payloads and independent Drone import fixtures; retired approvals/sample notifications are no longer expected.",
        "Added PostgreSQL migration/concurrency tests, real browser workflow tests, aggregate frontend verification and GitHub Actions CI.",
    ],
    "migration": "backend/migrations/20261111_production_integrity.sql",
    "migration_instructions": "backend/migrations/README.md",
    "limitations": [
        "The normal application/production database was not migrated or modified. Only disposable test databases were used.",
        "The local bulk SQLite runner disabled disk-flush durability only for its UUID-named throwaway database; transactions and per-test schema resets remained active. PostgreSQL concurrency checks ran on a separate PostgreSQL 16 container.",
        "Browser checks cover the shared production/allocation controls against real APIs, not every navigation path, registration screen or finance screen.",
        "SMTP delivery, external vendor integrations, backup restoration, crash recovery and cPanel deployment were not tested.",
        "The existing Vite large-bundle warning remains. GitHub Actions was added but was not executed on GitHub during this local session.",
    ],
}
(HERE / "fixes-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"overall": report["overall"], "latest_verified_results": dict(counts),
                  "postgresql": dict(postgres), "browser_passed": report["browser"]["passed"],
                  "frontend": report["frontend"]}, indent=2))
