#!/usr/bin/env bash
# Resolve canonical private runtime paths and export them or run a command with them.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
runtime_root="${repo_root}/private/runtime/current"
vector_index_path="${runtime_root}/vector-index"
sqlite_path="${runtime_root}/email_metadata.db"

if [[ ! -d "${vector_index_path}" ]]; then
  printf 'Missing vector-index path: %s\n' "${vector_index_path}" >&2
  exit 1
fi

if [[ ! -e "${sqlite_path}" ]]; then
  printf 'Missing SQLite path: %s\n' "${sqlite_path}" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  printf 'export VECTOR_INDEX_PATH=%q\n' "${vector_index_path}"
  printf 'export SQLITE_PATH=%q\n' "${sqlite_path}"
  exit 0
fi

VECTOR_INDEX_PATH="${vector_index_path}" SQLITE_PATH="${sqlite_path}" exec "$@"
