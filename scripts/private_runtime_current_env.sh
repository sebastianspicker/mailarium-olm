#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
runtime_root="${repo_root}/private/runtime/current"
chromadb_path="${runtime_root}/chromadb"
sqlite_path="${runtime_root}/email_metadata.db"

if [[ ! -d "${chromadb_path}" ]]; then
  printf 'Missing ChromaDB path: %s\n' "${chromadb_path}" >&2
  exit 1
fi

if [[ ! -e "${sqlite_path}" ]]; then
  printf 'Missing SQLite path: %s\n' "${sqlite_path}" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  printf 'export CHROMADB_PATH=%q\n' "${chromadb_path}"
  printf 'export SQLITE_PATH=%q\n' "${sqlite_path}"
  exit 0
fi

CHROMADB_PATH="${chromadb_path}" SQLITE_PATH="${sqlite_path}" exec "$@"
