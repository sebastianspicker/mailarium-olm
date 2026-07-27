#!/usr/bin/env python3
"""Refresh or check captured QA eval reports stored with test fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts._bootstrap import add_repository_root
except ModuleNotFoundError:  # Direct execution resolves helpers from the script directory.
    from _bootstrap import add_repository_root

ROOT = add_repository_root(__file__)


def _build_parser() -> argparse.ArgumentParser:
    """Define scenario selection, check-only, listing, and fixture-root options for report refreshes."""
    parser = argparse.ArgumentParser(
        description="Refresh the captured QA eval reports declared in tests/fixtures/qa_eval.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="Refresh only the named captured scenario. Repeat for multiple scenarios.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the saved captured reports already match the refresh output.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the named captured scenarios and exit.",
    )
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/qa_eval",
        help="Directory containing captured QA evaluation fixtures (default: tests/fixtures/qa_eval).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate requested scenarios, refresh or compare captured reports, and signal stale fixtures in check mode."""
    from mailarium.qa_eval_captured_artifacts import CAPTURED_EVAL_SCENARIOS, refresh_captured_eval_reports

    parser = _build_parser()
    args = parser.parse_args(argv)
    available_scenarios = [scenario.name for scenario in CAPTURED_EVAL_SCENARIOS]

    if args.list:
        print(json.dumps(available_scenarios, indent=2))
        return 0

    fixtures_dir = Path(args.fixtures_dir).expanduser()
    requested = set(args.scenarios) if args.scenarios else None
    if requested is not None:
        unknown = sorted(name for name in requested if name not in set(available_scenarios))
        if unknown:
            print(
                json.dumps(
                    {
                        "error": "unknown_scenarios",
                        "unknown": unknown,
                        "valid_scenarios": available_scenarios,
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2

    outcomes = refresh_captured_eval_reports(
        fixtures_dir=fixtures_dir,
        scenario_names=requested,
        check_only=args.check,
    )
    print(json.dumps(outcomes, indent=2))

    if args.check and any(item["status"] == "updated" for item in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
