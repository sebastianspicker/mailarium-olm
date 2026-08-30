#!/usr/bin/env python3
"""Enforce independent branch-coverage floors for critical Mailarium seams."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Floors are derived from the focused composition suite.  They intentionally
# protect exercised control flow per module, instead of letting high coverage
# in a small facade conceal an untested storage or adapter boundary.
CRITICAL_BRANCH_FLOORS = {
    "mailarium/runtime.py": 70.0,
    "mailarium/mailbox/sync_service.py": 40.0,
    "mailarium/investigation/answer_context/workflow.py": 50.0,
    "mailarium/interfaces/mcp/tools/search.py": 35.0,
    "mailarium/archive/database.py": 40.0,
    "mailarium/ingestion/ingest_embed_pipeline.py": 35.0,
    "mailarium/ingestion/mailbox_ingest.py": 35.0,
    "mailarium/web_app.py": 50.0,
}


def _branch_coverage(summary: dict[str, object]) -> float:
    """Return a percentage for executable branch arcs, treating no arcs as full coverage."""
    total = int(summary.get("num_branches", 0) or 0)
    covered = int(summary.get("covered_branches", 0) or 0)
    return 100.0 if total == 0 else (covered * 100.0 / total)


def check_coverage(payload: dict[str, object]) -> list[str]:
    """Return human-readable threshold failures for the expected coverage JSON payload."""
    files = payload.get("files")
    if not isinstance(files, dict):
        return ["coverage JSON did not contain a files mapping"]
    failures: list[str] = []
    for path, floor in CRITICAL_BRANCH_FLOORS.items():
        report = files.get(path)
        if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
            failures.append(f"{path}: missing from coverage data (required branch coverage >= {floor:.1f}%)")
            continue
        actual = _branch_coverage(report["summary"])
        print(f"{path}: branch coverage {actual:.1f}% (minimum {floor:.1f}%)")
        if actual < floor:
            failures.append(f"{path}: branch coverage {actual:.1f}% is below {floor:.1f}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    """Load coverage JSON and fail if any independent critical module is below its floor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"could not read coverage JSON: {exc}")
    failures = check_coverage(payload)
    if failures:
        print("Critical branch-coverage gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Critical branch-coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
