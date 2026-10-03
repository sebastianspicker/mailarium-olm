"""Clusters, topics, keywords, contacts, temporal, language, and sentiment analytics."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from ..locking import ArchiveRepository, archive_repository
from ..sql import sql_in_placeholders as _sql_in_placeholders
from .analytics_candidates import iter_analytics_candidate_batches

_LANGUAGE_GROUP_QUERIES = (
    """SELECT detected_language, COUNT(*) as cnt FROM emails
       WHERE detected_language IS NOT NULL AND detected_language != ''
       GROUP BY detected_language ORDER BY cnt DESC""",
    """SELECT detected_language_confidence AS confidence, COUNT(*) AS cnt FROM emails
       WHERE detected_language_confidence IS NOT NULL AND detected_language_confidence != ''
       GROUP BY detected_language_confidence ORDER BY cnt DESC""",
    """SELECT detected_language_reason AS reason, COUNT(*) AS cnt FROM emails
       WHERE detected_language_reason IS NOT NULL AND detected_language_reason != ''
       GROUP BY detected_language_reason ORDER BY cnt DESC""",
    """SELECT detected_language_source AS source, COUNT(*) AS cnt FROM emails
       WHERE detected_language_source IS NOT NULL AND detected_language_source != ''
       GROUP BY detected_language_source ORDER BY cnt DESC""",
)
_LANGUAGE_METADATA_QUERY = """SELECT
    SUM(CASE WHEN COALESCE(detected_language_confidence, '') != ''
        OR COALESCE(detected_language_reason, '') != ''
        OR COALESCE(detected_language_source, '') != '' THEN 1 ELSE 0 END) AS metadata_rows,
    SUM(CASE WHEN detected_language IS NOT NULL AND detected_language != ''
        AND detected_language_confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence_labeled_rows,
    SUM(CASE WHEN COALESCE(detected_language_reason, '') LIKE 'short_text_%' THEN 1 ELSE 0 END) AS short_text_rows
    FROM emails"""


@archive_repository
class AnalyticsRepository(ArchiveRepository):
    """Cluster, topic, keyword, contact, relationship, language, and sentiment analytics."""

    # ------------------------------------------------------------------
    # Cluster operations
    # ------------------------------------------------------------------

    def insert_clusters_batch(self, assignments: list[tuple[str, int, float]]) -> None:
        """Insert cluster assignments.

        Each tuple: (email_uid, cluster_id, distance_to_centroid).
        """
        self.conn.executemany(
            "INSERT OR REPLACE INTO email_clusters(email_uid, cluster_id, distance) VALUES(?, ?, ?)",
            assignments,
        )
        self.conn.commit()

    def insert_cluster_info(self, clusters: list[dict]) -> None:
        """Insert cluster metadata.

        Each dict: {cluster_id, size, representative_uid, label}.
        """
        self.conn.executemany(
            "INSERT OR REPLACE INTO cluster_info(cluster_id, size, representative_uid, label) VALUES(?, ?, ?, ?)",
            [(c["cluster_id"], c["size"], c.get("representative_uid"), c.get("label")) for c in clusters],
        )
        self.conn.commit()

    def emails_in_cluster(self, cluster_id: int, limit: int = 50) -> list[dict]:
        """Get emails in a specific cluster."""
        rows = self.conn.execute(
            """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder,
                      ec.distance
               FROM email_clusters ec
               JOIN emails e ON ec.email_uid = e.uid
               WHERE ec.cluster_id = ?
               ORDER BY ec.distance LIMIT ?""",
            (cluster_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def cluster_summary(self) -> list[dict]:
        """Get all clusters with sizes and representative info."""
        rows = self.conn.execute(
            """SELECT ci.cluster_id, ci.size, ci.representative_uid, ci.label,
                      e.subject AS representative_subject
               FROM cluster_info ci
               LEFT JOIN emails e ON ci.representative_uid = e.uid
               ORDER BY ci.size DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Keyword / Topic operations
    # ------------------------------------------------------------------

    def insert_topics(self, topics: list[dict]) -> None:
        """Insert topic definitions.

        Each dict: {id: int, label: str, top_words: list[str]}.
        """
        self.conn.executemany(
            "INSERT OR REPLACE INTO topics(id, label, top_words) VALUES(?, ?, ?)",
            [(t["id"], t["label"], json.dumps(t["top_words"])) for t in topics],
        )
        self.conn.commit()

    def insert_email_topics_batch(self, email_uid: str, topic_weights: list[tuple[int, float]]) -> None:
        """Insert topic assignments for an email."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO email_topics(email_uid, topic_id, weight) VALUES(?, ?, ?)",
            [(email_uid, topic_id, weight) for topic_id, weight in topic_weights],
        )
        self.conn.commit()

    def top_keywords(
        self,
        sender: str | None = None,
        folder: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        """Aggregate top keywords, optionally filtered by sender or folder."""
        query = """SELECT ek.keyword, ROUND(AVG(ek.score), 4) AS avg_score,
                          COUNT(DISTINCT ek.email_uid) AS email_count
                   FROM email_keywords ek"""
        conditions = []
        params: list = []

        if sender or folder:
            query += " JOIN emails e ON ek.email_uid = e.uid"
            if sender:
                conditions.append("e.sender_email = ?")
                params.append(sender)
            if folder:
                conditions.append(
                    "(EXISTS (SELECT 1 FROM email_sources active_source "
                    "WHERE active_source.canonical_email_uid=e.uid "
                    "AND active_source.is_tombstone=0 AND active_source.folder_id=?) "
                    "OR ((NOT EXISTS (SELECT 1 FROM email_sources mailbox_source "
                    "WHERE mailbox_source.canonical_email_uid=e.uid) "
                    "OR EXISTS (SELECT 1 FROM email_sources mailbox_source "
                    "WHERE mailbox_source.canonical_email_uid=e.uid "
                    "AND mailbox_source.canonical_preexisting=1)) AND e.folder=?))"
                )
                params.extend((folder, folder))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY ek.keyword ORDER BY avg_score DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def emails_by_topic(self, topic_id: int, limit: int = 30) -> list[dict]:
        """Get emails assigned to a specific topic, ranked by weight."""
        rows = self.conn.execute(
            """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder,
                      et.weight
               FROM email_topics et
               JOIN emails e ON et.email_uid = e.uid
               WHERE et.topic_id = ?
               ORDER BY et.weight DESC LIMIT ?""",
            (topic_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def topic_distribution(self) -> list[dict]:
        """Get all topics with their email counts."""
        rows = self.conn.execute(
            """SELECT t.id, t.label, t.top_words,
                      COUNT(et.email_uid) AS email_count
               FROM topics t
               LEFT JOIN email_topics et ON t.id = et.topic_id
               GROUP BY t.id
               ORDER BY email_count DESC"""
        ).fetchall()
        result = []
        for r in rows:
            try:
                words = json.loads(r["top_words"]) if r["top_words"] else []
            except json.JSONDecodeError, TypeError:
                words = []
            result.append(
                {
                    "id": r["id"],
                    "label": r["label"],
                    "top_words": words,
                    "email_count": r["email_count"],
                }
            )
        return result

    # ------------------------------------------------------------------
    # Contact / Communication queries
    # ------------------------------------------------------------------

    @staticmethod
    def _canonical_contact_identity(email_address: str) -> str:
        """Return a conservative canonical identity for contact aggregation.

        Gmail and Googlemail addresses are normalized into one identity and
        Gmail-style dots/plus-addressing are ignored so self-traffic does not
        surface as an external contact.
        """
        normalized = str(email_address or "").strip().lower()
        if "@" not in normalized:
            return normalized
        local, domain = normalized.split("@", 1)
        if domain == "googlemail.com":
            domain = "gmail.com"
        if domain == "gmail.com":
            local = local.split("+", 1)[0].replace(".", "")
        return f"{local}@{domain}"

    def top_contacts(self, email_address: str, limit: int = 20) -> list[dict]:
        """Top communication partners (bidirectional frequency)."""
        rows = self.conn.execute(
            """SELECT partner, SUM(cnt) AS total
               FROM (
                 SELECT recipient_email AS partner, email_count AS cnt
                 FROM communication_edges WHERE sender_email = ?
                 UNION ALL
                 SELECT sender_email AS partner, email_count AS cnt
                 FROM communication_edges WHERE recipient_email = ?
               )
               GROUP BY partner ORDER BY total DESC LIMIT ?""",
            (email_address, email_address, max(limit * 4, limit)),
        ).fetchall()
        focal_identity = self._canonical_contact_identity(email_address)
        totals_by_identity: dict[str, int] = defaultdict(int)
        display_by_identity: dict[str, str] = {}
        for row in rows:
            partner = str(row["partner"] or "").strip().lower()
            if not partner:
                continue
            canonical_partner = self._canonical_contact_identity(partner)
            if not canonical_partner or canonical_partner == focal_identity:
                continue
            totals_by_identity[canonical_partner] += int(row["total"] or 0)
            display_by_identity.setdefault(canonical_partner, canonical_partner)
        ranked = sorted(totals_by_identity.items(), key=lambda item: (-item[1], item[0]))
        return [{"partner": display_by_identity[identity], "total": total} for identity, total in ranked[:limit]]

    def communication_between(self, email_a: str, email_b: str) -> dict:
        """Bidirectional stats between two addresses."""
        rows = self.conn.execute(
            """SELECT sender_email, email_count, first_date, last_date
               FROM communication_edges
               WHERE (sender_email=? AND recipient_email=?)
                  OR (sender_email=? AND recipient_email=?)""",
            (email_a, email_b, email_b, email_a),
        ).fetchall()

        a_to_b_count = 0
        b_to_a_count = 0
        dates: list[str] = []
        last_dates: list[str] = []
        for r in rows:
            if r["sender_email"] == email_a:
                a_to_b_count = r["email_count"]
            else:
                b_to_a_count = r["email_count"]
            if r["first_date"]:
                dates.append(r["first_date"])
            if r["last_date"]:
                last_dates.append(r["last_date"])

        return {
            "a_to_b": a_to_b_count,
            "b_to_a": b_to_a_count,
            "total": a_to_b_count + b_to_a_count,
            "first_date": min(dates) if dates else "",
            "last_date": max(last_dates) if last_dates else "",
        }

    def all_edges(self) -> list[tuple[str, str, int]]:
        """All communication edges for graph building."""
        rows = self.conn.execute("SELECT sender_email, recipient_email, email_count FROM communication_edges").fetchall()
        return [(r["sender_email"], r["recipient_email"], r["email_count"]) for r in rows]

    # ------------------------------------------------------------------
    # Relationship queries
    # ------------------------------------------------------------------

    def shared_recipients_query(self, sender_emails: list[str], min_shared: int = 2) -> list[dict]:
        """Find recipients who received emails from multiple specified senders.

        Returns:
            List of {"recipient": str, "senders": [str], "total_emails": int}
        """
        if len(sender_emails) < 2:
            return []

        min_shared = max(min_shared, 1)

        placeholders = _sql_in_placeholders(sender_emails)
        query = (
            f"SELECT r.address AS recipient,"  # nosec B608
            f" GROUP_CONCAT(DISTINCT e.sender_email) AS senders,"  # nosec B608
            f" COUNT(*) AS total_emails"  # nosec B608
            f" FROM recipients r"  # nosec B608
            f" JOIN emails e ON r.email_uid = e.uid"  # nosec B608
            f" WHERE e.sender_email IN ({placeholders})"  # nosec B608
            f" AND r.type IN ('to', 'cc')"  # nosec B608
            f" GROUP BY r.address"  # nosec B608
            f" HAVING COUNT(DISTINCT e.sender_email) >= ?"  # nosec B608
            f" ORDER BY total_emails DESC"  # nosec B608
        )
        rows = self.conn.execute(query, [*sender_emails, min_shared]).fetchall()

        return [
            {
                "recipient": r["recipient"],
                "senders": r["senders"].split(",") if r["senders"] else [],
                "total_emails": r["total_emails"],
            }
            for r in rows
        ]

    def sender_activity_timeline(self, sender_emails: list[str]) -> list[dict]:
        """All email timestamps for specified senders, ordered by date.

        Returns:
            List of {"sender_email": str, "date": str, "uid": str, "subject": str}
        """
        if not sender_emails:
            return []

        placeholders = _sql_in_placeholders(sender_emails)
        query = (
            f"SELECT sender_email, date, uid, subject"  # nosec B608
            f" FROM emails"  # nosec B608
            f" WHERE sender_email IN ({placeholders})"  # nosec B608
            f" AND date IS NOT NULL"  # nosec B608
            f" ORDER BY date ASC"  # nosec B608
        )
        rows = self.conn.execute(query, sender_emails).fetchall()

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Temporal queries
    # ------------------------------------------------------------------

    def email_dates(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        sender: str | None = None,
    ) -> list[str]:
        """Return all email dates, optionally filtered."""
        query = "SELECT date FROM emails WHERE 1=1"
        params: list[str] = []
        if date_from:
            query += " AND SUBSTR(date, 1, 10) >= ?"
            params.append(date_from[:10])
        if date_to:
            query += " AND SUBSTR(date, 1, 10) <= ?"
            params.append(date_to[:10])
        if sender:
            query += " AND sender_email = ?"
            params.append(sender)
        rows = self.conn.execute(query, params).fetchall()
        return [r["date"] for r in rows if r["date"]]

    def response_pairs(self, sender: str | None = None, limit: int = 100) -> list[dict]:
        """Join reply→original via in_reply_to = message_id."""
        query = """
            SELECT reply.sender_email AS reply_sender,
                   reply.date AS reply_date,
                   original.sender_email AS original_sender,
                   original.date AS original_date
            FROM emails reply
            JOIN emails original ON reply.in_reply_to = original.message_id
            WHERE reply.in_reply_to != '' AND original.message_id != ''
        """
        params: list = []
        if sender:
            query += " AND reply.sender_email = ?"
            params.append(sender)
        query += " ORDER BY reply.date DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Language and sentiment distributions
    # ------------------------------------------------------------------

    def language_distribution_rows(
        self,
    ) -> tuple[
        sqlite3.Row,
        list[sqlite3.Row],
        list[sqlite3.Row],
        list[sqlite3.Row],
        list[sqlite3.Row],
        sqlite3.Row | None,
    ]:
        """Return total, label, confidence, reason, source, and metadata rows for language analytics.

        Raises ``sqlite3.OperationalError`` when the analytics columns are absent.
        """
        total = self.conn.execute("SELECT COUNT(*) AS cnt FROM emails").fetchone()
        labels, confidences, reasons, sources = (self.conn.execute(query).fetchall() for query in _LANGUAGE_GROUP_QUERIES)
        metadata = self.conn.execute(_LANGUAGE_METADATA_QUERY).fetchone()
        return total, labels, confidences, reasons, sources, metadata

    def sentiment_distribution_rows(self) -> list[sqlite3.Row]:
        """Return sentiment label counts and mean scores.

        Raises ``sqlite3.OperationalError`` when the analytics columns are absent.
        """
        return self.conn.execute(
            """
                        SELECT sentiment_label, COUNT(*) as cnt,
                               ROUND(AVG(sentiment_score), 4) as avg_score
                        FROM emails
                        WHERE sentiment_label IS NOT NULL AND sentiment_label != ''
                        GROUP BY sentiment_label
                        ORDER BY cnt DESC
                        """
        ).fetchall()

    def iter_analytics_batches(self, *, batch_size: int = 256) -> Iterator[list[dict[str, Any]]]:
        """Yield bounded pages of messages missing analytics, with their related surfaces attached."""
        yield from iter_analytics_candidate_batches(self.conn, batch_size=batch_size)

    # ------------------------------------------------------------------
    # Analytics batch update
    # ------------------------------------------------------------------

    def update_analytics_batch(
        self,
        rows: list[tuple[object, ...]],
        *,
        commit: bool = True,
    ) -> int:
        """Batch-update language and sentiment analytics by uid.

        Supported tuple shapes:
        - ``(detected_language, sentiment_label, sentiment_score, uid)``
        - ``(
              detected_language,
              detected_language_confidence,
              detected_language_reason,
              detected_language_source,
              detected_language_token_count,
              sentiment_label,
              sentiment_score,
              uid,
          )``
        Returns number of rows submitted for update.
        """
        if not rows:
            return 0
        first_row = rows[0]
        if len(first_row) == 4:
            self.conn.executemany(
                "UPDATE emails SET detected_language=?, sentiment_label=?, sentiment_score=? WHERE uid=?",
                rows,
            )
        elif len(first_row) == 8:
            self.conn.executemany(
                """
                UPDATE emails
                   SET detected_language=?,
                       detected_language_confidence=?,
                       detected_language_reason=?,
                       detected_language_source=?,
                       detected_language_token_count=?,
                       sentiment_label=?,
                       sentiment_score=?
                 WHERE uid=?
                """,
                rows,
            )
        else:
            raise ValueError(f"Unsupported analytics row shape: {len(first_row)}")
        if commit:
            self.conn.commit()
        return len(rows)

    def upsert_language_surface_analytics(
        self,
        rows: list[tuple[object, ...]],
        *,
        commit: bool = True,
    ) -> int:
        """Upsert per-surface language analytics rows for one batch."""
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO language_surface_analytics(
                email_uid,
                surface_scope,
                source_surface,
                segment_ordinal,
                text_hash,
                text_char_count,
                detected_language,
                detected_language_confidence,
                detected_language_reason,
                detected_language_token_count,
                detector_version,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stopword_v1', datetime('now'))
            ON CONFLICT(email_uid, surface_scope) DO UPDATE SET
                source_surface=excluded.source_surface,
                segment_ordinal=excluded.segment_ordinal,
                text_hash=excluded.text_hash,
                text_char_count=excluded.text_char_count,
                detected_language=excluded.detected_language,
                detected_language_confidence=excluded.detected_language_confidence,
                detected_language_reason=excluded.detected_language_reason,
                detected_language_token_count=excluded.detected_language_token_count,
                detector_version='stopword_v1',
                analyzed_at=datetime('now')
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)
