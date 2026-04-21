"""Analytics mixin for EmailDatabase: clusters, topics, keywords, contacts, relationships."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # conn declared below for mypy


class AnalyticsMixin:
    """Cluster, topic, keyword, contact, and relationship query methods."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

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

    def insert_keywords_batch(self, email_uid: str, keywords: list[tuple[str, float]]) -> None:
        """Insert keyword/score pairs for an email."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO email_keywords(email_uid, keyword, score) VALUES(?, ?, ?)",
            [(email_uid, keyword, score) for keyword, score in keywords],
        )
        self.conn.commit()

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
                conditions.append("e.folder = ?")
                params.append(folder)

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
            except (json.JSONDecodeError, TypeError):
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

        if min_shared < 1:
            min_shared = 1

        placeholders = ",".join("?" for _ in sender_emails)
        rows = self.conn.execute(
            f"SELECT r.address AS recipient,"  # nosec
            f" GROUP_CONCAT(DISTINCT e.sender_email) AS senders,"
            f" COUNT(*) AS total_emails"
            f" FROM recipients r"
            f" JOIN emails e ON r.email_uid = e.uid"
            f" WHERE e.sender_email IN ({placeholders})"
            f" AND r.type IN ('to', 'cc')"
            f" GROUP BY r.address"
            f" HAVING COUNT(DISTINCT e.sender_email) >= ?"
            f" ORDER BY total_emails DESC",
            [*sender_emails, min_shared],
        ).fetchall()

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

        placeholders = ",".join("?" for _ in sender_emails)
        rows = self.conn.execute(
            f"SELECT sender_email, date, uid, subject"  # nosec
            f" FROM emails"
            f" WHERE sender_email IN ({placeholders})"
            f" AND date IS NOT NULL"
            f" ORDER BY date ASC",
            sender_emails,
        ).fetchall()

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
