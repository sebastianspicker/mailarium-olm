"""Helpers for machine-readable local investigation result state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ACTIVE_RESULTS_MANIFEST = "active_run.json"


def _iso_utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_utc_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_within_results_root(results_root: Path, path: Path | str) -> Path:
    resolved_root = results_root.resolve()
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        resolved_candidate = candidate.resolve()
    else:
        resolved_candidate = candidate.resolve()
        if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
            resolved_candidate = (resolved_root / candidate).resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"results path must stay within {resolved_root}: {path}")
    return resolved_candidate


def _relative_path(results_root: Path, path: Path | str | None) -> str | None:
    if path is None:
        return None
    resolved_root = results_root.resolve()
    resolved_candidate = _resolve_within_results_root(results_root, path)
    return str(resolved_candidate.relative_to(resolved_root))


def active_results_manifest_path(results_root: Path) -> Path:
    """Return the canonical active-results manifest path."""
    return results_root / ACTIVE_RESULTS_MANIFEST


def _ledger_reference_snapshot(
    results_root: Path,
    path: Path | str | None,
    *,
    phase_id: str,
    run_id: str,
) -> dict[str, Any]:
    relative_path = _relative_path(results_root, path)
    if relative_path is None:
        return {
            "path": None,
            "exists": False,
            "phase_reference_found": False,
            "run_reference_found": False,
            "matches_active_run": False,
            "modified_at": None,
        }

    resolved = (results_root.resolve() / relative_path).resolve()
    snapshot = {
        "path": relative_path,
        "exists": resolved.exists(),
        "phase_reference_found": False,
        "run_reference_found": False,
        "matches_active_run": False,
        "modified_at": _iso_utc_mtime(resolved) if resolved.exists() else None,
    }
    if not resolved.exists() or not resolved.is_file():
        return snapshot

    body = resolved.read_text(encoding="utf-8", errors="ignore")
    snapshot["phase_reference_found"] = phase_id in body
    snapshot["run_reference_found"] = run_id in body
    snapshot["matches_active_run"] = bool(snapshot["phase_reference_found"] and snapshot["run_reference_found"])
    return snapshot


def _curation_state(
    results_root: Path,
    *,
    phase_id: str,
    run_id: str,
    question_register_path: Path | str | None,
    open_tasks_companion_path: Path | str | None,
) -> dict[str, Any]:
    ledgers = {
        "question_register": _ledger_reference_snapshot(
            results_root,
            question_register_path,
            phase_id=phase_id,
            run_id=run_id,
        ),
        "open_tasks_companion": _ledger_reference_snapshot(
            results_root,
            open_tasks_companion_path,
            phase_id=phase_id,
            run_id=run_id,
        ),
    }
    configured = [entry for entry in ledgers.values() if entry["path"]]
    current = [entry["path"] for entry in configured if entry["matches_active_run"]]
    stale = [entry["path"] for entry in configured if entry["exists"] and not entry["matches_active_run"]]
    missing = [entry["path"] for entry in configured if not entry["exists"]]

    if not configured:
        status = "raw_results_pending_curation"
    elif missing:
        status = "partially_curated_stale"
    elif len(current) == len(configured):
        status = "curated_current"
    elif current:
        status = "partially_curated_stale"
    else:
        status = "stale_curated_ledgers"

    required_action = {
        "curated_current": "",
        "raw_results_pending_curation": "refresh_curated_ledgers_or_record_invalidation",
        "partially_curated_stale": "refresh_or_invalidate_stale_ledgers",
        "stale_curated_ledgers": "refresh_or_invalidate_stale_ledgers",
    }[status]
    return {
        "status": status,
        "phase_id": phase_id,
        "run_id": run_id,
        "current_ledgers": current,
        "stale_ledgers": stale,
        "missing_ledgers": missing,
        "required_action": required_action,
        "ledgers": ledgers,
    }


def write_active_results_manifest(
    *,
    results_root: Path,
    matter_id: str,
    run_id: str,
    phase_id: str,
    active_checkpoint: Path | str,
    active_result_paths: list[Path | str],
    question_register_path: Path | str | None = None,
    open_tasks_companion_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write the canonical active-run pointer for one local investigation workspace."""
    results_root.mkdir(parents=True, exist_ok=True)
    curation = _curation_state(
        results_root,
        phase_id=phase_id,
        run_id=run_id,
        question_register_path=question_register_path,
        open_tasks_companion_path=open_tasks_companion_path,
    )
    payload = {
        "version": 2,
        "status": "active",
        "matter_id": matter_id,
        "run_id": run_id,
        "phase_id": phase_id,
        "active_checkpoint": _relative_path(results_root, active_checkpoint),
        "active_result_paths": [path for item in active_result_paths if (path := _relative_path(results_root, item))],
        "question_register_path": _relative_path(results_root, question_register_path),
        "open_tasks_companion_path": _relative_path(results_root, open_tasks_companion_path),
        "archive_dir": "_archive",
        "curation": curation,
        "updated_at": _iso_utc_now(),
    }
    manifest_path = active_results_manifest_path(results_root)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def load_active_results_manifest(results_root: Path) -> dict[str, Any]:
    """Load the active-run pointer for one local investigation workspace."""
    return json.loads(active_results_manifest_path(results_root).read_text(encoding="utf-8"))


def archive_results_paths(
    *,
    results_root: Path,
    relative_paths: list[str],
    archive_label: str,
) -> list[str]:
    """Move superseded result files under `_archive/<archive_label>/` while preserving relative layout."""
    if not archive_label or any(token in archive_label for token in ("/", "\\", "..")):
        raise ValueError("archive_label must be a simple directory name")

    resolved_root = results_root.resolve()
    planned_moves: list[tuple[Path, Path]] = []
    normalized_relative_paths: list[str] = []
    for relative_path in relative_paths:
        normalized_relative_path = _relative_path(results_root, relative_path)
        if normalized_relative_path is None:
            raise ValueError("results path must be provided")
        source = _resolve_within_results_root(results_root, normalized_relative_path)
        if not source.exists():
            raise ValueError(f"results path does not exist: {relative_path}")
        target = _resolve_within_results_root(
            results_root,
            Path("_archive") / archive_label / normalized_relative_path,
        )
        planned_moves.append((source, target))
        normalized_relative_paths.append(normalized_relative_path)

    archived_paths: list[str] = []
    for _source, target in planned_moves:
        target.parent.mkdir(parents=True, exist_ok=True)

    for source, target in planned_moves:
        source.rename(target)
        archived_paths.append(str(target.relative_to(resolved_root)))
    return archived_paths
