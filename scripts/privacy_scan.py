#!/usr/bin/env python3
"""Compatibility facade for the repository publication privacy scan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Direct script execution puts ``scripts/`` ahead of the package root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mailarium.privacy_scan_rules import Finding  # noqa: E402
from mailarium.privacy_scan_service import scan as _scan  # noqa: E402

__all__ = ("Finding", "main", "scan")


def scan(*, include_untracked: bool = True, include_history: bool = False) -> list[Finding]:
    """Scan the live ``REPO_ROOT`` to preserve monkeypatchable facade behavior."""
    return _scan(REPO_ROOT, include_untracked=include_untracked, include_history=include_history)


def main(argv: list[str] | None = None) -> int:
    """Select scan scope, render findings, and fail when risks remain."""
    parser = argparse.ArgumentParser(description="Scan for publication-risk private artifacts without printing secrets.")
    parser.add_argument("--tracked-only", action="store_true", help="Only scan tracked files.")
    parser.add_argument("--include-history", action="store_true", help="Also report risky paths seen in git history.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    findings = scan(include_untracked=not args.tracked_only, include_history=args.include_history)
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(f"{finding.category}\t{finding.path}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
