#!/usr/bin/env bash
set -euo pipefail

profile="${1:-local}"
python_bin="python"

if [[ "$profile" != "local" && "$profile" != "ci" ]]; then
  echo "Usage: bash scripts/run_acceptance_matrix.sh [local|ci]" >&2
  exit 2
fi

run_step() {
  local label="$1"
  shift
  echo
  echo "==> ${label}"
  "$@"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_command ruff
require_command python

if [[ "$profile" == "ci" ]]; then
  echo "Running CI profile. Ensure dependencies are installed: pip install -r requirements-dev.txt"
fi

run_step "Lint (python -m ruff check .)" "$python_bin" -m ruff check .
run_step "Format check (python -m ruff format --check .)" "$python_bin" -m ruff format --check .
run_step "Type check (python -m mypy src)" "$python_bin" -m mypy src
run_step \
  "Test suite (python -m pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80; local thread caps enabled)" \
  env \
  OMP_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 \
  "$python_bin" -m pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80
run_step "Streamlit smoke (python scripts/streamlit_smoke.py)" "$python_bin" scripts/streamlit_smoke.py
run_step "Security scan (python -m bandit -r src -q -ll -ii)" "$python_bin" -m bandit -r src -q -ll -ii

audit_cache_dir="$(mktemp -d)"
trap 'rm -rf "$audit_cache_dir"' EXIT

if [[ "$profile" == "local" ]] && ! "$python_bin" -c 'import socket; socket.getaddrinfo("pypi.org", 443)' >/dev/null 2>&1; then
  echo
  echo "==> Dependency audit (python -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539)"
  echo "Skipping in local profile because pypi.org is unreachable from this environment."
else
  run_step \
    "Dependency audit (python -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539)" \
    env PIP_CACHE_DIR="$audit_cache_dir" \
    "$python_bin" -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539
fi

echo
echo "Acceptance matrix profile '${profile}' passed."
