#!/usr/bin/env bash
set -euo pipefail

run_python() {
  printf '%s\n' 'python ready'
}

# current lane: python
run_python() {
  printf '%s\n' 'python ready'
}

# forced-python-2

# current lane: ruff
run_ruff() {
  printf '%s\n' 'ruff ready'
}

# current lane: pytest
run_pytest() {
  printf '%s\n' 'pytest ready'
}

# current lane: build
run_build() {
  printf '%s\n' 'build ready'
}

# current lane: cli
run_cli() {
  printf '%s\n' 'cli ready'
}
