"""Evidence items: creation, quote verification, updates, search, statistics, and provenance."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, ClassVar

from ..locking import ArchiveRepository, archive_repository
from ..session import ArchiveSession
from ..sql import validate_column_update_pairs as _validate_column_update_pairs
from .custody import CustodyRepository, compute_content_hash
from .evidence_queries import evidence_categories as _evidence_categories
from .evidence_queries import evidence_stats as _evidence_stats
from .evidence_queries import evidence_timeline as _evidence_timeline
from .evidence_queries import get_evidence as _get_evidence
from .evidence_queries import list_evidence as _list_evidence
from .evidence_queries import quote_verification_state_for_evidence
from .evidence_queries import search_evidence as _search_evidence
from .evidence_queries import verify_evidence_quotes as _verify_evidence_quotes


def _decode_locator_json(value: Any) -> dict[str, Any]:
    """Copy or decode locator metadata, failing closed to an empty mapping."""
    if isinstance(value, dict):
        return dict(value)
    raw = " ".join(str(value or "").split()).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class _EvidenceAddContext:
    """Collect state shared while enriching a new evidence record."""

    email_uid: str
    category: str
    key_quote: str
    summary: str
    relevance: int
    recipients: str
    notes: str
    verified: int
    content_hash: str
    candidate_kind: str
    provenance: dict | None
    document_locator: dict | None
    context: dict | None


def _new_evidence_payload(
    evidence_id: int,
    email_row: sqlite3.Row,
    request: _EvidenceAddContext,
) -> dict[str, Any]:
    """Build the public payload returned after creating an evidence item."""
    return {
        "id": evidence_id,
        "email_uid": request.email_uid,
        "category": request.category,
        "key_quote": request.key_quote,
        "summary": request.summary,
        "relevance": request.relevance,
        "sender_name": email_row["sender_name"],
        "sender_email": email_row["sender_email"],
        "date": email_row["date"],
        "recipients": request.recipients,
        "subject": email_row["subject"],
        "notes": request.notes,
        "verified": request.verified,
        "content_hash": request.content_hash,
        "candidate_kind": request.candidate_kind,
        "provenance": request.provenance or {},
        "document_locator": request.document_locator or {},
        "context": request.context or {},
    }


@archive_repository
class EvidenceRepository(ArchiveRepository):
    """Evidence item CRUD, verification, search, statistics, and provenance."""

    def __init__(self, session: ArchiveSession, *, custody: CustodyRepository) -> None:
        super().__init__(session)
        self._custody = custody

    EVIDENCE_CATEGORIES: ClassVar[list[str]] = [
        "general",
        "fact",
        "decision",
        "action_item",
        "commitment",
        "contradiction",
        "chronology",
        "provenance",
        "quote_repair",
        "omission",
        "risk",
        "requirement",
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
            category: User-defined evidence category (e.g. fact, decision, contradiction).
            key_quote: Exact quote from the email body.
            summary: Brief description of why this is evidence.
            relevance: 1-5 rating (1=tangential, 5=critical).
            notes: Optional analyst notes.

        Returns:
            Dict with the created evidence item including id and verified status.

        Raises:
            ValueError: If email_uid does not exist in the database.
        """
        relevance = max(1, min(5, int(relevance)))
        category = str(category).strip()
        if not category:
            raise ValueError("Evidence category must not be empty")
        if len(category) > 80:
            raise ValueError("Evidence category must not exceed 80 characters")

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
            self.conn,
            email_uid=email_uid,
            quote=key_quote,
            candidate_kind=candidate_kind,
            document_locator=document_locator or {},
        )
        verified = 1 if verification.get("state") == "exact_verified" else 0

        content_hash = compute_content_hash(f"{email_uid}|{category}|{key_quote}")

        new_id = self._insert_evidence_item(
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
            email_uid=email_uid,
            category=category,
            relevance=relevance,
            summary=summary,
            content_hash=content_hash,
        )
        return _new_evidence_payload(
            new_id,
            email_row,
            _EvidenceAddContext(
                email_uid,
                category,
                key_quote,
                summary,
                relevance,
                recipients,
                notes,
                verified,
                content_hash,
                candidate_kind,
                provenance,
                document_locator,
                context,
            ),
        )

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
        return _list_evidence(
            self.conn,
            category=category,
            min_relevance=min_relevance,
            email_uid=email_uid,
            limit=limit,
            offset=offset,
        )

    def get_evidence(self, evidence_id: int) -> dict | None:
        """Get a single evidence item by ID."""
        return _get_evidence(self.conn, evidence_id)

    def update_evidence(self, evidence_id: int, **fields) -> bool:
        """Update fields on an evidence item.

        Allowed fields: category, key_quote, summary, relevance, notes.
        Sets updated_at automatically. Re-verifies if key_quote changes.
        Logs a custody event with a snapshot of old values.

        Returns:
            True if the item was updated, False if not found.
        """
        allowed = {"category", "key_quote", "summary", "relevance", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False

        # Check item exists and snapshot old values
        existing = self.conn.execute(
            "SELECT * FROM evidence_items WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        if not existing:
            return False
        old_values = {k: existing[k] for k in updates}
        updates, new_hash = self._prepare_evidence_updates(existing, updates)
        return self._execute_evidence_update(evidence_id, updates, old_values, new_hash, allowed)

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
                self._custody.log_custody_event(
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
        return _verify_evidence_quotes(self.conn)

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
        return _evidence_stats(self.conn, category=category, min_relevance=min_relevance)

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
        return _search_evidence(
            self.conn,
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
        return _evidence_timeline(
            self.conn,
            category=category,
            min_relevance=min_relevance,
            limit=limit,
            offset=offset,
        )

    def evidence_categories(self) -> list[dict]:
        """Return suggested and user-defined categories with current evidence counts.

        Returns:
            List of {"category": str, "count": int} entries.
        """
        return _evidence_categories(self.conn, self.EVIDENCE_CATEGORIES)

    def quote_verification_state(
        self,
        *,
        email_uid: str,
        quote: str,
        candidate_kind: str = "",
        document_locator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify one quote against the message's artifact-scoped surfaces without persisting anything."""
        return quote_verification_state_for_evidence(
            self.conn,
            email_uid=email_uid,
            quote=quote,
            candidate_kind=candidate_kind,
            document_locator=document_locator,
        )

    def evidence_provenance(self, evidence_id: int) -> dict:
        """Full provenance for evidence: item details, source email, custody history."""
        item = self.get_evidence(evidence_id)
        if not item:
            return {"error": f"Evidence not found: {evidence_id}"}

        email_prov = self._custody.email_provenance(item["email_uid"])

        evidence_events = self._custody.get_custody_chain(
            target_type="evidence",
            target_id=str(evidence_id),
        )

        return {
            "evidence": item,
            "source_email": email_prov,
            "custody_events": evidence_events,
        }

    # ── Private persistence steps ────────────────────────────

    def _insert_evidence_item(
        self,
        values: tuple[Any, ...],
        *,
        email_uid: str,
        category: str,
        relevance: int,
        summary: str,
        content_hash: str,
    ) -> int:
        """Insert evidence item while preserving the invariants of evidence database persistence."""
        try:
            cur = self.conn.execute(
                """INSERT INTO evidence_items
                   (email_uid, category, key_quote, summary, relevance,
                    sender_name, sender_email, date, recipients, subject, notes, verified,
                    content_hash, candidate_kind, provenance_json, document_locator_json, context_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cur.lastrowid is None:  # pragma: no cover - INSERT always sets lastrowid
                raise RuntimeError("Failed to obtain lastrowid after evidence INSERT")
            evidence_id = int(cur.lastrowid)
            self._custody.log_custody_event(
                "evidence_add",
                target_type="evidence",
                target_id=str(evidence_id),
                details={"email_uid": email_uid, "category": category, "relevance": relevance, "summary": summary[:200]},
                content_hash=content_hash,
                commit=False,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return evidence_id

    def _prepare_evidence_updates(self, existing: sqlite3.Row, updates: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Validate mutable evidence fields and collect SQL assignments and values."""
        if "relevance" in updates and updates["relevance"] is not None:
            updates["relevance"] = max(1, min(5, int(updates["relevance"])))
        if "category" in updates:
            category = str(updates["category"]).strip()
            if not category:
                raise ValueError("Evidence category must not be empty")
            if len(category) > 80:
                raise ValueError("Evidence category must not exceed 80 characters")
            updates["category"] = category
        if "key_quote" in updates:
            verification = quote_verification_state_for_evidence(
                self.conn,
                email_uid=str(existing["email_uid"] or ""),
                quote=updates["key_quote"].strip(),
                candidate_kind=str(existing["candidate_kind"] or ""),
                document_locator=_decode_locator_json(existing["document_locator_json"]),
            )
            updates["verified"] = int(verification.get("state") == "exact_verified")
        category = updates.get("category", existing["category"])
        key_quote = updates.get("key_quote", existing["key_quote"])
        content_hash = compute_content_hash(f"{existing['email_uid']}|{category}|{key_quote}")
        updates["content_hash"] = content_hash
        return updates, content_hash

    def _execute_evidence_update(
        self,
        evidence_id: int,
        updates: dict[str, Any],
        old_values: dict[str, Any],
        content_hash: str,
        allowed: set[str],
    ) -> bool:
        """Apply a prepared evidence update and return whether a row changed."""
        set_clause = _validate_column_update_pairs(updates, allowed_columns=allowed | {"content_hash", "verified"})
        set_clause += ", updated_at = datetime('now')"
        try:
            cur = self.conn.execute(
                f"UPDATE evidence_items SET {set_clause} WHERE id = ?",  # nosec B608
                [*updates.values(), evidence_id],
            )
            if cur.rowcount > 0:
                self._custody.log_custody_event(
                    "evidence_update",
                    target_type="evidence",
                    target_id=str(evidence_id),
                    details={
                        "old_values": old_values,
                        "new_values": {key: value for key, value in updates.items() if key != "content_hash"},
                    },
                    content_hash=content_hash,
                    commit=False,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return cur.rowcount > 0
