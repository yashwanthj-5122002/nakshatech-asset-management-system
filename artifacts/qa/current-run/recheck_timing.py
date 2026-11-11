"""Recheck timing failures with the suite's original SQLite settings."""
import json
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
report = json.loads((HERE / "report.json").read_text(encoding="utf-8"))
targets = {
    (failure["module"], failure["test"])
    for failure in report["backend"]["failures"]
    if "End time must be after" in failure["message"]
}


class SelectTimingFailures:
    def pytest_collection_modifyitems(self, config, items):
        selected, deselected = [], []
        for item in items:
            module = item.module.__name__
            if any(module.endswith(name.split(".")[-1]) and item.name == test
                   for name, test in targets):
                selected.append(item)
            else:
                deselected.append(item)
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


raise SystemExit(pytest.main([
    str(ROOT / "backend/tests"), "-v", "--tb=short",
    f"--junitxml={HERE / 'backend-timing-recheck.xml'}",
], plugins=[SelectTimingFailures()]))
