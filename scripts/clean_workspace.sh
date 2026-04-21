#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/clean_workspace.sh [--dry-run] [--include-venv]

Options:
  --dry-run       Print planned removals without deleting files
  --include-venv  Also remove .venv/ from the workspace
  -h, --help      Show this help message
EOF
}

dry_run=0
include_venv=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      dry_run=1
      ;;
    --include-venv)
      include_venv=1
      ;;
    -h|--help)
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

remove_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    return
  fi
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN remove: $path"
    return
  fi
  rm -rf -- "$path"
  echo "Removed: $path"
}

remove_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    return
  fi
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN remove: $path"
    return
  fi
  rm -f -- "$path"
  echo "Removed: $path"
}

declare -a fixed_paths=(
  ".mypy_cache"
  ".pytest_cache"
  ".ruff_cache"
  "src/__pycache__"
  "tests/__pycache__"
  ".tmp"
  "tmp"
)

if [[ "$include_venv" -eq 1 ]]; then
  fixed_paths+=(".venv")
fi

for path in "${fixed_paths[@]}"; do
  remove_path "$path"
done

while IFS= read -r path; do
  remove_path "$path"
done < <(
  find . -type d -name "__pycache__" \
    -not -path "./.git/*" \
    -not -path "./.venv/*" \
    -not -path "./.venv"
)

while IFS= read -r path; do
  remove_file "$path"
done < <(
  find . -type f \
    \( -name "*.log" -o -name "*.tmp" -o -name "*.bak" -o -name "*.orig" -o -name "*.sqlite3" -o -name "*.db" \) \
    -not -path "./.git/*" \
    -not -path "./data/*"
)

if [[ "$dry_run" -eq 1 ]]; then
  echo "Dry run complete."
else
  echo "Workspace cleanup complete."
fi
