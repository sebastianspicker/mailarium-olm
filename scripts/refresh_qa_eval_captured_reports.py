#!/usr/bin/env python3
"""Refresh or check the captured QA eval reports tracked under docs/agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh the captured QA eval reports declared in docs/agent.",
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
        "--docs-agent-dir",
        default="docs/agent",
        help="Docs agent directory containing captured QA and golden artifacts (default: docs/agent).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from src.legal_support_acceptance_goldens import (
        FULL_PACK_GOLDEN_ALIAS,
        LEGAL_SUPPORT_GOLDEN_SCENARIOS,
        refresh_legal_support_goldens,
    )
    from src.qa_eval_captured_artifacts import CAPTURED_EVAL_SCENARIOS, refresh_captured_eval_reports

    parser = _build_parser()
    args = parser.parse_args(argv)
    available_scenarios = [scenario.name for scenario in CAPTURED_EVAL_SCENARIOS] + [
        FULL_PACK_GOLDEN_ALIAS,
        *[scenario.name for scenario in LEGAL_SUPPORT_GOLDEN_SCENARIOS],
    ]

    if args.list:
        print(json.dumps(available_scenarios, indent=2))
        return 0

    docs_agent_dir = Path(args.docs_agent_dir).expanduser()
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

    qa_eval_names = (
        {name for name in requested if name in {scenario.name for scenario in CAPTURED_EVAL_SCENARIOS}} if requested else None
    )
    golden_names = (
        {
            name
            for name in requested
            if name == FULL_PACK_GOLDEN_ALIAS or name in {scenario.name for scenario in LEGAL_SUPPORT_GOLDEN_SCENARIOS}
        }
        if requested
        else None
    )

    outcomes = []
    if requested is None or qa_eval_names:
        outcomes.extend(
            refresh_captured_eval_reports(
                docs_agent_dir=docs_agent_dir,
                scenario_names=qa_eval_names,
                check_only=args.check,
            )
        )
    if requested is None or golden_names:
        outcomes.extend(
            refresh_legal_support_goldens(
                docs_agent_dir=docs_agent_dir,
                scenario_names=golden_names,
                check_only=args.check,
            )
        )
    print(json.dumps(outcomes, indent=2))

    if args.check and any(item["status"] == "updated" for item in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
