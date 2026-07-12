"""Entity management mixin for EmailDatabase."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .db_schema import _escape_like, _sql_in_placeholders


def _safe_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _EntityOccurrence:
    text: str
    entity_type: str
    normalized_form: str
    source_scope: str
    surface_scope: str
    segment_ordinal: int | None
    char_start: int | None
    char_end: int | None
    occurrence_text: str


def _entity_occurrence(row: tuple[object, ...]) -> _EntityOccurrence:
    if len(row) != 9:
        raise ValueError(f"Unsupported occurrence row shape: {len(row)}")
    entity_text, entity_type, normalized_form, source_scope, surface_scope, ordinal, start, end, occurrence_text = row
    return _EntityOccurrence(
        text=str(entity_text or ""),
        entity_type=str(entity_type or ""),
        normalized_form=str(normalized_form or ""),
        source_scope=str(source_scope or "email_text"),
        surface_scope=str(surface_scope or ""),
        segment_ordinal=_safe_optional_int(ordinal),
        char_start=_safe_optional_int(start),
        char_end=_safe_optional_int(end),
        occurrence_text=str(occurrence_text or ""),
    )


def _upsert_occurrence_entity(cur: sqlite3.Cursor, occurrence: _EntityOccurrence) -> int | None:
    row = cur.execute(
        """INSERT INTO entities(entity_text, entity_type, normalized_form)
           VALUES(?, ?, ?)
           ON CONFLICT(normalized_form, entity_type) DO UPDATE SET
             entity_text = excluded.entity_text
           RETURNING id""",
        (occurrence.text, occurrence.entity_type, occurrence.normalized_form),
    ).fetchone()
    return int(row[0]) if row is not None else None


def _occurrence_hash(entity_id: int, email_uid: str, occurrence: _EntityOccurrence) -> str:
    values = (
        entity_id,
        email_uid,
        occurrence.source_scope,
        occurrence.surface_scope,
        occurrence.segment_ordinal,
        occurrence.char_start,
        occurrence.char_end,
        occurrence.occurrence_text.casefold(),
    )
    return hashlib.sha256(
        "|".join("" if value is None else str(value) for value in values).encode("utf-8", errors="ignore")
    ).hexdigest()


def _persist_entity_occurrence(
    cur: sqlite3.Cursor,
    email_uid: str,
    entity_id: int,
    occurrence: _EntityOccurrence,
    extractor_key: str,
    extraction_version: str,
) -> None:
    cur.execute(
        """
        INSERT INTO entity_occurrences(
            entity_id, email_uid, source_scope, surface_scope, segment_ordinal,
            char_start, char_end, occurrence_text, occurrence_hash,
            extractor_key, extraction_version, extracted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(entity_id, email_uid, occurrence_hash) DO UPDATE SET
            source_scope=excluded.source_scope,
            surface_scope=excluded.surface_scope,
            segment_ordinal=excluded.segment_ordinal,
            char_start=excluded.char_start,
            char_end=excluded.char_end,
            occurrence_text=excluded.occurrence_text,
            extractor_key=excluded.extractor_key,
            extraction_version=excluded.extraction_version,
            extracted_at=datetime('now')
        """,
        (
            entity_id,
            email_uid,
            occurrence.source_scope,
            occurrence.surface_scope,
            occurrence.segment_ordinal,
            occurrence.char_start,
            occurrence.char_end,
            occurrence.occurrence_text,
            _occurrence_hash(entity_id, email_uid, occurrence),
            str(extractor_key or ""),
            str(extraction_version or ""),
        ),
    )


class EntityMixin:
    """NLP entity insert, search, timeline, and co-occurrence queries."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

    @staticmethod
    def _coerce_entity_row(entity: tuple[str, str, str] | Any) -> tuple[str, str, str]:
        """Accept tuple-based or object-based extracted entities."""
        if isinstance(entity, tuple) and len(entity) == 3:
            text, entity_type, normalized_form = entity
            return str(text), str(entity_type), str(normalized_form)
        text = getattr(entity, "text", None)
        entity_type = getattr(entity, "entity_type", None)
        normalized_form = getattr(entity, "normalized_form", None)
        if text is None or entity_type is None or normalized_form is None:
            raise TypeError(f"Unsupported entity row: {entity!r}")
        return str(text), str(entity_type), str(normalized_form)

    def insert_entities_batch(
        self,
        email_uid: str,
        entities: list[tuple[str, str, str]],
        *,
        extractor_key: str = "",
        extraction_version: str = "",
        commit: bool = True,
    ) -> None:
        """Insert extracted entities for an email.

        Each entity is (entity_text, entity_type, normalized_form).

        Args:
            commit: If False, skip the final commit (caller is responsible).
        """
        cur = self.conn.cursor()
        for entity in entities:
            text, etype, norm = self._coerce_entity_row(entity)
            row = cur.execute(
                """INSERT INTO entities(entity_text, entity_type, normalized_form)
                   VALUES(?, ?, ?)
                   ON CONFLICT(normalized_form, entity_type) DO UPDATE SET
                     entity_text = excluded.entity_text
                   RETURNING id""",
                (text, etype, norm),
            ).fetchone()
            entity_id = row[0]
            cur.execute(
                """INSERT INTO entity_mentions(
                       entity_id, email_uid, mention_count, extractor_key, extraction_version, extracted_at
                   )
                   VALUES(?, ?, 1, ?, ?, datetime('now'))
                   ON CONFLICT(entity_id, email_uid) DO UPDATE SET
                     mention_count = entity_mentions.mention_count + 1,
                     extractor_key = excluded.extractor_key,
                     extraction_version = excluded.extraction_version,
                     extracted_at = datetime('now')""",
                (entity_id, email_uid, str(extractor_key or ""), str(extraction_version or "")),
            )
        if commit:
            self.conn.commit()

    def insert_entities_batch_idempotent(
        self,
        email_uid: str,
        entities: list[tuple[str, str, str]],
        *,
        extractor_key: str = "",
        extraction_version: str = "",
        commit: bool = True,
    ) -> None:
        """Insert extracted entities for maintenance paths without count inflation on rerun."""
        cur = self.conn.cursor()
        for entity in entities:
            text, etype, norm = self._coerce_entity_row(entity)
            row = cur.execute(
                """INSERT INTO entities(entity_text, entity_type, normalized_form)
                   VALUES(?, ?, ?)
                   ON CONFLICT(normalized_form, entity_type) DO UPDATE SET
                     entity_text = excluded.entity_text
                   RETURNING id""",
                (text, etype, norm),
            ).fetchone()
            entity_id = row[0]
            cur.execute(
                """INSERT INTO entity_mentions(
                       entity_id, email_uid, mention_count, extractor_key, extraction_version, extracted_at
                   )
                   VALUES(?, ?, 1, ?, ?, datetime('now'))
                   ON CONFLICT(entity_id, email_uid) DO UPDATE SET
                     mention_count = MAX(entity_mentions.mention_count, excluded.mention_count),
                     extractor_key = excluded.extractor_key,
                     extraction_version = excluded.extraction_version,
                     extracted_at = datetime('now')""",
                (entity_id, email_uid, str(extractor_key or ""), str(extraction_version or "")),
            )
        if commit:
            self.conn.commit()

    def insert_entity_occurrences(
        self,
        email_uid: str,
        occurrences: list[tuple[object, ...]],
        *,
        extractor_key: str = "",
        extraction_version: str = "",
        commit: bool = True,
    ) -> int:
        """Insert occurrence-level entity provenance rows without count inflation."""
        if not occurrences:
            return 0
        inserted = 0
        cur = self.conn.cursor()
        for raw_occurrence in occurrences:
            occurrence = _entity_occurrence(raw_occurrence)
            if not occurrence.normalized_form or not occurrence.entity_type:
                continue
            entity_id = _upsert_occurrence_entity(cur, occurrence)
            if entity_id is None:
                continue
            _persist_entity_occurrence(cur, email_uid, entity_id, occurrence, extractor_key, extraction_version)
            inserted += 1
        if commit:
            self.conn.commit()
        return inserted

    def entity_occurrences_for_email(self, email_uid: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return occurrence-level entity rows for one email."""
        rows = self.conn.execute(
            """
            SELECT eo.id, eo.email_uid, eo.source_scope, eo.surface_scope,
                   eo.segment_ordinal, eo.char_start, eo.char_end,
                   eo.occurrence_text, eo.occurrence_hash,
                   eo.extractor_key, eo.extraction_version, eo.extracted_at,
                   ent.entity_text, ent.entity_type, ent.normalized_form
            FROM entity_occurrences eo
            JOIN entities ent ON ent.id = eo.entity_id
            WHERE eo.email_uid = ?
            ORDER BY COALESCE(eo.segment_ordinal, 999999), COALESCE(eo.char_start, 999999), eo.id
            LIMIT ?
            """,
            (email_uid, max(int(limit), 1)),
        ).fetchall()
        return [dict(row) for row in rows]

    def entity_occurrences_for_uids(
        self,
        uids: list[str],
        *,
        limit_per_uid: int = 64,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return occurrence-level entity rows grouped by email UID."""
        normalized_uids = [str(uid or "") for uid in uids if str(uid or "")]
        if not normalized_uids:
            return {}
        result: dict[str, list[dict[str, Any]]] = {uid: [] for uid in normalized_uids}
        placeholders = _sql_in_placeholders(normalized_uids)
        rows = self.conn.execute(
            "SELECT eo.id, eo.email_uid, eo.source_scope, eo.surface_scope, "
            "eo.segment_ordinal, eo.char_start, eo.char_end, "
            "eo.occurrence_text, eo.occurrence_hash, "
            "eo.extractor_key, eo.extraction_version, eo.extracted_at, "
            "ent.entity_text, ent.entity_type, ent.normalized_form "
            "FROM entity_occurrences eo "
            "JOIN entities ent ON ent.id = eo.entity_id "
            f"WHERE eo.email_uid IN ({placeholders}) "  # nosec B608
            "ORDER BY eo.email_uid, COALESCE(eo.segment_ordinal, 999999), "
            "COALESCE(eo.char_start, 999999), eo.id",
            normalized_uids,
        ).fetchall()
        limit_value = max(int(limit_per_uid), 1)
        for row in rows:
            uid = str(row["email_uid"] or "")
            if not uid:
                continue
            bucket = result.setdefault(uid, [])
            if len(bucket) >= limit_value:
                continue
            bucket.append(dict(row))
        return result

    def delete_entity_mentions_for_email(self, email_uid: str, *, commit: bool = True) -> int:
        """Delete entity mentions for one email and prune now-orphaned entities."""
        cur = self.conn.cursor()
        deleted = cur.execute("DELETE FROM entity_mentions WHERE email_uid = ?", (email_uid,)).rowcount
        cur.execute(
            """DELETE FROM entities
               WHERE id NOT IN (SELECT DISTINCT entity_id FROM entity_mentions)"""
        )
        if commit:
            self.conn.commit()
        return deleted

    def entity_provenance_summary(self) -> dict[str, Any]:
        """Return counts grouped by persisted entity extractor provenance."""
        rows = self.conn.execute(
            """SELECT COALESCE(NULLIF(extractor_key, ''), 'unknown') AS extractor_key,
                      COALESCE(NULLIF(extraction_version, ''), 'unknown') AS extraction_version,
                      COUNT(*) AS mention_rows,
                      COUNT(DISTINCT email_uid) AS email_count
               FROM entity_mentions
               GROUP BY extractor_key, extraction_version
               ORDER BY mention_rows DESC, extractor_key ASC"""
        ).fetchall()
        return {"rows": [dict(row) for row in rows]}

    def search_by_entity(self, entity_text: str, entity_type: str | None = None, limit: int = 20) -> list[dict]:
        """Find emails mentioning an entity (LIKE match)."""
        escaped = f"%{_escape_like(entity_text.lower())}%"
        if entity_type:
            rows = self.conn.execute(
                """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder,
                          ent.entity_text, ent.entity_type
                   FROM entity_mentions em
                   JOIN entities ent ON em.entity_id = ent.id
                   JOIN emails e ON em.email_uid = e.uid
                   WHERE ent.normalized_form LIKE ? ESCAPE '\\' AND ent.entity_type = ?
                   ORDER BY e.date DESC LIMIT ?""",
                (escaped, entity_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder,
                          ent.entity_text, ent.entity_type
                   FROM entity_mentions em
                   JOIN entities ent ON em.entity_id = ent.id
                   JOIN emails e ON em.email_uid = e.uid
                   WHERE ent.normalized_form LIKE ? ESCAPE '\\'
                   ORDER BY e.date DESC LIMIT ?""",
                (escaped, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def top_entities(self, entity_type: str | None = None, limit: int = 20) -> list[dict]:
        """Most frequently mentioned entities."""
        if entity_type:
            rows = self.conn.execute(
                """SELECT ent.entity_text, ent.entity_type, ent.normalized_form,
                          SUM(em.mention_count) AS total_mentions,
                          COUNT(DISTINCT em.email_uid) AS email_count
                   FROM entities ent
                   JOIN entity_mentions em ON ent.id = em.entity_id
                   WHERE ent.entity_type = ?
                   GROUP BY ent.id
                   ORDER BY total_mentions DESC LIMIT ?""",
                (entity_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT ent.entity_text, ent.entity_type, ent.normalized_form,
                          SUM(em.mention_count) AS total_mentions,
                          COUNT(DISTINCT em.email_uid) AS email_count
                   FROM entities ent
                   JOIN entity_mentions em ON ent.id = em.entity_id
                   GROUP BY ent.id
                   ORDER BY total_mentions DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def people_in_emails(self, name_query: str, limit: int = 20) -> list[dict]:
        """Find emails mentioning a person by name (LIKE match on person entities)."""
        rows = self.conn.execute(
            """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder,
                      ent.entity_text AS person_name
               FROM entity_mentions em
               JOIN entities ent ON em.entity_id = ent.id
               JOIN emails e ON em.email_uid = e.uid
               WHERE ent.entity_type = 'person'
                 AND ent.normalized_form LIKE ? ESCAPE '\\'
               ORDER BY e.date DESC LIMIT ?""",
            (f"%{_escape_like(name_query.lower())}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def entity_timeline(self, entity_text: str, period: str = "month") -> list[dict]:
        """Show how often an entity appears over time.

        Args:
            entity_text: Entity text to search for (partial match).
            period: 'day', 'week', or 'month'.

        Returns:
            List of {period, count} dicts.
        """
        if period == "day":
            date_expr = "substr(e.date, 1, 10)"
        elif period == "week":
            # Use date only (day granularity) and compute ISO week in Python
            # because SQLite's %W uses Sunday-based weeks, not ISO 8601.
            date_expr = "substr(e.date, 1, 10)"
        else:
            date_expr = "substr(e.date, 1, 7)"

        _date_expr_allowlist = {"substr(e.date, 1, 10)", "substr(e.date, 1, 7)"}
        if date_expr not in _date_expr_allowlist:
            date_expr = "substr(e.date, 1, 7)"

        query = (
            f"SELECT {date_expr} AS period, COUNT(*) AS count"  # nosec B608
            f" FROM entity_mentions em"  # nosec B608
            f" JOIN entities ent ON em.entity_id = ent.id"  # nosec B608
            f" JOIN emails e ON em.email_uid = e.uid"  # nosec B608
            r" WHERE ent.normalized_form LIKE ? ESCAPE '\'"  # nosec B608
            f" GROUP BY period"  # nosec B608
            f" ORDER BY period"  # nosec B608
        )
        rows = self.conn.execute(
            query,
            (f"%{_escape_like(entity_text.lower())}%",),
        ).fetchall()

        if period == "week":
            # Aggregate day-level rows into ISO 8601 weeks (Monday-based)
            from datetime import datetime as _dt

            week_counts: dict[str, int] = {}
            for r in rows:
                try:
                    d = _dt.strptime(r["period"], "%Y-%m-%d")
                    iso_year, iso_week, _ = d.isocalendar()
                    week_key = f"{iso_year}-W{iso_week:02d}"
                except (ValueError, TypeError):
                    week_key = r["period"]
                week_counts[week_key] = week_counts.get(week_key, 0) + r["count"]
            return [{"period": k, "count": v} for k, v in sorted(week_counts.items())]

        return [dict(r) for r in rows]

    def entity_co_occurrences(self, entity_text: str, limit: int = 20) -> list[dict]:
        """Entities that co-occur with the given entity in the same emails."""
        rows = self.conn.execute(
            """SELECT ent2.entity_text, ent2.entity_type, ent2.normalized_form,
                      COUNT(DISTINCT em1.email_uid) AS co_occurrence_count
               FROM entity_mentions em1
               JOIN entities ent1 ON em1.entity_id = ent1.id
               JOIN entity_mentions em2 ON em1.email_uid = em2.email_uid
               JOIN entities ent2 ON em2.entity_id = ent2.id
               WHERE ent1.normalized_form LIKE ? ESCAPE '\\' AND ent2.id != ent1.id
               GROUP BY ent2.id
               ORDER BY co_occurrence_count DESC LIMIT ?""",
            (f"%{_escape_like(entity_text.lower())}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]
