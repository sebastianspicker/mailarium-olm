"""Chain-of-custody and ingestion tracking mixin for EmailDatabase."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)


class CustodyMixin:
    """Chain-of-custody audit trail and ingestion run tracking."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

        def get_evidence(self, evidence_id: int) -> dict | None: ...  # from EvidenceMixin

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """SHA-256 hash of a content string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

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
        rows = self.conn.execute(
            f"SELECT * FROM custody_chain{where} ORDER BY timestamp DESC LIMIT ?",  # nosec
            [*params, limit],
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except (json.JSONDecodeError, TypeError):
                    pass  # keep raw details string if JSON parsing fails
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

    def evidence_provenance(self, evidence_id: int) -> dict:
        """Full provenance for evidence: item details, source email, custody history."""
        item = self.get_evidence(evidence_id)
        if not item:
            return {"error": f"Evidence not found: {evidence_id}"}

        email_prov = self.email_provenance(item["email_uid"])

        evidence_events = self.get_custody_chain(
            target_type="evidence",
            target_id=str(evidence_id),
        )

        return {
            "evidence": item,
            "source_email": email_prov,
            "custody_events": evidence_events,
        }

    # ------------------------------------------------------------------
    # Ingestion tracking
    # ------------------------------------------------------------------

    def record_ingestion_start(
        self,
        olm_path: str,
        olm_sha256: str | None = None,
        file_size_bytes: int | None = None,
        custodian: str = "system",
    ) -> int:
        """Record the start of an ingestion run. Returns run ID."""
        cur = self.conn.execute(
            """INSERT INTO ingestion_runs(olm_path, started_at, olm_sha256, file_size_bytes, custodian)
               VALUES(?, ?, ?, ?, ?)""",
            (
                olm_path,
                datetime.now(UTC).isoformat(),
                olm_sha256,
                file_size_bytes,
                custodian,
            ),
        )
        self.conn.commit()
        run_id = cur.lastrowid
        if run_id is None:  # pragma: no cover — INSERT always sets lastrowid
            msg = "Failed to obtain lastrowid after INSERT"
            raise RuntimeError(msg)

        self.log_custody_event(
            "ingest_start",
            target_type="ingestion_run",
            target_id=str(run_id),
            details={
                "olm_path": olm_path,
                "olm_sha256": olm_sha256,
                "file_size_bytes": file_size_bytes,
            },
            content_hash=olm_sha256,
            actor=custodian,
        )
        return run_id

    def record_ingestion_complete(self, run_id: int, stats: dict) -> None:
        """Record the completion of an ingestion run."""
        self.conn.execute(
            "UPDATE ingestion_runs SET completed_at=?, emails_parsed=?, emails_inserted=?, status='completed' WHERE id=?",
            (
                datetime.now(UTC).isoformat(),
                stats.get("emails_parsed", 0),
                stats.get("emails_inserted", 0),
                run_id,
            ),
        )
        self.conn.commit()
        run_row = self.conn.execute("SELECT olm_path FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is not None:
            self.update_ingest_checkpoint(
                run_id=run_id,
                olm_path=str(run_row["olm_path"] or ""),
                last_batch_ordinal=0,
                emails_parsed=int(stats.get("emails_parsed", 0) or 0),
                emails_inserted=int(stats.get("emails_inserted", 0) or 0),
                last_email_uid="",
                status="completed",
                commit=True,
            )

    def record_ingestion_failure(self, run_id: int, *, error_message: str, stats: dict | None = None) -> None:
        """Record that an ingestion run failed instead of leaving it as running."""
        stats = stats or {}
        self.conn.execute(
            "UPDATE ingestion_runs SET completed_at=?, emails_parsed=?, emails_inserted=?, status='failed' WHERE id=?",
            (
                datetime.now(UTC).isoformat(),
                stats.get("emails_parsed", 0),
                stats.get("emails_inserted", 0),
                run_id,
            ),
        )
        self.conn.commit()
        self.log_custody_event(
            "ingest_failed",
            target_type="ingestion_run",
            target_id=str(run_id),
            details={
                "error_message": error_message,
                "emails_parsed": stats.get("emails_parsed", 0),
                "emails_inserted": stats.get("emails_inserted", 0),
            },
        )
        run_row = self.conn.execute("SELECT olm_path FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is not None:
            self.update_ingest_checkpoint(
                run_id=run_id,
                olm_path=str(run_row["olm_path"] or ""),
                last_batch_ordinal=0,
                emails_parsed=int(stats.get("emails_parsed", 0) or 0),
                emails_inserted=int(stats.get("emails_inserted", 0) or 0),
                last_email_uid="",
                status="failed",
                commit=True,
            )

    def update_ingest_checkpoint(
        self,
        *,
        run_id: int,
        olm_path: str,
        last_batch_ordinal: int,
        emails_parsed: int,
        emails_inserted: int,
        last_email_uid: str,
        status: str = "running",
        commit: bool = True,
        skip_locked: bool = False,
    ) -> bool:
        """Upsert resumable ingest checkpoint state for one run."""
        started = time.monotonic()
        try:
            self.conn.execute(
                """
                INSERT INTO ingest_checkpoints(
                    run_id,
                    olm_path,
                    last_batch_ordinal,
                    emails_parsed,
                    emails_inserted,
                    last_email_uid,
                    status,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(run_id) DO UPDATE SET
                    olm_path=excluded.olm_path,
                    last_batch_ordinal=excluded.last_batch_ordinal,
                    emails_parsed=excluded.emails_parsed,
                    emails_inserted=excluded.emails_inserted,
                    last_email_uid=excluded.last_email_uid,
                    status=excluded.status,
                    updated_at=datetime('now')
                """,
                (
                    run_id,
                    olm_path,
                    int(last_batch_ordinal or 0),
                    int(emails_parsed or 0),
                    int(emails_inserted or 0),
                    str(last_email_uid or ""),
                    str(status or "running"),
                ),
            )
            if commit:
                self.conn.commit()
            return True
        except sqlite3.OperationalError as exc:
            if skip_locked and "locked" in str(exc).lower():
                logger.debug(
                    "Skipping ingest checkpoint update for run %s after %.3fs because SQLite is locked "
                    "(status=%s, batch=%s, parsed=%s, inserted=%s)",
                    run_id,
                    time.monotonic() - started,
                    status,
                    last_batch_ordinal,
                    emails_parsed,
                    emails_inserted,
                    exc_info=True,
                )
                return False
            raise

    def latest_ingest_checkpoint(self, *, olm_path: str) -> dict | None:
        """Return the most recent resumable checkpoint for one OLM path."""
        row = self.conn.execute(
            """
            SELECT *
            FROM ingest_checkpoints
            WHERE olm_path = ?
              AND status IN ('running', 'failed')
            ORDER BY updated_at DESC, run_id DESC
            LIMIT 1
            """,
            (olm_path,),
        ).fetchone()
        return dict(row) if row else None

    def clear_ingest_checkpoint(self, run_id: int, *, commit: bool = True) -> None:
        """Mark one checkpoint as completed and non-resumable."""
        self.conn.execute(
            "UPDATE ingest_checkpoints SET status='completed', updated_at=datetime('now') WHERE run_id = ?",
            (run_id,),
        )
        if commit:
            self.conn.commit()

    def last_ingestion(self, olm_path: str | None = None) -> dict | None:
        """Return the most recent completed ingestion run."""
        if olm_path:
            row = self.conn.execute(
                "SELECT * FROM ingestion_runs WHERE olm_path=? AND status='completed' ORDER BY id DESC LIMIT 1",
                (olm_path,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM ingestion_runs WHERE status='completed' ORDER BY id DESC LIMIT 1",
            ).fetchone()
        return dict(row) if row else None
