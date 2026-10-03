"""Chain-of-custody audit trail and email provenance for the canonical archive."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress

from ..locking import ArchiveRepository, archive_repository


def compute_content_hash(content: str) -> str:
    """SHA-256 hash of a content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@archive_repository
class CustodyRepository(ArchiveRepository):
    """Chain-of-custody audit trail and email provenance."""

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """SHA-256 hash of a content string."""
        return compute_content_hash(content)

    def log_custody_event(
        self,
        action: str,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict | None = None,
        content_hash: str | None = None,
        actor: str = "system",
        commit: bool = True,
    ) -> int:
        """Record a chain-of-custody event. Returns event ID."""
        cur = self.conn.execute(
            """INSERT INTO custody_chain
               (action, actor, target_type, target_id, details, content_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                action,
                actor,
                target_type,
                target_id,
                json.dumps(details) if details else None,
                content_hash,
            ),
        )
        if commit:
            self.conn.commit()
        lastrowid = cur.lastrowid
        assert lastrowid is not None
        return int(lastrowid)

    def get_custody_chain(
        self,
        target_type: str | None = None,
        target_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve custody events with optional filters."""
        conditions: list[str] = []
        params: list = []

        if target_type:
            conditions.append("target_type = ?")
            params.append(target_type)
        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)
        if action:
            conditions.append("action = ?")
            params.append(action)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"SELECT * FROM custody_chain{where} ORDER BY timestamp DESC LIMIT ?"
        rows = self.conn.execute(
            query,
            [*params, limit],
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            if d.get("details"):
                with suppress(json.JSONDecodeError, TypeError):
                    d["details"] = json.loads(d["details"])
            result.append(d)
        return result

    def email_provenance(self, email_uid: str) -> dict:
        """Full provenance for an email: ingestion run, custody events."""
        email_row = self.conn.execute(
            "SELECT uid, message_id, sender_email, date, subject, content_sha256, ingestion_run_id FROM emails WHERE uid = ?",
            (email_uid,),
        ).fetchone()
        if not email_row:
            return {"error": f"Email not found: {email_uid}"}

        # Find the ingestion run that actually inserted this email
        run_row = None
        run_id = email_row["ingestion_run_id"]
        if run_id is not None:
            run_row = self.conn.execute(
                "SELECT * FROM ingestion_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        # Fall back to latest completed run for pre-v9 emails
        if run_row is None:
            run_row = self.conn.execute(
                "SELECT * FROM ingestion_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1"
            ).fetchone()

        custody_events = self.get_custody_chain(
            target_type="email",
            target_id=email_uid,
        )

        return {
            "email": dict(email_row),
            "ingestion_run": dict(run_row) if run_row else None,
            "custody_events": custody_events,
        }
