"""Ingestion runs, resumable checkpoints, and per-message ingest state."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import UTC, datetime

from ..locking import ArchiveRepository, archive_repository
from ..session import ArchiveSession
from .custody import CustodyRepository

logger = logging.getLogger(__name__)


def _int_value(value: object) -> int:
    """Coerce a database value to integer while preserving a caller default."""
    return int(value) if isinstance(value, int | float | str) else 0


def _ingest_state_rows(
    rows: list[dict[str, object]],
    *,
    email_first: bool,
) -> list[tuple[object, ...]]:
    """Build pending or completed ingest-ledger rows from one canonical projection."""
    projected: list[tuple[object, ...]] = []
    for row in rows:
        email_uid = str(row.get("email_uid") or "")
        if not email_uid:
            continue
        state = (
            _int_value(row.get("body_chunk_count")),
            _int_value(row.get("attachment_chunk_count")),
            _int_value(row.get("image_chunk_count")),
            _int_value(row.get("vector_chunk_count")),
            str(row.get("attachment_status") or "not_requested"),
            str(row.get("image_status") or "not_requested"),
        )
        projected.append((email_uid, *state) if email_first else (*state, email_uid))
    return projected


@archive_repository
class IngestLedgerRepository(ArchiveRepository):
    """Track ingestion runs, resumable checkpoints, and per-message vector/attachment state."""

    def __init__(self, session: ArchiveSession, *, custody: CustodyRepository) -> None:
        super().__init__(session)
        self._custody = custody

    # ------------------------------------------------------------------
    # Ingestion runs and checkpoints
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
        if run_id is None:  # pragma: no cover - INSERT always sets lastrowid
            msg = "Failed to obtain lastrowid after INSERT"
            raise RuntimeError(msg)

        self._custody.log_custody_event(
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
        self._update_terminal_ingest_checkpoint(run_id, stats, status="completed")

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
        self._custody.log_custody_event(
            "ingest_failed",
            target_type="ingestion_run",
            target_id=str(run_id),
            details={
                "error_message": error_message,
                "emails_parsed": stats.get("emails_parsed", 0),
                "emails_inserted": stats.get("emails_inserted", 0),
            },
        )
        self._update_terminal_ingest_checkpoint(run_id, stats, status="failed")

    def _update_terminal_ingest_checkpoint(self, run_id: int, stats: dict, *, status: str) -> None:
        """Mirror terminal ingestion state into its resumable checkpoint row."""
        run_row = self.conn.execute("SELECT olm_path FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is not None:
            self.update_ingest_checkpoint(
                run_id=run_id,
                olm_path=str(run_row["olm_path"] or ""),
                last_batch_ordinal=0,
                emails_parsed=int(stats.get("emails_parsed", 0) or 0),
                emails_inserted=int(stats.get("emails_inserted", 0) or 0),
                last_email_uid="",
                status=status,
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

    # ------------------------------------------------------------------
    # Per-message ingest state
    # ------------------------------------------------------------------

    def mark_ingest_batch_pending(
        self,
        rows: list[dict[str, object]],
        *,
        commit: bool = True,
    ) -> None:
        """Mark one batch as pending vector completion in the ingest ledger."""
        if not rows:
            return
        self.conn.executemany(
            """INSERT INTO email_ingest_state(
                   email_uid, body_chunk_count, attachment_chunk_count, image_chunk_count,
                   vector_chunk_count, vector_status, attachment_status, image_status,
                   last_error, updated_at
               ) VALUES(?, ?, ?, ?, ?, 'pending', ?, ?, '', datetime('now'))
               ON CONFLICT(email_uid) DO UPDATE SET
                   body_chunk_count=excluded.body_chunk_count,
                   attachment_chunk_count=excluded.attachment_chunk_count,
                   image_chunk_count=excluded.image_chunk_count,
                   vector_chunk_count=excluded.vector_chunk_count,
                   vector_status='pending',
                   attachment_status=excluded.attachment_status,
                   image_status=excluded.image_status,
                   last_error='',
                   updated_at=datetime('now')""",
            _ingest_state_rows(rows, email_first=True),
        )
        if commit:
            self.conn.commit()

    def mark_ingest_batch_completed(
        self,
        rows: list[dict[str, object]],
        *,
        commit: bool = True,
    ) -> None:
        """Mark one batch as fully persisted to the vector store."""
        if not rows:
            return
        self.conn.executemany(
            """UPDATE email_ingest_state
               SET body_chunk_count = ?,
                   attachment_chunk_count = ?,
                   image_chunk_count = ?,
                   vector_chunk_count = ?,
                   vector_status = 'completed',
                   attachment_status = ?,
                   image_status = ?,
                   last_error = '',
                   updated_at = datetime('now')
               WHERE email_uid = ?""",
            _ingest_state_rows(rows, email_first=False),
        )
        if commit:
            self.conn.commit()

    def mark_ingest_batch_failed(
        self,
        email_uids: list[str],
        *,
        error_message: str,
        commit: bool = True,
    ) -> None:
        """Persist a failed vector-write state for one batch."""
        if not email_uids:
            return
        self.conn.executemany(
            """UPDATE email_ingest_state
               SET vector_status = 'failed',
                   last_error = ?,
                   updated_at = datetime('now')
               WHERE email_uid = ?""",
            [(error_message, uid) for uid in email_uids if uid],
        )
        if commit:
            self.conn.commit()

    def degraded_attachment_ingest_uids(self) -> set[str]:
        """Return messages whose ingest ledger records degraded or unsupported attachment extraction."""
        rows = self.conn.execute(
            "SELECT email_uid FROM email_ingest_state WHERE attachment_status IN ('degraded', 'unsupported')"
        ).fetchall()
        return {str(row["email_uid"]) for row in rows if str(row["email_uid"] or "")}

    def ingest_state_chunk_counts(self, email_uid: str) -> sqlite3.Row | None:
        """Return the recorded body and image chunk counts for one message, if any."""
        return self.conn.execute(
            "SELECT body_chunk_count, image_chunk_count FROM email_ingest_state WHERE email_uid = ?",
            (email_uid,),
        ).fetchone()

    def completed_ingest_uids(
        self,
        *,
        attachment_required: bool = False,
    ) -> set[str]:
        """Return UIDs whose relational and vector ingest state is complete enough to skip."""
        manageres = ["state.vector_status = 'completed'"]
        if attachment_required:
            manageres.append("(state.attachment_status = 'completed' OR emails.has_attachments = 0)")
        rows = self.conn.execute(
            "SELECT state.email_uid "
            "FROM email_ingest_state AS state "
            "JOIN emails ON emails.uid = state.email_uid "
            f"WHERE {' AND '.join(manageres)}",  # nosec B608
        ).fetchall()
        return {str(row["email_uid"]) for row in rows if str(row["email_uid"] or "")}
