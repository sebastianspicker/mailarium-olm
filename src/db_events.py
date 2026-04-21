"""Event record persistence mixin for EmailDatabase."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any


class EventMixin:
    """Persist and query source-aware extracted event records."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

    def upsert_event_records(
        self,
        rows: list[tuple[object, ...]],
        *,
        commit: bool = True,
    ) -> int:
        """Upsert extracted event rows using stable ``event_key`` identity."""
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO event_records(
                event_key,
                email_uid,
                event_kind,
                source_scope,
                surface_scope,
                segment_ordinal,
                char_start,
                char_end,
                trigger_text,
                event_date,
                surface_hash,
                detected_language,
                confidence,
                extractor_version,
                provenance_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(event_key) DO UPDATE SET
                email_uid=excluded.email_uid,
                event_kind=excluded.event_kind,
                source_scope=excluded.source_scope,
                surface_scope=excluded.surface_scope,
                segment_ordinal=excluded.segment_ordinal,
                char_start=excluded.char_start,
                char_end=excluded.char_end,
                trigger_text=excluded.trigger_text,
                event_date=excluded.event_date,
                surface_hash=excluded.surface_hash,
                detected_language=excluded.detected_language,
                confidence=excluded.confidence,
                extractor_version=excluded.extractor_version,
                provenance_json=excluded.provenance_json,
                updated_at=datetime('now')
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    def event_records_for_email(self, email_uid: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return extracted events for one email sorted by best locator specificity."""
        rows = self.conn.execute(
            """
            SELECT event_key, event_kind, source_scope, surface_scope, segment_ordinal,
                   char_start, char_end, trigger_text, event_date, surface_hash,
                   detected_language, confidence, extractor_version, provenance_json,
                   created_at, updated_at
            FROM event_records
            WHERE email_uid = ?
            ORDER BY COALESCE(segment_ordinal, 999999), COALESCE(char_start, 999999), event_kind
            LIMIT ?
            """,
            (email_uid, max(int(limit), 1)),
        ).fetchall()
        return [dict(row) for row in rows]

    def event_records_for_uids(self, uids: list[str], *, limit_per_uid: int = 32) -> dict[str, list[dict[str, Any]]]:
        """Return ``{uid: [event_record, ...]}`` for multiple emails."""
        if not uids:
            return {}
        result: dict[str, list[dict[str, Any]]] = {uid: [] for uid in uids if uid}
        placeholders = ",".join("?" for _ in uids)
        rows = self.conn.execute(
            "SELECT email_uid, event_key, event_kind, source_scope, surface_scope, "
            "segment_ordinal, char_start, char_end, trigger_text, event_date, "
            "surface_hash, detected_language, confidence, extractor_version, "
            "provenance_json, created_at, updated_at "
            "FROM event_records "
            f"WHERE email_uid IN ({placeholders}) "  # nosec
            "ORDER BY email_uid, COALESCE(segment_ordinal, 999999), "
            "COALESCE(char_start, 999999), event_kind",
            uids,
        ).fetchall()
        for row in rows:
            uid = str(row["email_uid"] or "")
            if not uid:
                continue
            bucket = result.setdefault(uid, [])
            if len(bucket) >= max(int(limit_per_uid), 1):
                continue
            bucket.append(dict(row))
        return result
