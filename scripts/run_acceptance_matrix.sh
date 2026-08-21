#!/usr/bin/env bash
# Run progressively broader local, CI, or release verification gates.
set -euo pipefail

profile="${1:-local}"
python_bin="${PYTHON_BIN:-}"

if [[ -z "$python_bin" ]]; then
	if [[ -x ".venv/bin/python" ]]; then
		python_bin=".venv/bin/python"
	else
		python_bin="python"
	fi
fi

if [[ "$profile" != "local" && "$profile" != "ci" && "$profile" != "release" ]]; then
	echo "Usage: bash scripts/run_acceptance_matrix.sh [local|ci|release]" >&2
	exit 2
fi

run_step() {
	local label="$1"
	shift
	echo
	echo "==> ${label}"
	"$@"
}

run_dependency_audit() {
	local label="Dependency audit (python scripts/dependency_audit.py)"
	local -a audit_cmd=("$python_bin" scripts/dependency_audit.py)

	echo
	echo "==> ${label}"
	if env PIP_CACHE_DIR="$audit_cache_dir" "${audit_cmd[@]}"; then
		return 0
	fi

	echo "Initial dependency audit failed; retrying once with a fresh PyPI request path." >&2
	"${audit_cmd[@]}"
}

require_command() {
	if ! command -v "$1" >/dev/null 2>&1; then
		echo "Missing required command: $1" >&2
		exit 127
	fi
}

require_python() {
	if [[ "$python_bin" == */* ]]; then
		if [[ ! -x "$python_bin" ]]; then
			echo "Missing required Python interpreter: $python_bin" >&2
			exit 127
		fi
		return
	fi
	require_command "$python_bin"
}

require_python

if [[ "$profile" == "ci" ]]; then
	echo "Running CI profile. Ensure the lock is current and all declared extras are installed with uv sync --locked."
elif [[ "$profile" == "release" ]]; then
	echo "Running release profile. Dependency audit is required and may not be skipped."
else
	echo "Running local profile with interpreter: ${python_bin}"
fi

run_step "Lint (python -m ruff check .)" "$python_bin" -m ruff check .
run_step "Format check (python -m ruff format --check .)" "$python_bin" -m ruff format --check .
run_step "Type check (python -m mypy mailarium)" "$python_bin" -m mypy mailarium
run_step "Direct contracts (python -m pytest -q tests/test_contracts.py)" "$python_bin" -m pytest -q tests/test_contracts.py
run_step \
	"Ingest smoke (reports native vs fallback runtime)" \
	env \
	RUNTIME_PROFILE=offline-test \
	EMBEDDING_LOAD_MODE=local_only \
	DISABLE_SAFETENSORS_CONVERSION=1 \
	SPACY_AUTO_DOWNLOAD_DURING_INGEST=0 \
	"$python_bin" scripts/ingest_smoke.py
run_step "Security scan (python -m bandit -r mailarium -q -ll -ii)" "$python_bin" -m bandit -r mailarium -q -ll -ii

audit_cache_dir="$(mktemp -d)"
trap 'rm -rf "$audit_cache_dir"' EXIT

if [[ "$profile" == "local" ]] && ! "$python_bin" -c 'import socket; socket.getaddrinfo("pypi.org", 443)' >/dev/null 2>&1; then
	echo
	echo "==> Dependency audit (python scripts/dependency_audit.py)"
	echo "Skipping in local profile because pypi.org is unreachable from this environment."
elif [[ "$profile" == "release" ]] && ! "$python_bin" -c 'import socket; socket.getaddrinfo("pypi.org", 443)' >/dev/null 2>&1; then
	echo
	echo "==> Dependency audit (python scripts/dependency_audit.py)"
	echo "Release profile requires a real dependency-audit result, but pypi.org is unreachable from this environment." >&2
	exit 1
else
	run_dependency_audit
fi

echo
echo "Acceptance matrix profile '${profile}' passed."
