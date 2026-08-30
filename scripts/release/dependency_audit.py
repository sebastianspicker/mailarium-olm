#!/usr/bin/env python3
"""Audit the dependency graph exported from the canonical uv lockfile."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 180
IGNORED_VULNS: tuple[str, ...] = ()
AUDITED_EXTRAS = ("nlp", "training", "ews-ntlm")
REPO_ROOT = Path(__file__).resolve().parents[2]


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
    if uv is None or not (REPO_ROOT / "uv.lock").is_file():
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
        cwd=REPO_ROOT,
    )
    return completed.returncode == 0


def _audit_command(requirements_path: str) -> list[str]:
    """Build a pip-audit command for a fully resolved lockfile export."""
    command = [sys.executable, "-m", "pip_audit", "-r", requirements_path]
    command.extend(("--no-deps", "--disable-pip"))
    for vulnerability_id in IGNORED_VULNS:
        command.extend(("--ignore-vuln", vulnerability_id))
    return command


def main(argv: list[str] | None = None) -> int:
    """Audit a temporary export from the canonical lockfile and fail closed otherwise."""
    args = _build_parser().parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="mailarium-audit-") as tmp_dir:
        locked_path = Path(tmp_dir) / "requirements.locked.txt"
        if not _export_locked_requirements(locked_path):
            print(
                "Unable to export canonical uv.lock. Install uv and run `uv lock --check` before auditing.",
                file=sys.stderr,
            )
            return 2
        command = _audit_command(str(locked_path))
        try:
            completed = subprocess.run(  # nosemgrep
                command,
                check=False,
                timeout=args.timeout_seconds,
                cwd=REPO_ROOT,
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
