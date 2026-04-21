#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'EOF'
Usage: bash scripts/clean_ingest_reset.sh [--dry-run] [--yes]

Reset the workspace for a fresh private ingestion run while preserving the live
case source inputs.

Preserved by default:
  - private/files/
  - private/matter.md
  - private/ingest/my-export.olm
  - private/README.local.md
  - private/tests/materials/

Purged by default:
  - private/runtime/ runtime stores, lock files, ledgers, and run history
  - private/tests/results/
  - private/tests/exports/
  - stale runtime DB/Chroma leftovers under data/
  - repo-local scratch files like tmp_*.txt and .DS_Store
  - generic caches handled by scripts/clean_workspace.sh

Options:
  --dry-run  Print planned removals without deleting files
  --yes      Confirm destructive cleanup
  -h, --help Show this help message
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

dry_run=0
confirmed=0

for arg in "$@"; do
	case "$arg" in
	--dry-run)
		dry_run=1
		;;
	--yes)
		confirmed=1
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "Unknown argument: $arg" >&2
		usage >&2
		exit 2
		;;
	esac
done

if [[ "$dry_run" -ne 1 && "$confirmed" -ne 1 ]]; then
	echo "Refusing destructive clean-ingest reset without --yes." >&2
	echo "Run with --dry-run first or pass --yes to execute." >&2
	exit 2
fi

remove_path() {
	local path="$1"
	if [[ ! -e "$path" && ! -L "$path" ]]; then
		return
	fi
	if [[ "$dry_run" -eq 1 ]]; then
		echo "DRY-RUN remove: $path"
		return
	fi
	rm -rf -- "$path"
	echo "Removed: $path"
}

ensure_dir() {
	local path="$1"
	if [[ "$dry_run" -eq 1 ]]; then
		echo "DRY-RUN create: $path"
		return
	fi
	mkdir -p -- "$path"
	echo "Ensured: $path"
}

echo "Preserving case inputs:"
echo "  - ${repo_root}/private/files"
echo "  - ${repo_root}/private/matter.md"
echo "  - ${repo_root}/private/ingest/my-export.olm"
echo "  - ${repo_root}/private/README.local.md"
echo "  - ${repo_root}/private/tests/materials"

declare -a purge_paths=(
	"${repo_root}/private/runtime/current"
	"${repo_root}/private/runtime/runs"
	"${repo_root}/private/runtime/ledgers"
	"${repo_root}/private/runtime/archive"
	"${repo_root}/private/runtime/chromadb"
	"${repo_root}/private/runtime/chromadb_p73"
	"${repo_root}/private/runtime/email_metadata.db"
	"${repo_root}/private/runtime/email_metadata.db-shm"
	"${repo_root}/private/runtime/email_metadata.db-wal"
	"${repo_root}/private/runtime/email_metadata_p73.db"
	"${repo_root}/private/runtime/mcp_server.lock"
	"${repo_root}/private/tests/results"
	"${repo_root}/private/tests/exports"
	"${repo_root}/data/chromadb"
	"${repo_root}/data/email_metadata.db"
	"${repo_root}/data/email_metadata.db-shm"
	"${repo_root}/data/email_metadata.db-wal"
	"${repo_root}/data/email_index.db"
	"${repo_root}/data/email_index.db-shm"
	"${repo_root}/data/email_index.db-wal"
	"${repo_root}/data/mcp_server.lock"
)

for path in "${purge_paths[@]}"; do
	remove_path "$path"
done

for path in "${repo_root}"/private/runtime/runtime_inventory_*.json; do
	remove_path "$path"
done

for path in "${repo_root}"/tmp_*.txt; do
	remove_path "$path"
done

while IFS= read -r path; do
	remove_path "$path"
done < <(
	find "$repo_root" -name ".DS_Store" -not -path "*/.git/*"
)

if [[ "$dry_run" -eq 1 ]]; then
	bash "${repo_root}/scripts/clean_workspace.sh" --dry-run
else
	bash "${repo_root}/scripts/clean_workspace.sh"
fi

ensure_dir "${repo_root}/private/runtime/current"
ensure_dir "${repo_root}/private/tests/results"
ensure_dir "${repo_root}/private/tests/exports"

if [[ "$dry_run" -eq 1 ]]; then
	echo "Dry run complete. No files were deleted."
else
	echo "Clean-ingest reset complete. Case inputs preserved; runtime and generated artifacts purged."
fi
