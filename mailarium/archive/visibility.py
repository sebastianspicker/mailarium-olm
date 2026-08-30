"""Default-retrieval visibility rules for synchronized mailbox sources.

This policy belongs to the canonical archive because retrieval consumes it
without depending on a live mailbox adapter.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

_SQL_BATCH_SIZE = 900


def has_tombstoned_mailbox_sources(conn: sqlite3.Connection | None) -> bool:
    """Return whether the canonical database currently has mailbox tombstones."""
    if conn is None or not _table_exists(conn, "email_sources"):
        return False
    return conn.execute("SELECT 1 FROM email_sources WHERE is_tombstone=1 LIMIT 1").fetchone() is not None


def active_mailbox_uids(conn: sqlite3.Connection | None, uids: Iterable[str]) -> set[str]:
    """Return UIDs visible to default retrieval under mailbox source rules."""
    requested = tuple(dict.fromkeys(str(uid) for uid in uids if str(uid)))
    if not requested or conn is None or not _table_exists(conn, "email_sources"):
        return set(requested)
    statuses = _mailbox_source_statuses(conn, requested)
    return {uid for uid in requested if uid not in statuses or statuses[uid][0] or statuses[uid][1]}


def _mailbox_source_statuses(conn: sqlite3.Connection, requested: tuple[str, ...]) -> dict[str, tuple[bool, bool]]:
    statuses: dict[str, tuple[bool, bool]] = {}
    origin = "canonical_preexisting" if _column_exists(conn, "email_sources", "canonical_preexisting") else "0"
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        rows = conn.execute(
            "SELECT canonical_email_uid,is_tombstone,"
            f"{origin} AS canonical_preexisting FROM email_sources WHERE canonical_email_uid IN ({','.join('?' for _ in batch)})",  # nosec B608
            batch,
        ).fetchall()
        for uid, tombstone, preexisting in rows:
            key = str(uid or "")
            active, existed = statuses.get(key, (False, False))
            statuses[key] = (active or not bool(tombstone), existed or bool(preexisting))
    return statuses


def active_source_folders(conn: sqlite3.Connection | None, uids: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Return deterministic active mailbox folder memberships keyed by UID."""
    requested = tuple(dict.fromkeys(str(uid) for uid in uids if str(uid)))
    if (
        not requested
        or conn is None
        or not _table_exists(conn, "email_sources")
        or not _column_exists(conn, "email_sources", "folder_id")
    ):
        return {}
    folders: dict[str, set[str]] = {}
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        rows = conn.execute(
            "SELECT canonical_email_uid,folder_id FROM email_sources WHERE is_tombstone=0 "
            f"AND canonical_email_uid IN ({','.join('?' for _ in batch)})",  # nosec B608
            batch,
        ).fetchall()
        for uid, folder in rows:
            key, name = str(uid or "").strip(), str(folder or "").strip()
            if key and name:
                folders.setdefault(key, set()).add(name)
    return {uid: tuple(sorted(values)) for uid, values in folders.items()}


def effective_source_folders(conn: sqlite3.Connection | None, canonical_folders: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    """Project active source folders plus valid canonical-folder fallbacks."""
    canonical = {str(uid).strip(): str(folder or "").strip() for uid, folder in canonical_folders.items() if str(uid).strip()}
    if not canonical:
        return {}
    if conn is None or not _table_exists(conn, "email_sources"):
        return {uid: (folder,) for uid, folder in canonical.items() if folder}
    projected = {uid: set(folders) for uid, folders in active_source_folders(conn, canonical).items()}
    mapped, preexisting = _mapped_source_uids(conn, canonical)
    for uid, folder in canonical.items():
        if folder and (uid not in mapped or uid in preexisting):
            projected.setdefault(uid, set()).add(folder)
    return {uid: tuple(sorted(folders)) for uid, folders in projected.items() if folders}


def _mapped_source_uids(conn: sqlite3.Connection, canonical_folders: Mapping[str, str]) -> tuple[set[str], set[str]]:
    mapped: set[str] = set()
    preexisting: set[str] = set()
    origin = "canonical_preexisting" if _column_exists(conn, "email_sources", "canonical_preexisting") else "0"
    requested = tuple(canonical_folders)
    for start in range(0, len(requested), _SQL_BATCH_SIZE):
        batch = requested[start : start + _SQL_BATCH_SIZE]
        rows = conn.execute(
            "SELECT canonical_email_uid,"
            f"{origin} AS canonical_preexisting FROM email_sources WHERE canonical_email_uid IN ({','.join('?' for _ in batch)})",  # nosec B608
            batch,
        ).fetchall()
        for uid, existed in rows:
            key = str(uid or "").strip()
            if key:
                mapped.add(key)
                if bool(existed):
                    preexisting.add(key)
    return mapped, preexisting


def filter_active_mailbox_results[ResultT](results: Sequence[ResultT], *, conn: sqlite3.Connection | None) -> list[ResultT]:
    """Drop mailbox-only tombstones from result objects with UID metadata."""
    keyed = [(result, _metadata_uid(getattr(result, "metadata", {}))) for result in results]
    visible = active_mailbox_uids(conn, (uid for _, uid in keyed if uid))
    return [result for result, uid in keyed if not uid or uid in visible]


def _metadata_uid(metadata: Any) -> str:
    return str(metadata.get("uid") or metadata.get("email_uid") or "").strip() if isinstance(metadata, Mapping) else ""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, name: str) -> bool:
    return any(str(row[1]) == name for row in conn.execute(f"PRAGMA table_info({table})"))  # nosec B608
