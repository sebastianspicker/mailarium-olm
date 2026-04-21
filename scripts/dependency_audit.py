#!/usr/bin/env python3
"""Run the Python dependency vulnerability audit with a bounded wall clock."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

DEFAULT_TIMEOUT_SECONDS = 180
IGNORED_VULNS = ("CVE-2026-4539",)


def _timeout_seconds(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be an integer number of seconds") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=_timeout_seconds,
        default=_timeout_seconds(os.getenv("PIP_AUDIT_TIMEOUT_SECONDS")),
        help=f"Maximum runtime for pip-audit. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        "requirements.txt",
    ]
    for vulnerability_id in IGNORED_VULNS:
        command.extend(("--ignore-vuln", vulnerability_id))

    try:
        completed = subprocess.run(command, check=False, timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            f"Dependency audit timed out after {args.timeout_seconds}s: {' '.join(command)}",
            file=sys.stderr,
        )
        return 124
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
