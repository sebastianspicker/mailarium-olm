#!/usr/bin/env bash
# Reset private ingestion state while preserving source inputs and requiring explicit confirmation.
set -euo pipefail

usage() {
	cat <<'EOF'
Usage: bash scripts/ops/clean_ingest_reset.sh [--dry-run] [--yes] [--discard-evidence]

Reset the workspace for a fresh private ingestion run while preserving source
inputs.

Preserved by default:
  - private/files/
  - private/context.md
  - private/ingest/
  - private/README.local.md

Purged by default:
  - private/runtime/ runtime stores, lock files, ledgers, and run history
  - the metadata databases, including evidence items, the custody chain,
    mailbox (EWS) accounts, synchronized mail, sync cursors, and proposals
  - stale runtime database/vector-index leftovers under data/
  - repo-local scratch files like tmp_*.txt and .DS_Store
  - generic caches handled by scripts/ops/clean_workspace.sh

Refused (also with --dry-run):
  - while an MCP server holds mcp_server.lock
  - while a metadata database holds evidence items or mailbox state,
    unless --discard-evidence is given

Options:
  --dry-run           Print planned removals without deleting files
  --yes               Confirm destructive cleanup
  --discard-evidence  Also purge databases holding evidence, custody, and mailbox state
  -h, --help          Show this help message
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"

dry_run=0
confirmed=0
discard_evidence=0

for arg in "$@"; do
	case "$arg" in
	--dry-run)
		dry_run=1
		;;
	--yes)
		confirmed=1
		;;
	--discard-evidence)
		discard_evidence=1
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

echo "Preserving source inputs:"
echo "  - ${repo_root}/private/files"
echo "  - ${repo_root}/private/context.md"
echo "  - ${repo_root}/private/ingest"
echo "  - ${repo_root}/private/README.local.md"

declare -a purge_paths=(
	"${repo_root}/private/runtime/current"
	"${repo_root}/private/runtime/runs"
	"${repo_root}/private/runtime/ledgers"
	"${repo_root}/private/runtime/archive"
	"${repo_root}/private/runtime/vector-index"
	"${repo_root}/private/runtime/vector-index_p73"
	"${repo_root}/private/runtime/email_metadata.db"
	"${repo_root}/private/runtime/email_metadata.db-shm"
	"${repo_root}/private/runtime/email_metadata.db-wal"
	"${repo_root}/private/runtime/email_metadata_p73.db"
	"${repo_root}/private/runtime/mcp_server.lock"
	"${repo_root}/data/vector-index"
	"${repo_root}/data/email_metadata.db"
	"${repo_root}/data/email_metadata.db-shm"
	"${repo_root}/data/email_metadata.db-wal"
	"${repo_root}/data/email_index.db"
	"${repo_root}/data/email_index.db-shm"
	"${repo_root}/data/email_index.db-wal"
	"${repo_root}/data/mcp_server.lock"
)

# Refuse before deleting anything: a running server or irreplaceable evidence/mailbox state.
python3 - "$discard_evidence" "${purge_paths[@]}" <<'PY'
import fcntl
import sqlite3
import sys
from pathlib import Path

discard_evidence = sys.argv[1] == "1"
files = []
for raw in sys.argv[2:]:
    path = Path(raw)
    files.extend(sorted(path.rglob("*")) if path.is_dir() else [path])
for lock in (path for path in files if path.name == "mcp_server.lock" and path.is_file()):
    with open(lock, "rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            sys.exit(f"Refusing reset: an MCP server holds {lock}. Stop the server first.")
if discard_evidence:
    sys.exit(0)
tables = (
    "evidence_items",
    "evidence_candidates",
    "custody_chain",
    "mailbox_accounts",
    "mailbox_folders",
    "mailbox_sync_cursors",
    "mailbox_action_proposals",
    "mailbox_action_events",
    "mailbox_action_attempts",
)
for db in (path for path in files if path.suffix == ".db" and path.is_file()):
    try:
        conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            held = [table for table in tables if table in names and conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        held = [f"unreadable database ({exc})"]
    if held:
        sys.exit(
            f"Refusing reset: {db} holds {', '.join(held)} (evidence, custody, or mailbox state). "
            "Export what you need, then rerun with --discard-evidence to purge it."
        )
PY

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
	bash "${repo_root}/scripts/ops/clean_workspace.sh" --dry-run
else
	bash "${repo_root}/scripts/ops/clean_workspace.sh"
fi

ensure_dir "${repo_root}/private/runtime/current"

if [[ "$dry_run" -eq 1 ]]; then
	echo "Dry run complete. No files were deleted."
else
	echo "Clean-ingest reset complete. Source inputs preserved; runtime and generated artifacts purged."
fi
