#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/topology_inventory.sh [REPO_ROOT]

Print a lightweight mixed-stack inventory to help fill docs/agent/Topology.md.

The script is intentionally read-only and heuristic. It does not modify files.
EOF
}

if (($# > 1)); then
  usage >&2
  exit 1
fi

repo_root="${1:-.}"
repo_root="$(cd -- "$repo_root" && pwd)"

if ! command -v rg >/dev/null 2>&1; then
  printf 'rg is required for topology_inventory.sh\n' >&2
  exit 1
fi

printf '# Topology inventory for %s\n\n' "$repo_root"

printf '## Workspace signals\n\n'
rg --files "$repo_root" \
  -g 'pnpm-workspace.yaml' \
  -g 'turbo.json' \
  -g 'nx.json' \
  -g 'Package.swift' \
  -g 'pyproject.toml' \
  -g 'docker-compose.yml' \
  -g 'compose.yaml' \
  -g 'package.json' \
  -g 'next.config.*' \
  -g 'vite.config.*' \
  | sed "s#^$repo_root/#- #"

printf '\n## Suggested units\n\n'
printf '| Unit | Type | Path | Stack |\n'
printf '| --- | --- | --- | --- |\n'

while IFS= read -r path; do
  rel="${path#"$repo_root"/}"
  dir="$(dirname -- "$rel")"
  base="$(basename -- "$rel")"
  stack="unknown"
  type="unit"

  case "$base" in
    next.config.*)
      stack="Next.js"
      type="app"
      ;;
    vite.config.*)
      stack="Vite"
      type="app"
      ;;
    pyproject.toml)
      stack="Python"
      type="service"
      ;;
    Package.swift)
      stack="Swift"
      type="package"
      ;;
    docker-compose.yml|compose.yaml)
      stack="Docker Compose"
      type="infra"
      ;;
    package.json)
      stack="Node.js"
      type="package"
      ;;
  esac

  printf "| \`%s\` | %s | \`%s\` | %s |\n" "$(basename -- "$dir")" "$type" "$dir" "$stack"
done < <(
  rg --files "$repo_root" \
    -g 'package.json' \
    -g 'next.config.*' \
    -g 'vite.config.*' \
    -g 'pyproject.toml' \
    -g 'Package.swift' \
    -g 'docker-compose.yml' \
    -g 'compose.yaml' \
    | sort -u
)

printf '\n## Next step\n\n'
printf '%s\n' '- Copy the relevant lines into docs/agent/Topology.md and add real ownership, dependencies, and verification commands.'
