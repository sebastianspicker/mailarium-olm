#!/usr/bin/env python3
"""Run the Python dependency vulnerability audit with a bounded wall clock."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 180
IGNORED_VULNS = (
    "PYSEC-2026-597",  # nltk 3.9.4 / CVE-2026-12243: no fixed release available
)
AUDITED_EXTRAS = ("nlp", "image", "training", "ews-ntlm")


def _timeout_seconds(raw: str | None) -> int:
    """Parse a positive audit timeout, using the configured default for blank input."""
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
    """Define the dependency-audit CLI and its bounded execution timeout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=_timeout_seconds,
        default=_timeout_seconds(os.getenv("PIP_AUDIT_TIMEOUT_SECONDS")),
        help=f"Maximum runtime for pip-audit. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    return parser


def _export_locked_requirements(output_path: Path) -> bool:
    """Export the locked production environment for a deterministic audit."""
    uv = shutil.which("uv")
    if uv is None or not Path("uv.lock").is_file():
        return False
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(output_path.parent / "uv-cache")
    completed = subprocess.run(  # nosemgrep
        [
            uv,
            "export",
            "--locked",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--no-dev",
            *(option for extra in AUDITED_EXTRAS for option in ("--extra", extra)),
            "--output-file",
            str(output_path),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        env=env,
    )
    return completed.returncode == 0


def _audit_command(requirements_path: str, *, locked: bool) -> list[str]:
    """Build a pip-audit command that treats exported lock data as resolved and applies approved ignores."""
    command = [sys.executable, "-m", "pip_audit", "-r", requirements_path]
    if locked:
        command.extend(("--no-deps", "--disable-pip"))
    for vulnerability_id in IGNORED_VULNS:
        command.extend(("--ignore-vuln", vulnerability_id))
    return command


def main(argv: list[str] | None = None) -> int:
    """Export the current lock when present, run pip-audit with a timeout, and fail closed on stale lock data."""
    args = _build_parser().parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="mailarium-audit-") as tmp_dir:
        locked_path = Path(tmp_dir) / "requirements.locked.txt"
        locked = _export_locked_requirements(locked_path)
        if Path("uv.lock").is_file() and not locked:
            print(
                "Unable to export a current uv.lock; run `uv lock --check` and regenerate the lockfile before auditing.",
                file=sys.stderr,
            )
            return 2
        command = _audit_command(str(locked_path) if locked else "requirements.txt", locked=locked)
        try:
            completed = subprocess.run(  # nosemgrep
                command,
                check=False,
                timeout=args.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            print(
                f"Dependency audit timed out after {args.timeout_seconds}s: {' '.join(command)}",
                file=sys.stderr,
            )
            return 124
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
