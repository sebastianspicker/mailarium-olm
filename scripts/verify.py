#!/usr/bin/env python3
"""Run Mailarium's canonical fast, pull-request, or release verification profile."""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CONTRACT_TARGET = ROOT / "tests" / "contract"
CRITICAL_INTEGRATION_TARGETS = (
    "tests/integration/test_archive_database.py",
    "tests/integration/test_runtime_ownership.py",
    "tests/integration/test_retrieval_flow.py",
    "tests/integration/test_answer_context_flow.py",
    "tests/integration/test_mailbox_sync_flow.py",
    "tests/integration/test_adapter_wiring.py",
    "tests/integration/test_native_ingestion_flow.py",
    "tests/integration/test_archive_migrations_flow.py",
    "tests/integration/test_mailbox_projection_flow.py",
    "tests/integration/test_retrieval_channels.py",
    "tests/integration/test_web_app_flow.py",
)
CRITICAL_COVERAGE_MODULES = (
    "mailarium.runtime",
    "mailarium.mailbox.sync_service",
    "mailarium.investigation.answer_context.workflow",
    "mailarium.interfaces.mcp.tools.search",
    "mailarium.archive.database",
    "mailarium.ingestion.ingest_embed_pipeline",
    "mailarium.ingestion.mailbox_ingest",
    "mailarium.web_app",
)
OFFLINE_INGEST_ENV = {
    "RUNTIME_PROFILE": "offline-test",
    "EMBEDDING_LOAD_MODE": "local_only",
    "DISABLE_SAFETENSORS_CONVERSION": "1",
    "SPACY_AUTO_DOWNLOAD_DURING_INGEST": "0",
}


def _run(label: str, command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    """Run one named verification step from the repository root."""
    print(f"\n==> {label}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)  # nosec B603


def _run_fast() -> None:
    """Run the fast, deterministic source and contract checks."""
    _run("Lint", [sys.executable, "-m", "ruff", "check", "."])
    _run("Format check", [sys.executable, "-m", "ruff", "format", "--check", "."])
    _run("Architecture dependencies", [sys.executable, "scripts/check_architecture.py"])
    _run("Contract tests", [sys.executable, "-m", "pytest", "-q", str(CONTRACT_TARGET.relative_to(ROOT))])


def _run_complete_test_tree() -> None:
    """Run every test package so integration behavior is not inferred from contracts alone."""
    _run("Complete test suite", [sys.executable, "-m", "pytest", "-q", "tests"])


def _run_critical_integration_coverage() -> None:
    """Gate high-value composition seams with independent branch floors per module."""
    source = ",".join(CRITICAL_COVERAGE_MODULES)
    _run(
        "Critical integration coverage",
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--source={source}",
            "-m",
            "pytest",
            "-q",
            *CRITICAL_INTEGRATION_TARGETS,
        ],
    )
    _run("Critical integration coverage report", [sys.executable, "-m", "coverage", "report"])
    with tempfile.TemporaryDirectory(prefix="mailarium-critical-coverage-") as temporary:
        coverage_json = Path(temporary) / "coverage.json"
        _run(
            "Critical integration coverage JSON",
            [sys.executable, "-m", "coverage", "json", "-o", str(coverage_json)],
        )
        _run(
            "Critical per-module branch coverage",
            [sys.executable, "scripts/check_critical_coverage.py", str(coverage_json)],
        )


def _run_pull_request() -> None:
    """Run pull-request checks, including offline and security-sensitive lanes."""
    _run_fast()
    _run("Type check", [sys.executable, "-m", "mypy", "mailarium"])
    _run_complete_test_tree()
    _run_critical_integration_coverage()
    ingest_env = os.environ | OFFLINE_INGEST_ENV
    _run("Offline ingest smoke", [sys.executable, "scripts/smoke/ingest.py"], env=ingest_env)
    _run("Native SQLite storage ingest smoke", [sys.executable, "scripts/smoke/native_storage_ingest.py"])
    _run("Security scan", [sys.executable, "-m", "bandit", "-r", "mailarium", "-q", "-ll", "-ii"])
    _run("Dependency audit", [sys.executable, "scripts/release/dependency_audit.py"])
    _run("Publication privacy scan", [sys.executable, "scripts/release/privacy_scan.py", "--tracked-only", "--json"])


def _build_release_artifacts() -> None:
    """Build and inspect the release archives exported from the canonical lockfile."""
    _run("Build release artifacts", ["uv", "build", "--out-dir", str(DIST)])
    _run(
        "Export locked runtime requirements",
        [
            "uv",
            "export",
            "--locked",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--no-dev",
            "--extra",
            "nlp",
            "--extra",
            "training",
            "--extra",
            "ews-ntlm",
            "--no-hashes",
            "--output-file",
            str(DIST / "requirements.locked.txt"),
        ],
    )
    _run("Inspect release artifacts", [sys.executable, "scripts/release/check_artifacts.py", str(DIST)])


def _run_installed_wheel_smoke() -> None:
    """Install the built wheel, then verify package entry points from outside the checkout."""
    wheels = sorted(DIST.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one built wheel in {DIST}, found {len(wheels)}")

    entrypoint = Path(sys.executable).parent / "mailarium"
    with (
        tempfile.TemporaryDirectory(prefix="mailarium-wheel-smoke-") as runtime_home,
        tempfile.TemporaryDirectory(prefix="mailarium-wheel-site-") as install_root,
    ):
        install_site = Path(install_root) / "site-packages"
        _run(
            "Install built wheel",
            ["uv", "pip", "install", "--python", sys.executable, "--target", str(install_site), "--no-deps", str(wheels[0])],
        )
        existing_pythonpath = os.environ.get("PYTHONPATH", "")
        smoke_env = os.environ | {
            "MAILARIUM_RUNTIME_HOME": runtime_home,
            "MAILARIUM_INSTALLED_WHEEL_ROOT": str(install_site),
            "PYTHONPATH": os.pathsep.join(item for item in (str(install_site), existing_pythonpath) if item),
        }
        _run("Installed mailarium CLI", [str(entrypoint), "--version"], cwd=Path("/tmp"), env=smoke_env)
        _run(
            "Installed MCP entry point",
            [sys.executable, "-m", "mailarium.mcp_server", "--version"],
            cwd=Path("/tmp"),
            env=smoke_env,
        )
        _run(
            "Installed wheel and Streamlit AppTest smoke",
            [sys.executable, str(ROOT / "scripts" / "smoke" / "installed_wheel.py")],
            cwd=Path("/tmp"),
            env=smoke_env,
        )


def _run_release() -> None:
    """Run the complete release-style profile, including an installed-wheel smoke."""
    _run_pull_request()
    _run("Streamlit AppTest smoke", [sys.executable, "scripts/smoke/streamlit.py"])
    _build_release_artifacts()
    _run_installed_wheel_smoke()


def main(argv: list[str] | None = None) -> int:
    """Select and run one canonical verification profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("fast", "pr", "release"), nargs="?", default="fast")
    args = parser.parse_args(argv)

    try:
        _run("Check lockfile", ["uv", "lock", "--check"])
        if args.profile == "fast":
            _run_fast()
        elif args.profile == "pr":
            _run_pull_request()
        else:
            _run_release()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Verification profile '{args.profile}' failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nVerification profile '{args.profile}' passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
