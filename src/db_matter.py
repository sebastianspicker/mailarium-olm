"""Persisted matter workspace and snapshot helpers for EmailDatabase."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from .db_matter_helpers import (
    as_dict as _as_dict,
)
from .db_matter_helpers import (
    compact as _compact,
)
from .db_matter_helpers import (
    diff_registry_sets as _diff_registry_sets,
)
from .db_matter_helpers import (
    registry_ids as _registry_ids,
)
from .db_matter_persistence import persist_snapshot as _persist_snapshot
from .db_matter_persistence import record_export as _record_export

_SNAPSHOT_REVIEW_STATES = {
    "machine_extracted",
    "human_verified",
    "disputed",
    "draft_only",
    "export_approved",
    "superseded",
}


class MatterMixin:
    """Persist shared matter entities and snapshots."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection
        _matter_write_lock: Any

        def log_custody_event(
            self,
            action: str,
            target_type: str | None = None,
            target_id: str | None = None,
            details: dict | None = None,
            content_hash: str | None = None,
            actor: str = "system",
            commit: bool = True,
        ) -> int: ...

    def persist_matter_snapshot(
        self,
        *,
        payload: dict[str, Any],
        review_mode: str,
        source_scope: str,
    ) -> dict[str, Any] | None:
        with self._matter_write_lock:
            return _persist_snapshot(self, payload=payload, review_mode=review_mode, source_scope=source_scope)

    def list_matter_snapshots(self, *, workspace_id: str) -> list[dict[str, Any]]:
        """Return persisted matter snapshots for one workspace."""
        rows = self.conn.execute(
            """SELECT snapshot_id, workspace_id, matter_id, review_mode, source_scope,
                      review_state, coverage_summary_json, created_at
               FROM matter_snapshots
               WHERE workspace_id = ?
               ORDER BY created_at DESC, rowid DESC""",
            (workspace_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["coverage_summary"] = json.loads(str(item.pop("coverage_summary_json") or "{}"))
            result.append(item)
        return result

    def latest_matter_snapshot(
        self,
        *,
        workspace_id: str,
        review_states: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return the latest persisted snapshot, optionally filtered by review state."""
        if not review_states:
            row = self.conn.execute(
                """SELECT ms.snapshot_id, ms.workspace_id, ms.matter_id, ms.review_mode, ms.source_scope,
                          ms.review_state, ms.coverage_summary_json, ms.created_at
                   FROM matters AS m
                   JOIN matter_snapshots AS ms ON ms.snapshot_id = m.latest_snapshot_id
                   WHERE m.workspace_id = ?""",
                (workspace_id,),
            ).fetchone()
            if row:
                item = dict(row)
                item["coverage_summary"] = json.loads(str(item.pop("coverage_summary_json") or "{}"))
                return item
        manageres = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        if review_states:
            normalized_states = sorted({state for state in review_states if state in _SNAPSHOT_REVIEW_STATES})
            if not normalized_states:
                return None
            manageres.append(f"review_state IN ({', '.join('?' for _ in normalized_states)})")
            params.extend(normalized_states)
        row = self.conn.execute(
            "SELECT snapshot_id, workspace_id, matter_id, review_mode, source_scope, "
            "review_state, coverage_summary_json, created_at "
            "FROM matter_snapshots "
            f"WHERE {' AND '.join(manageres)} "  # nosec
            "ORDER BY created_at DESC, rowid DESC "
            "LIMIT 1",
            params,
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["coverage_summary"] = json.loads(str(item.pop("coverage_summary_json") or "{}"))
        return item

    def get_matter_snapshot(self, *, snapshot_id: str) -> dict[str, Any] | None:
        """Return one persisted matter snapshot payload."""
        row = self.conn.execute(
            "SELECT payload_json FROM matter_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if not row:
            return None
        return json.loads(str(row["payload_json"]))

    def diff_matter_snapshots(
        self,
        *,
        older_snapshot_id: str,
        newer_snapshot_id: str,
    ) -> dict[str, Any] | None:
        """Return a compact registry diff between two persisted matter snapshots."""
        older = self.get_matter_snapshot(snapshot_id=older_snapshot_id)
        newer = self.get_matter_snapshot(snapshot_id=newer_snapshot_id)
        if older is None or newer is None:
            return None
        registry_diff = _diff_registry_sets(_registry_ids(older), _registry_ids(newer))
        return {
            "older_snapshot_id": older_snapshot_id,
            "newer_snapshot_id": newer_snapshot_id,
            "changed": bool(registry_diff.get("changed")),
            "changed_registries": list(registry_diff.get("changed_registries") or []),
            "registry_changes": _as_dict(registry_diff.get("registry_changes")),
            "coverage_transition": {
                "older": _as_dict(_as_dict(older.get("matter_coverage_ledger")).get("summary")),
                "newer": _as_dict(_as_dict(newer.get("matter_coverage_ledger")).get("summary")),
            },
        }

    def set_matter_snapshot_review_state(
        self,
        *,
        snapshot_id: str,
        review_state: str,
        reviewer: str = "human",
    ) -> dict[str, Any]:
        """Update one snapshot review state and supersede prior approved snapshots when needed."""
        normalized_state = _compact(review_state)
        if normalized_state not in _SNAPSHOT_REVIEW_STATES:
            raise ValueError(f"Unsupported snapshot review_state: {review_state}")
        row = self.conn.execute(
            """SELECT snapshot_id, workspace_id, matter_id, review_state
               FROM matter_snapshots
               WHERE snapshot_id = ?""",
            (snapshot_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown matter snapshot: {snapshot_id}")
        item = dict(row)
        workspace_id = _compact(item.get("workspace_id"))
        superseded_snapshot_ids: list[str] = []
        if normalized_state == "export_approved":
            rows = self.conn.execute(
                """SELECT snapshot_id
                   FROM matter_snapshots
                   WHERE workspace_id = ? AND snapshot_id <> ? AND review_state = 'export_approved'""",
                (workspace_id, snapshot_id),
            ).fetchall()
            superseded_snapshot_ids = [str(candidate["snapshot_id"]) for candidate in rows if str(candidate["snapshot_id"] or "")]
            if superseded_snapshot_ids:
                self.conn.executemany(
                    "UPDATE matter_snapshots SET review_state = 'superseded' WHERE snapshot_id = ?",
                    [(candidate_id,) for candidate_id in superseded_snapshot_ids],
                )
        self.conn.execute(
            "UPDATE matter_snapshots SET review_state = ? WHERE snapshot_id = ?",
            (normalized_state, snapshot_id),
        )
        self.conn.execute(
            "UPDATE matters SET latest_snapshot_id = ? WHERE workspace_id = ?",
            (snapshot_id, workspace_id),
        )
        self.conn.commit()
        self.log_custody_event(
            "matter_snapshot_review_state",
            target_type="matter_snapshot",
            target_id=snapshot_id,
            details={
                "workspace_id": workspace_id,
                "review_state": normalized_state,
                "reviewer": reviewer,
                "superseded_snapshot_ids": superseded_snapshot_ids,
            },
        )
        return {
            "snapshot_id": snapshot_id,
            "workspace_id": workspace_id,
            "matter_id": _compact(item.get("matter_id")),
            "review_state": normalized_state,
            "superseded_snapshot_ids": superseded_snapshot_ids,
        }

    def record_matter_export(
        self,
        *,
        snapshot_id: str,
        workspace_id: str,
        delivery_target: str,
        delivery_format: str,
        output_path: str,
        review_state: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._matter_write_lock:
            return _record_export(
                self,
                snapshot_id=snapshot_id,
                workspace_id=workspace_id,
                delivery_target=delivery_target,
                delivery_format=delivery_format,
                output_path=output_path,
                review_state=review_state,
                details=details,
            )
