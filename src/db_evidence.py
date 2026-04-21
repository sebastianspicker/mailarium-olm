"""Evidence management mixin for EmailDatabase."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Any, ClassVar

from .db_evidence_queries import (
    evidence_candidate_stats_impl,
    evidence_categories_impl,
    evidence_stats_impl,
    evidence_timeline_impl,
    get_evidence_impl,
    list_evidence_impl,
    quote_verification_state_for_evidence,
    search_evidence_impl,
    verify_evidence_quotes_impl,
)

logger = logging.getLogger(__name__)
_REVIEW_STATES = {
    "machine_extracted",
    "human_verified",
    "disputed",
    "draft_only",
    "export_approved",
}


def _clean_identity_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _coerce_non_negative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _decode_locator_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    raw = _clean_identity_text(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalized_artifact_locator(locator: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "evidence_handle": _clean_identity_text(locator.get("evidence_handle")),
        "chunk_id": _clean_identity_text(locator.get("chunk_id")),
        "segment_type": _clean_identity_text(locator.get("segment_type")).casefold(),
        "segment_ordinal": _coerce_non_negative_int(locator.get("segment_ordinal")),
        "snippet_start": _coerce_non_negative_int(locator.get("snippet_start")),
        "snippet_end": _coerce_non_negative_int(locator.get("snippet_end")),
        "source_scope": _clean_identity_text(locator.get("source_scope")).casefold(),
        "char_start": _coerce_non_negative_int(locator.get("char_start")),
        "char_end": _coerce_non_negative_int(locator.get("char_end")),
        "surface_hash": _clean_identity_text(locator.get("surface_hash")).casefold(),
        "attachment_id": _clean_identity_text(locator.get("attachment_id")).casefold(),
        "content_sha256": _clean_identity_text(locator.get("content_sha256")).casefold(),
        "attachment_filename": _clean_identity_text(locator.get("attachment_filename")).casefold(),
    }
    return {key: value for key, value in normalized.items() if value not in (None, "")}


def _artifact_identity_matches(
    *,
    candidate_kind: str,
    candidate_locator: dict[str, Any],
    existing_kind: str,
    existing_locator: dict[str, Any],
) -> bool:
    normalized_candidate_kind = _clean_identity_text(candidate_kind).casefold()
    normalized_existing_kind = _clean_identity_text(existing_kind).casefold()

    if normalized_candidate_kind:
        if normalized_existing_kind and normalized_existing_kind != normalized_candidate_kind:
            return False
        if normalized_candidate_kind != "attachment" and normalized_existing_kind == "attachment":
            return False
    if normalized_candidate_kind == "attachment":
        candidate_attachment_id = _clean_identity_text(candidate_locator.get("attachment_id")).casefold()
        existing_attachment_id = _clean_identity_text(existing_locator.get("attachment_id")).casefold()
        if candidate_attachment_id and existing_attachment_id and candidate_attachment_id == existing_attachment_id:
            return True
        candidate_content_sha = _clean_identity_text(candidate_locator.get("content_sha256")).casefold()
        existing_content_sha = _clean_identity_text(existing_locator.get("content_sha256")).casefold()
        if candidate_content_sha and existing_content_sha and candidate_content_sha == existing_content_sha:
            return True
        candidate_filename = _clean_identity_text(candidate_locator.get("attachment_filename")).casefold()
        existing_filename = _clean_identity_text(existing_locator.get("attachment_filename")).casefold()
        if not candidate_filename or not existing_filename or candidate_filename != existing_filename:
            return False

    for key in (
        "evidence_handle",
        "chunk_id",
        "segment_type",
        "segment_ordinal",
        "snippet_start",
        "snippet_end",
        "source_scope",
        "char_start",
        "char_end",
        "surface_hash",
        "attachment_id",
        "content_sha256",
    ):
        candidate_value = candidate_locator.get(key)
        existing_value = existing_locator.get(key)
        if candidate_value not in (None, "") and existing_value not in (None, "") and candidate_value != existing_value:
            return False

    if normalized_candidate_kind == "attachment":
        return True
    if (
        candidate_locator.get("evidence_handle")
        and existing_locator.get("evidence_handle")
        and candidate_locator.get("evidence_handle") == existing_locator.get("evidence_handle")
    ):
        return True
    if (
        candidate_locator.get("chunk_id")
        and existing_locator.get("chunk_id")
        and candidate_locator.get("chunk_id") == existing_locator.get("chunk_id")
    ):
        return True
    candidate_segment = (candidate_locator.get("segment_type"), candidate_locator.get("segment_ordinal"))
    existing_segment = (existing_locator.get("segment_type"), existing_locator.get("segment_ordinal"))
    if all(candidate_segment) and all(existing_segment) and candidate_segment == existing_segment:
        return True
    if (
        candidate_locator.get("snippet_start") is not None
        and candidate_locator.get("snippet_end") is not None
        and existing_locator.get("snippet_start") is not None
        and existing_locator.get("snippet_end") is not None
        and candidate_locator.get("snippet_start") == existing_locator.get("snippet_start")
        and candidate_locator.get("snippet_end") == existing_locator.get("snippet_end")
    ):
        return True

    has_candidate_artifact_identity = any(
        candidate_locator.get(key) not in (None, "")
        for key in (
            "evidence_handle",
            "chunk_id",
            "segment_type",
            "segment_ordinal",
            "snippet_start",
            "snippet_end",
            "source_scope",
            "char_start",
            "char_end",
            "surface_hash",
            "attachment_id",
            "content_sha256",
        )
    )
    if not has_candidate_artifact_identity and normalized_candidate_kind in {"", "body"}:
        return normalized_existing_kind in {"", "body"}
    return False


class EvidenceMixin:
    """Evidence item CRUD, verification, search, and statistics."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

        @staticmethod
        def compute_content_hash(content: str) -> str: ...  # from CustodyMixin

        def log_custody_event(
            self,
            action: str,
            target_type: str | None = ...,
            target_id: str | None = ...,
            details: dict | None = ...,
            content_hash: str | None = ...,
            actor: str = ...,
            commit: bool = ...,
        ) -> int: ...  # from CustodyMixin

    EVIDENCE_CATEGORIES: ClassVar[list[str]] = [
        "bossing",
        "harassment",
        "discrimination",
        "retaliation",
        "hostile_environment",
        "micromanagement",
        "exclusion",
        "gaslighting",
        "workload",
        "contradiction",
        "chronology",
        "provenance",
        "quote_repair",
        "omission",
        "promise",
        "general",
    ]

    def add_evidence(
        self,
        email_uid: str,
        category: str,
        key_quote: str,
        summary: str,
        relevance: int,
        notes: str = "",
        *,
        candidate_kind: str = "",
        provenance: dict | None = None,
        document_locator: dict | None = None,
        context: dict | None = None,
    ) -> dict:
        """Add an evidence item linked to an email.

        Auto-populates sender/date/recipients/subject from the email record.
        Runs quote verification immediately against the best available stored body text.

        Args:
            email_uid: UID of the source email (must exist).
            category: Evidence category (e.g. discrimination, contradiction, harassment).
            key_quote: Exact quote from the email body.
            summary: Brief description of why this is evidence.
            relevance: 1-5 rating (1=tangential, 5=critical).
            notes: Optional notes for the lawyer.

        Returns:
            Dict with the created evidence item including id and verified status.

        Raises:
            ValueError: If email_uid does not exist in the database.
        """
        relevance = max(1, min(5, int(relevance)))

        if category not in self.EVIDENCE_CATEGORIES:
            logger.warning(
                "Non-standard evidence category: %s (expected one of %s)",
                category,
                self.EVIDENCE_CATEGORIES,
            )

        # Validate email exists and fetch metadata
        email_row = self.conn.execute(
            """SELECT sender_name, sender_email, date, subject,
                      forensic_body_text, body_text, raw_body_text,
                      (SELECT GROUP_CONCAT(COALESCE(a.extracted_text, a.text_preview, ''), '\n')
                         FROM attachments a
                        WHERE a.email_uid = emails.uid) AS attachment_text,
                      (SELECT GROUP_CONCAT(ms.text, '\n')
                         FROM message_segments ms
                        WHERE ms.email_uid = emails.uid) AS segment_text
               FROM emails WHERE uid = ?""",
            (email_uid,),
        ).fetchone()
        if not email_row:
            raise ValueError(f"Email not found: {email_uid}")

        # Build recipients string from recipients table
        recip_rows = self.conn.execute(
            "SELECT address, display_name FROM recipients WHERE email_uid = ? AND type = 'to'",
            (email_uid,),
        ).fetchall()
        recipients = ", ".join(f"{r['display_name']} <{r['address']}>" if r["display_name"] else r["address"] for r in recip_rows)

        # Verify quote against the richest stored body sources for the email.
        verification = quote_verification_state_for_evidence(
            self,
            email_uid=email_uid,
            quote=key_quote,
            candidate_kind=candidate_kind,
            document_locator=document_locator or {},
        )
        verified = 1 if verification.get("state") == "exact_verified" else 0

        content_hash = self.compute_content_hash(f"{email_uid}|{category}|{key_quote}")

        try:
            cur = self.conn.execute(
                """INSERT INTO evidence_items
                   (email_uid, category, key_quote, summary, relevance,
                    sender_name, sender_email, date, recipients, subject, notes, verified,
                    content_hash, candidate_kind, provenance_json, document_locator_json, context_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    email_uid,
                    category,
                    key_quote,
                    summary,
                    relevance,
                    email_row["sender_name"],
                    email_row["sender_email"],
                    email_row["date"],
                    recipients,
                    email_row["subject"],
                    notes,
                    verified,
                    content_hash,
                    candidate_kind,
                    json.dumps(provenance or {}, ensure_ascii=False),
                    json.dumps(document_locator or {}, ensure_ascii=False),
                    json.dumps(context or {}, ensure_ascii=False),
                ),
            )
            new_id = cur.lastrowid

            self.log_custody_event(
                "evidence_add",
                target_type="evidence",
                target_id=str(new_id),
                details={
                    "email_uid": email_uid,
                    "category": category,
                    "relevance": relevance,
                    "summary": summary[:200],
                },
                content_hash=content_hash,
                commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        return {
            "id": new_id,
            "email_uid": email_uid,
            "category": category,
            "key_quote": key_quote,
            "summary": summary,
            "relevance": relevance,
            "sender_name": email_row["sender_name"],
            "sender_email": email_row["sender_email"],
            "date": email_row["date"],
            "recipients": recipients,
            "subject": email_row["subject"],
            "notes": notes,
            "verified": verified,
            "content_hash": content_hash,
            "candidate_kind": candidate_kind,
            "provenance": provenance or {},
            "document_locator": document_locator or {},
            "context": context or {},
        }

    def list_evidence(
        self,
        category: str | None = None,
        min_relevance: int | None = None,
        email_uid: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """List evidence items with optional filters.

        Returns:
            {"items": [...], "total": int}
        """
        return list_evidence_impl(
            self,
            category=category,
            min_relevance=min_relevance,
            email_uid=email_uid,
            limit=limit,
            offset=offset,
        )

    def get_evidence(self, evidence_id: int) -> dict | None:
        """Get a single evidence item by ID."""
        return get_evidence_impl(self, evidence_id)

    def update_evidence(self, evidence_id: int, **fields) -> bool:
        """Update fields on an evidence item.

        Allowed fields: category, key_quote, summary, relevance, notes.
        Sets updated_at automatically. Re-verifies if key_quote changes.
        Logs a custody event with a snapshot of old values.

        Returns:
            True if the item was updated, False if not found.
        """
        allowed = {"category", "key_quote", "summary", "relevance", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        if "relevance" in updates and updates["relevance"] is not None:
            updates["relevance"] = max(1, min(5, int(updates["relevance"])))

        # Check item exists and snapshot old values
        existing = self.conn.execute(
            "SELECT * FROM evidence_items WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        if not existing:
            return False
        old_values = {k: existing[k] for k in updates}

        # Re-verify if key_quote changed
        if "key_quote" in updates:
            new_quote = updates["key_quote"].strip()
            verification = quote_verification_state_for_evidence(
                self,
                email_uid=str(existing["email_uid"] or ""),
                quote=new_quote,
                candidate_kind=str(existing["candidate_kind"] or ""),
                document_locator=_decode_locator_json(existing["document_locator_json"]),
            )
            updates["verified"] = 1 if verification.get("state") == "exact_verified" else 0

        # Recompute content hash
        category = updates.get("category", existing["category"])
        key_quote = updates.get("key_quote", existing["key_quote"])
        new_hash = self.compute_content_hash(f"{existing['email_uid']}|{category}|{key_quote}")
        updates["content_hash"] = new_hash

        set_managere = ", ".join(f"{k} = ?" for k in updates)
        set_managere += ", updated_at = datetime('now')"
        params = [*updates.values(), evidence_id]

        try:
            cur = self.conn.execute(
                f"UPDATE evidence_items SET {set_managere} WHERE id = ?",  # nosec
                params,
            )

            if cur.rowcount > 0:
                self.log_custody_event(
                    "evidence_update",
                    target_type="evidence",
                    target_id=str(evidence_id),
                    details={"old_values": old_values, "new_values": {k: v for k, v in updates.items() if k != "content_hash"}},
                    content_hash=new_hash,
                    commit=False,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return cur.rowcount > 0

    def remove_evidence(self, evidence_id: int) -> bool:
        """Delete an evidence item by ID. Logs custody event with snapshot. Returns True if deleted."""
        # Snapshot before deletion
        existing = self.conn.execute(
            "SELECT * FROM evidence_items WHERE id = ?",
            (evidence_id,),
        ).fetchone()

        try:
            cur = self.conn.execute(
                "DELETE FROM evidence_items WHERE id = ?",
                (evidence_id,),
            )

            if cur.rowcount > 0 and existing:
                snapshot = dict(existing)
                self.log_custody_event(
                    "evidence_remove",
                    target_type="evidence",
                    target_id=str(evidence_id),
                    details={
                        "email_uid": snapshot.get("email_uid"),
                        "category": snapshot.get("category"),
                        "key_quote": snapshot.get("key_quote", "")[:200],
                        "relevance": snapshot.get("relevance"),
                        "summary": snapshot.get("summary", "")[:200],
                    },
                    content_hash=snapshot.get("content_hash"),
                    commit=False,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return cur.rowcount > 0

    def verify_evidence_quotes(self) -> dict:
        """Verify all evidence quotes against actual email body text.

        For each evidence item, checks if key_quote appears (case-insensitive)
        in the linked email's richest stored body sources. Updates the verified column.

        Returns:
            {"verified": int, "failed": int, "failures": [{"evidence_id": ..., "key_quote_preview": ..., "email_uid": ...}, ...]}
        """
        return verify_evidence_quotes_impl(self)

    def evidence_stats(
        self,
        category: str | None = None,
        min_relevance: int | None = None,
    ) -> dict:
        """Return evidence collection statistics, optionally filtered.

        Args:
            category: Only count items in this category.
            min_relevance: Only count items with relevance >= this value.

        Returns:
            {"total": int, "verified": int, "unverified": int,
             "by_category": [{"category": str, "count": int}, ...],
             "by_relevance": [{"relevance": int, "count": int}, ...]}
        """
        return evidence_stats_impl(self, category=category, min_relevance=min_relevance)

    def add_evidence_candidate(
        self,
        *,
        run_id: str,
        phase_id: str,
        wave_id: str,
        wave_label: str,
        question_ids: list[str],
        email_uid: str | None,
        candidate_kind: str,
        quote_candidate: str,
        summary: str,
        category_hint: str,
        rank: int,
        score: float,
        verification_status: str,
        verified_exact: bool,
        subject: str,
        sender_name: str,
        sender_email: str,
        date: str,
        conversation_id: str,
        matched_query_lanes: list[str],
        matched_query_queries: list[str],
        provenance: dict | None = None,
        context: dict | None = None,
    ) -> dict:
        """Persist one harvested evidence candidate for a wave run.

        Returns the stored row plus an ``inserted`` flag. Duplicate candidates for the
        same ``run_id`` and ``wave_id`` are ignored and returned as existing rows.
        """
        content_hash = self.compute_content_hash(
            json.dumps(
                {
                    "phase_id": phase_id,
                    "email_uid": email_uid or "",
                    "candidate_kind": candidate_kind,
                    "quote_candidate": quote_candidate,
                    "provenance": provenance or {},
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        existing = self.conn.execute(
            """SELECT *
               FROM evidence_candidates
               WHERE run_id = ? AND wave_id = ? AND content_hash = ?""",
            (run_id, wave_id, content_hash),
        ).fetchone()
        if existing:
            payload = dict(existing)
            payload["inserted"] = False
            return payload

        values = (
            run_id,
            phase_id,
            wave_id,
            wave_label,
            json.dumps(question_ids, ensure_ascii=False),
            email_uid,
            candidate_kind,
            quote_candidate,
            summary,
            category_hint,
            rank,
            score,
            verification_status,
            1 if verified_exact else 0,
            subject,
            sender_name,
            sender_email,
            date,
            conversation_id,
            json.dumps(matched_query_lanes, ensure_ascii=False),
            json.dumps(matched_query_queries, ensure_ascii=False),
            json.dumps(provenance or {}, ensure_ascii=False),
            json.dumps(context or {}, ensure_ascii=False),
            "harvested",
            None,
            content_hash,
        )
        try:
            cur = self.conn.execute(
                """INSERT INTO evidence_candidates(
                       run_id, phase_id, wave_id, wave_label, question_ids_json, email_uid,
                       candidate_kind, quote_candidate, summary, category_hint, rank, score,
                       verification_status, verified_exact, subject, sender_name, sender_email,
                       date, conversation_id, matched_query_lanes_json, matched_query_queries_json,
                       provenance_json, context_json, status, promoted_evidence_id, content_hash
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            candidate_id = cur.lastrowid
            self.log_custody_event(
                "evidence_candidate_add",
                target_type="evidence_candidate",
                target_id=str(candidate_id),
                details={
                    "run_id": run_id,
                    "phase_id": phase_id,
                    "wave_id": wave_id,
                    "candidate_kind": candidate_kind,
                    "email_uid": email_uid or "",
                    "verified_exact": bool(verified_exact),
                },
                content_hash=content_hash,
                commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        created = self.conn.execute("SELECT * FROM evidence_candidates WHERE id = ?", (candidate_id,)).fetchone()
        payload = dict(created) if created else {"id": candidate_id, "content_hash": content_hash}
        payload["inserted"] = True
        return payload

    def mark_evidence_candidate_promoted(self, candidate_id: int, *, evidence_id: int) -> bool:
        """Mark a harvested candidate as promoted into the durable evidence corpus."""
        try:
            cur = self.conn.execute(
                """UPDATE evidence_candidates
                   SET status = 'promoted', promoted_evidence_id = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (evidence_id, candidate_id),
            )
            if cur.rowcount > 0:
                self.log_custody_event(
                    "evidence_candidate_promote",
                    target_type="evidence_candidate",
                    target_id=str(candidate_id),
                    details={"evidence_id": evidence_id},
                    commit=False,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return cur.rowcount > 0

    def find_evidence_by_email_quote(self, *, email_uid: str, key_quote: str) -> dict | None:
        """Return an existing evidence item matching one email UID and exact quote."""
        row = self.conn.execute(
            """SELECT *
               FROM evidence_items
               WHERE email_uid = ? AND lower(key_quote) = lower(?)""",
            (email_uid, key_quote),
        ).fetchone()
        return dict(row) if row else None

    def find_evidence_by_email_artifact_quote(
        self,
        *,
        email_uid: str,
        key_quote: str,
        candidate_kind: str,
        document_locator: dict[str, Any] | None = None,
    ) -> dict | None:
        """Return an existing evidence item matching one email UID, quote, and artifact identity."""
        normalized_email_uid = _clean_identity_text(email_uid)
        normalized_key_quote = _clean_identity_text(key_quote)
        if not normalized_email_uid or not normalized_key_quote:
            return None
        candidate_locator = _normalized_artifact_locator(document_locator or {})
        rows = self.conn.execute(
            """SELECT id, email_uid, key_quote, candidate_kind, document_locator_json
               FROM evidence_items
               WHERE email_uid = ? AND lower(key_quote) = lower(?)
               ORDER BY id ASC""",
            (normalized_email_uid, normalized_key_quote),
        ).fetchall()
        for row in rows:
            payload = dict(row)
            existing_locator = _normalized_artifact_locator(_decode_locator_json(payload.get("document_locator_json")))
            if _artifact_identity_matches(
                candidate_kind=candidate_kind,
                candidate_locator=candidate_locator,
                existing_kind=_clean_identity_text(payload.get("candidate_kind")),
                existing_locator=existing_locator,
            ):
                return payload
        return None

    def evidence_candidate_stats(
        self,
        *,
        run_id: str | None = None,
        phase_id: str | None = None,
    ) -> dict:
        """Return harvested evidence-candidate statistics."""
        return evidence_candidate_stats_impl(self, run_id=run_id, phase_id=phase_id)

    def upsert_matter_review_override(
        self,
        *,
        workspace_id: str,
        target_type: str,
        target_id: str,
        review_state: str,
        override_payload: dict | None = None,
        machine_payload: dict | None = None,
        source_evidence: list[dict] | None = None,
        reviewer: str = "human",
        review_notes: str = "",
        apply_on_refresh: bool = True,
    ) -> dict:
        """Persist or replace one human review override for a matter product item."""
        workspace_id = str(workspace_id or "").strip()
        target_type = str(target_type or "").strip()
        target_id = str(target_id or "").strip()
        review_state = str(review_state or "").strip()
        if not workspace_id or not target_type or not target_id:
            raise ValueError("workspace_id, target_type, and target_id are required for review overrides.")
        if review_state not in _REVIEW_STATES:
            raise ValueError(f"Unsupported review_state: {review_state}")

        override_payload = override_payload if isinstance(override_payload, dict) else {}
        machine_payload = machine_payload if isinstance(machine_payload, dict) else {}
        source_evidence = [item for item in (source_evidence or []) if isinstance(item, dict)]
        content_hash = self.compute_content_hash(
            json.dumps(
                {
                    "workspace_id": workspace_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "review_state": review_state,
                    "override_payload": override_payload,
                },
                sort_keys=True,
            )
        )

        try:
            self.conn.execute(
                """INSERT INTO matter_review_overrides(
                       workspace_id, target_type, target_id, review_state,
                       override_payload_json, machine_payload_json, source_evidence_json,
                       reviewer, review_notes, apply_on_refresh, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(workspace_id, target_type, target_id) DO UPDATE SET
                       review_state=excluded.review_state,
                       override_payload_json=excluded.override_payload_json,
                       machine_payload_json=excluded.machine_payload_json,
                       source_evidence_json=excluded.source_evidence_json,
                       reviewer=excluded.reviewer,
                       review_notes=excluded.review_notes,
                       apply_on_refresh=excluded.apply_on_refresh,
                       updated_at=datetime('now')""",
                (
                    workspace_id,
                    target_type,
                    target_id,
                    review_state,
                    json.dumps(override_payload, sort_keys=True),
                    json.dumps(machine_payload, sort_keys=True),
                    json.dumps(source_evidence, sort_keys=True),
                    reviewer,
                    review_notes,
                    int(bool(apply_on_refresh)),
                ),
            )
            row = self.conn.execute(
                """SELECT * FROM matter_review_overrides
                   WHERE workspace_id=? AND target_type=? AND target_id=?""",
                (workspace_id, target_type, target_id),
            ).fetchone()
            self.log_custody_event(
                "review_override_upsert",
                target_type="matter_review_override",
                target_id=f"{workspace_id}:{target_type}:{target_id}",
                details={
                    "workspace_id": workspace_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "review_state": review_state,
                    "apply_on_refresh": bool(apply_on_refresh),
                },
                content_hash=content_hash,
                commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        return dict(row) if row else {}

    def list_matter_review_overrides(
        self,
        *,
        workspace_id: str,
        target_type: str | None = None,
        apply_on_refresh_only: bool = False,
    ) -> list[dict]:
        """Return persisted review overrides for one matter workspace."""
        manageres = ["workspace_id = ?"]
        params: list[object] = [workspace_id]
        if target_type:
            manageres.append("target_type = ?")
            params.append(target_type)
        if apply_on_refresh_only:
            manageres.append("apply_on_refresh = 1")
        rows = self.conn.execute(
            "SELECT * FROM matter_review_overrides "
            f"WHERE {' AND '.join(manageres)} "  # nosec
            "ORDER BY target_type, target_id",
            params,
        ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["override_payload"] = json.loads(str(item.pop("override_payload_json") or "{}"))
            item["machine_payload"] = json.loads(str(item.pop("machine_payload_json") or "{}"))
            item["source_evidence"] = json.loads(str(item.pop("source_evidence_json") or "[]"))
            item["apply_on_refresh"] = bool(item.get("apply_on_refresh"))
            result.append(item)
        return result

    def matter_review_status_summary(self, *, workspace_id: str) -> dict:
        """Return review-state counts for one matter workspace."""
        overrides = self.list_matter_review_overrides(workspace_id=workspace_id)
        counts: dict[str, int] = dict.fromkeys(sorted(_REVIEW_STATES), 0)
        target_type_counts: dict[str, int] = {}
        for item in overrides:
            review_state = str(item.get("review_state") or "")
            target_type = str(item.get("target_type") or "")
            if review_state in counts:
                counts[review_state] += 1
            if target_type:
                target_type_counts[target_type] = target_type_counts.get(target_type, 0) + 1
        return {
            "workspace_id": workspace_id,
            "override_count": len(overrides),
            "review_state_counts": counts,
            "target_type_counts": target_type_counts,
        }

    # ── Evidence: extended queries ────────────────────────────

    def search_evidence(
        self,
        query: str,
        category: str | None = None,
        min_relevance: int | None = None,
        limit: int = 50,
    ) -> dict:
        """Search evidence items by text across key_quote, summary, and notes.

        Returns:
            {"items": [...], "total": int, "query": str}
        """
        return search_evidence_impl(
            self,
            query=query,
            category=category,
            min_relevance=min_relevance,
            limit=limit,
        )

    def evidence_timeline(
        self,
        category: str | None = None,
        min_relevance: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Return evidence items in chronological order for narrative building.

        Args:
            category: Filter by evidence category.
            min_relevance: Minimum relevance score.
            limit: Maximum items to return (None = unlimited).
            offset: Number of items to skip (for pagination).

        Returns:
            List of evidence items ordered by date ascending.
        """
        return evidence_timeline_impl(
            self,
            category=category,
            min_relevance=min_relevance,
            limit=limit,
            offset=offset,
        )

    def evidence_categories(self) -> list[dict]:
        """Return all canonical categories with current evidence counts.

        Returns:
            List of {"category": str, "count": int} for all 10 canonical categories.
        """
        return evidence_categories_impl(self)
