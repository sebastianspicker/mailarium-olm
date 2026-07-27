"""Default-retrieval visibility rules for synchronized mailbox sources."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

_SQL_BATCH_SIZE = 900


def has_tombstoned_mailbox_sources(conn: sqlite3.Connection | None) -> bool:
    """Return whether the canonical database currently has mailbox tombstones."""
    if conn is None or not _table_exists(conn, "email_sources"):
        return False
    row = conn.execute("SELECT 1 FROM email_sources WHERE is_tombstone=1 LIMIT 1").fetchone()
    return row is not None


def active_mailbox_uids(conn: sqlite3.Connection | None, uids: Iterable[str]) -> set[str]:
    """Return UIDs visible to default retrieval under mailbox source rules.

    Canonical rows without mailbox mappings remain visible. A row with mailbox
    mappings is hidden only when every mapping is tombstoned and none records
    that the canonical email pre-existed the mailbox integration.
    """
    requested = tuple(dict.fromkeys(str(uid) for uid in uids if str(uid)))
    if not requested or conn is None or not _table_exists(conn, "email_sources"):
        return set(requested)

    statuses = _mailbox_source_statuses(conn, requested)
    return {uid for uid in requested if uid not in statuses or statuses[uid][0] or statuses[uid][1]}


def _mailbox_source_statuses(conn: sqlite3.Connection, requested: tuple[str, ...]) -> dict[str, tuple[bool, bool]]:
    statuses: dict[str, tuple[bool, bool]] = {}
    origin_expression = "canonical_preexisting" if _column_exists(conn, "email_sources", "canonical_preexisting") else "0"
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            "SELECT canonical_email_uid,is_tombstone,"
            f"{origin_expression} AS canonical_preexisting "
            f"FROM email_sources WHERE canonical_email_uid IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        for row in rows:
            uid = str(row[0] or "")
            active, preexisting = statuses.get(uid, (False, False))
            statuses[uid] = (active or not bool(row[1]), preexisting or bool(row[2]))
    return statuses


def active_source_folders(
    conn: sqlite3.Connection | None,
    uids: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    """Return deterministic active mailbox folder memberships keyed by UID.

    This intentionally returns source folders only.  Callers that project a
    canonical ``emails.folder`` fallback retain that value separately, because
    it is valid only for unmapped or canonical-preexisting records.
    """
    requested = tuple(dict.fromkeys(str(uid) for uid in uids if str(uid)))
    if (
        not requested
        or conn is None
        or not _table_exists(conn, "email_sources")
        or not _column_exists(conn, "email_sources", "folder_id")
    ):
        return {}

    folders = _active_source_folder_sets(conn, requested)
    return {uid: tuple(sorted(values)) for uid, values in folders.items()}


def _active_source_folder_sets(conn: sqlite3.Connection, requested: tuple[str, ...]) -> dict[str, set[str]]:
    folders: dict[str, set[str]] = {}
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            "SELECT canonical_email_uid,folder_id FROM email_sources "
            "WHERE is_tombstone=0 "
            f"AND canonical_email_uid IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        for uid, folder in rows:
            normalized_uid = str(uid or "").strip()
            normalized_folder = str(folder or "").strip()
            if normalized_uid and normalized_folder:
                folders.setdefault(normalized_uid, set()).add(normalized_folder)
    return folders


def effective_source_folders(
    conn: sqlite3.Connection | None,
    canonical_folders: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    """Project active source folders plus valid canonical-folder fallbacks."""
    normalized = _normalized_canonical_folders(canonical_folders)
    if not normalized:
        return {}
    if conn is None or not _table_exists(conn, "email_sources"):
        return _canonical_folder_projection(normalized)
    return _project_effective_source_folders(conn, normalized)


def _canonical_folder_projection(
    canonical_folders: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    return {uid: (folder,) for uid, folder in canonical_folders.items() if folder}


def _project_effective_source_folders(
    conn: sqlite3.Connection,
    canonical_folders: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    projected = {uid: set(folders) for uid, folders in active_source_folders(conn, canonical_folders).items()}
    mapped, preexisting = _mapped_source_uids(conn, canonical_folders)
    _add_canonical_folder_fallbacks(projected, canonical_folders, mapped, preexisting)
    return {uid: tuple(sorted(folders)) for uid, folders in projected.items() if folders}


def _add_canonical_folder_fallbacks(
    projected: dict[str, set[str]],
    canonical_folders: Mapping[str, str],
    mapped: set[str],
    preexisting: set[str],
) -> None:
    for uid, folder in canonical_folders.items():
        if folder and (uid not in mapped or uid in preexisting):
            projected.setdefault(uid, set()).add(folder)


def _normalized_canonical_folders(canonical_folders: Mapping[str, str]) -> dict[str, str]:
    return {str(uid).strip(): str(folder or "").strip() for uid, folder in canonical_folders.items() if str(uid).strip()}


def _mapped_source_uids(
    conn: sqlite3.Connection,
    canonical_folders: Mapping[str, str],
) -> tuple[set[str], set[str]]:
    mapped: set[str] = set()
    preexisting: set[str] = set()
    origin_expression = "canonical_preexisting" if _column_exists(conn, "email_sources", "canonical_preexisting") else "0"
    requested = tuple(canonical_folders)
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            "SELECT canonical_email_uid,"
            f"{origin_expression} AS canonical_preexisting FROM email_sources "
            f"WHERE canonical_email_uid IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        for uid, canonical_preexisting in rows:
            normalized_uid = str(uid or "").strip()
            if normalized_uid:
                mapped.add(normalized_uid)
                if bool(canonical_preexisting):
                    preexisting.add(normalized_uid)
    return mapped, preexisting


def filter_active_mailbox_results[ResultT](
    results: Sequence[ResultT],
    *,
    conn: sqlite3.Connection | None,
) -> list[ResultT]:
    """Drop mailbox-only tombstones from result objects with UID metadata."""
    keyed: list[tuple[ResultT, str]] = []
    for result in results:
        metadata = getattr(result, "metadata", {})
        uid = _metadata_uid(metadata)
        keyed.append((result, uid))
    visible = active_mailbox_uids(conn, (uid for _, uid in keyed if uid))
    return [result for result, uid in keyed if not uid or uid in visible]


def _metadata_uid(metadata: Any) -> str:
    if not isinstance(metadata, Mapping):
        return ""
    return str(metadata.get("uid") or metadata.get("email_uid") or "").strip()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, name: str) -> bool:
    return any(str(row[1]) == name for row in conn.execute(f"PRAGMA table_info({table})"))  # nosec B608
