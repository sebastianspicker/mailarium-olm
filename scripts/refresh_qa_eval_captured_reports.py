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

    qa_eval_names, golden_names = _selected_scenario_names(
        requested, CAPTURED_EVAL_SCENARIOS, LEGAL_SUPPORT_GOLDEN_SCENARIOS, FULL_PACK_GOLDEN_ALIAS
    )
    outcomes = _refresh_outcomes(
        requested=requested,
        qa_names=qa_eval_names,
        golden_names=golden_names,
        docs_agent_dir=docs_agent_dir,
        check_only=args.check,
        refresh_qa=refresh_captured_eval_reports,
        refresh_goldens=refresh_legal_support_goldens,
    )
    print(json.dumps(outcomes, indent=2))

    if args.check and any(item["status"] == "updated" for item in outcomes):
        return 1
    return 0


def _selected_scenario_names(requested, qa_scenarios, golden_scenarios, full_pack_alias):
    if requested is None:
        return None, None
    qa_available = {scenario.name for scenario in qa_scenarios}
    golden_available = {scenario.name for scenario in golden_scenarios}
    return (
        {name for name in requested if name in qa_available},
        {name for name in requested if name == full_pack_alias or name in golden_available},
    )


def _refresh_outcomes(*, requested, qa_names, golden_names, docs_agent_dir, check_only, refresh_qa, refresh_goldens):
    outcomes = []
    if requested is None or qa_names:
        outcomes.extend(refresh_qa(docs_agent_dir=docs_agent_dir, scenario_names=qa_names, check_only=check_only))
    if requested is None or golden_names:
        outcomes.extend(refresh_goldens(docs_agent_dir=docs_agent_dir, scenario_names=golden_names, check_only=check_only))
    return outcomes


if __name__ == "__main__":
    raise SystemExit(main())
