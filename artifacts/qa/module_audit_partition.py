"""Partition after full collection; keep identical imports and private databases."""
import json
import os
from pathlib import Path

def pytest_collection_modifyitems(config, items):
    index = int(os.environ['ERP_AUDIT_SHARD'])
    count = int(os.environ['ERP_AUDIT_SHARDS'])
    selected = [item for ordinal, item in enumerate(items) if ordinal % count == index]
    deselected = [item for ordinal, item in enumerate(items) if ordinal % count != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected

def pytest_runtest_logreport(report):
    if report.when == 'call' or (report.when == 'setup' and report.outcome != 'passed'):
        target = Path(os.environ['ERP_AUDIT_PROGRESS'])
        with target.open('a', encoding='utf-8') as output:
            output.write(json.dumps(dict(nodeid=report.nodeid, phase=report.when,
                                         outcome=report.outcome, duration=report.duration)) + '\n')
