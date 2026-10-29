#!/usr/bin/env python3
"""Read-only NakshaTech Pilot Project integration preflight.

Run from the ERP repository root:
    python NAKSHA_PILOT_INTEGRATION_PREP.py --scan

Finds project creation, workflow, finance and notification integration points.
Copies only relevant source files to a LOCALAPPDATA review directory, without
changing application files, database, git, or Docker.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PATTERNS = {
    "bd_clients": re.compile(r"Create Project|View Client|Client Management|Client Register", re.I),
    "project_creation": re.compile(r"create.project|project.create|@router\.post\([^\n]*projects|def create_project", re.I),
    "workflow": re.compile(r"qa.?qc|quality.check|deliverable|department.assignment|project.stage|workflow", re.I),
    "finance": re.compile(r"invoice|receivable|payment.due|project.amount|billable", re.I),
    "notifications": re.compile(r"notification|notify.*project", re.I),
}
IGNORE_PARTS = {"node_modules", "dist", "build", ".git", ".venv", "venv", "__pycache__", "migrations", "alembic", "backups", "test", "tests"}
SUFFIXES = {".py", ".tsx", ".ts"}
MAX_FILE_SIZE = 450_000
MAX_COPY_FILES = 35


def root_check(root: Path) -> None:
    if not (root / "frontend" / "src").is_dir() or not (root / "backend" / "app").is_dir():
        raise SystemExit("REFUSED: run in ERP root with frontend/src and backend/app")


def scan(root: Path) -> tuple[list[dict], list[tuple[int, Path]]]:
    matches = []
    candidates = []
    for top in (root / "frontend" / "src", root / "backend" / "app"):
        for path in top.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            rel = path.relative_to(root)
            if any(p.lower() in IGNORE_PARTS for p in rel.parts) or path.stat().st_size > MAX_FILE_SIZE:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            lines = text.splitlines()
            hits = []
            for idx, line in enumerate(lines, 1):
                types = [name for name, rex in PATTERNS.items() if rex.search(line)]
                if types:
                    hits.append({"line": idx, "categories": types, "preview": line.strip()[:180]})
            if not hits:
                continue
            categories = set(category for hit in hits for category in hit["categories"])
            score = len(categories) * 10 + min(len(hits), 20)
            if "project" in path.name.lower() or "bd" in str(rel).lower() or "client" in path.name.lower():
                score += 15
            matches.append({"file": str(rel), "categories": sorted(categories), "hits": hits[:24], "score": score})
            candidates.append((score, path))
    matches.sort(key=lambda x: (-x["score"], x["file"]))
    candidates.sort(key=lambda x: (-x[0], str(x[1])))
    return matches, candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true", help="Read-only source discovery and safe copy")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="ERP root (defaults to current directory)")
    args = parser.parse_args()
    if not args.scan:
        parser.error("Specify --scan. This tool intentionally does not patch unknown application code.")
    root = args.root.resolve()
    root_check(root)
    matches, candidates = scan(root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    out = local / "NakshaTech" / "pilot-integration-review" / stamp
    out.mkdir(parents=True, exist_ok=False)
    selected = candidates[:MAX_COPY_FILES]
    for _, source in selected:
        relative = source.relative_to(root)
        target = out / "sources" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = {
        "project_root": str(root),
        "created_at": stamp,
        "intent": "Pilot Project, non-billable, 2% client sample, normal workflow, finance/software notified, BD conversion only after delivery and satisfied feedback",
        "scan_only": True,
        "source_files_copied": [str(path.relative_to(root)) for _, path in selected],
        "matches": matches,
        "required_rules": [
            "Pilot creation available from client, using existing department workflow",
            "No client billing or internal pilot expense posting",
            "Assigned departments receive normal project tasks; Finance and Software receive info notifications",
            "Conversion unavailable until all workflow gates, QA, delivery, and satisfied feedback",
            "BD manually confirms conversion via normal paid-project creation",
            "Pilot audit/history stays immutable and linked to commercial project",
            "No regression to existing regular projects",
        ],
    }
    (out / "scan_report.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    overview = ["NAKSHA PILOT INTEGRATION REVIEW", f"Project: {root}", "READ-ONLY: No project files/database/Docker changed", "", "Top candidate files:"]
    overview += [f"- {path.relative_to(root)}" for _, path in selected]
    overview += ["", "Next: Share scan_report.json and the copied sources from this folder."]
    (out / "README.txt").write_text("\n".join(overview) + "\n", encoding="utf-8")
    print("SCANNED:", len(matches), "files with relevant references")
    print("COPIED:", len(selected), "candidate source files (read-only copies)")
    print("REVIEW DIRECTORY:", out)
    print("REPORT:", out / "scan_report.json")
    for entry in matches[:12]:
        print(" -", entry["file"], "[", ", ".join(entry["categories"]), "]")
    print("NO APPLICATION OR DATABASE CHANGES MADE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
