"""Candidate persistence and evidence-artifact reconciliation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _EvidenceCandidateRequest:
    """Describe the normalized inputs for inserting an evidence candidate."""

    run_id: str
    phase_id: str
    wave_id: str
    wave_label: str
    question_ids: list[str]
    email_uid: str | None
    candidate_kind: str
    quote_candidate: str
    summary: str
    category_hint: str
    rank: int
    score: float
    verification_status: str
    verified_exact: bool
    subject: str
    sender_name: str
    sender_email: str
    date: str
    conversation_id: str
    matched_query_lanes: list[str]
    matched_query_queries: list[str]
    provenance: dict | None = None
    context: dict | None = None


def _evidence_candidate_request(values: dict[str, Any]) -> _EvidenceCandidateRequest:
    """Validate and normalize caller inputs for an evidence candidate insert."""
    return _EvidenceCandidateRequest(**values)


def _candidate_content_hash(db: Any, request: _EvidenceCandidateRequest) -> str:
    """Hash candidate content and locator fields for deduplication."""
    return db.compute_content_hash(
        json.dumps(
            {
                "phase_id": request.phase_id,
                "email_uid": request.email_uid or "",
                "candidate_kind": request.candidate_kind,
                "quote_candidate": request.quote_candidate,
                "provenance": request.provenance or {},
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )


def _candidate_insert_values(request: _EvidenceCandidateRequest, content_hash: str) -> tuple[Any, ...]:
    """Order normalized candidate fields to match the evidence SQL insert."""
    return (
        request.run_id,
        request.phase_id,
        request.wave_id,
        request.wave_label,
        json.dumps(request.question_ids, ensure_ascii=False),
        request.email_uid,
        request.candidate_kind,
        request.quote_candidate,
        request.summary,
        request.category_hint,
        request.rank,
        request.score,
        request.verification_status,
        int(request.verified_exact),
        request.subject,
        request.sender_name,
        request.sender_email,
        request.date,
        request.conversation_id,
        json.dumps(request.matched_query_lanes, ensure_ascii=False),
        json.dumps(request.matched_query_queries, ensure_ascii=False),
        json.dumps(request.provenance or {}, ensure_ascii=False),
        json.dumps(request.context or {}, ensure_ascii=False),
        "harvested",
        None,
        content_hash,
    )


def _insert_evidence_candidate(db: Any, request: _EvidenceCandidateRequest, content_hash: str) -> int:
    """Insert evidence candidate while preserving the invariants of evidence database persistence."""
    try:
        cur = db.conn.execute(
            """INSERT INTO evidence_candidates(
                   run_id, phase_id, wave_id, wave_label, question_ids_json, email_uid,
                   candidate_kind, quote_candidate, summary, category_hint, rank, score,
                   verification_status, verified_exact, subject, sender_name, sender_email,
                   date, conversation_id, matched_query_lanes_json, matched_query_queries_json,
                   provenance_json, context_json, status, promoted_evidence_id, content_hash
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _candidate_insert_values(request, content_hash),
        )
        candidate_id = int(cur.lastrowid)
        db.log_custody_event(
            "evidence_candidate_add",
            target_type="evidence_candidate",
            target_id=str(candidate_id),
            details={
                "run_id": request.run_id,
                "phase_id": request.phase_id,
                "wave_id": request.wave_id,
                "candidate_kind": request.candidate_kind,
                "email_uid": request.email_uid or "",
                "verified_exact": bool(request.verified_exact),
            },
            content_hash=content_hash,
            commit=False,
        )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise
    return candidate_id


def add_evidence_candidate_impl(db: Any, **values: Any) -> dict:
    """Persist one harvested evidence candidate for a wave run."""
    request = _evidence_candidate_request(values)
    content_hash = _candidate_content_hash(db, request)
    existing = db.conn.execute(
        """SELECT *
           FROM evidence_candidates
           WHERE run_id = ? AND wave_id = ? AND content_hash = ?""",
        (request.run_id, request.wave_id, content_hash),
    ).fetchone()
    if existing:
        payload = dict(existing)
        payload["inserted"] = False
        return payload

    candidate_id = _insert_evidence_candidate(db, request, content_hash)
    created = db.conn.execute("SELECT * FROM evidence_candidates WHERE id = ?", (candidate_id,)).fetchone()
    payload = dict(created) if created else {"id": candidate_id, "content_hash": content_hash}
    payload["inserted"] = True
    return payload


def mark_evidence_candidate_promoted_impl(db: Any, candidate_id: int, *, evidence_id: int) -> bool:
    """Mark a harvested candidate as promoted into the durable evidence corpus."""
    try:
        cur = db.conn.execute(
            """UPDATE evidence_candidates
               SET status = 'promoted', promoted_evidence_id = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (evidence_id, candidate_id),
        )
        if cur.rowcount > 0:
            db.log_custody_event(
                "evidence_candidate_promote",
                target_type="evidence_candidate",
                target_id=str(candidate_id),
                details={"evidence_id": evidence_id},
                commit=False,
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise
    return cur.rowcount > 0


def _clean_identity_text(value: Any) -> str:
    """Collapse identity-field whitespace before comparison or hashing."""
    return " ".join(str(value or "").split()).strip()


def _coerce_non_negative_int(value: Any) -> int | None:
    """Parse a non-negative offset, returning ``None`` for invalid values."""
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return None
    return parsed if parsed >= 0 else None


def _decode_locator_json(value: Any) -> dict[str, Any]:
    """Copy or decode locator metadata, failing closed to an empty mapping."""
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
    """Normalize locator identities, scopes, hashes, and offsets for stable persistence."""
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
    """Compare stable artifact identifiers before allowing evidence reconciliation."""
    normalized_candidate_kind = _clean_identity_text(candidate_kind).casefold()
    normalized_existing_kind = _clean_identity_text(existing_kind).casefold()
    if not _artifact_kinds_compatible(normalized_candidate_kind, normalized_existing_kind):
        return False
    if normalized_candidate_kind == "attachment":
        attachment_match = _attachment_identity_match(candidate_locator, existing_locator)
        if attachment_match is not None:
            return attachment_match
    identity_keys = (
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
    if _artifact_locator_conflict(candidate_locator, existing_locator, identity_keys):
        return False
    if normalized_candidate_kind == "attachment":
        return True
    if _positive_artifact_locator_match(candidate_locator, existing_locator):
        return True
    has_candidate_artifact_identity = any(candidate_locator.get(key) not in (None, "") for key in identity_keys)
    if not has_candidate_artifact_identity and normalized_candidate_kind in {"", "body"}:
        return normalized_existing_kind in {"", "body"}
    return False


def _artifact_kinds_compatible(candidate_kind: str, existing_kind: str) -> bool:
    """Return whether two artifact kinds may refer to the same source surface."""
    if not candidate_kind:
        return True
    if existing_kind and existing_kind != candidate_kind:
        return False
    return not all((candidate_kind != "attachment", existing_kind == "attachment"))


def _shared_locator_value(candidate: dict[str, Any], existing: dict[str, Any], key: str) -> bool:
    """Return a non-empty locator value only when both records agree."""
    candidate_value = _clean_identity_text(candidate.get(key)).casefold()
    existing_value = _clean_identity_text(existing.get(key)).casefold()
    return all((candidate_value, existing_value, candidate_value == existing_value))


def _attachment_identity_match(candidate: dict[str, Any], existing: dict[str, Any]) -> bool | None:
    """Compare attachment IDs, hashes, indexes, and filenames for identity."""
    if _shared_locator_value(candidate, existing, "attachment_id"):
        return True
    if _shared_locator_value(candidate, existing, "content_sha256"):
        return True
    candidate_filename = _clean_identity_text(candidate.get("attachment_filename")).casefold()
    existing_filename = _clean_identity_text(existing.get("attachment_filename")).casefold()
    if not all((candidate_filename, existing_filename, candidate_filename == existing_filename)):
        return False
    return None


def _artifact_locator_conflict(candidate: dict[str, Any], existing: dict[str, Any], keys: tuple[str, ...]) -> bool:
    """Detect contradictory locator fields that prevent safe evidence merging."""
    for key in keys:
        candidate_value = candidate.get(key)
        existing_value = existing.get(key)
        if all((candidate_value not in (None, ""), existing_value not in (None, ""), candidate_value != existing_value)):
            return True
    return False


def _positive_artifact_locator_match(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    """Require at least one stable locator field to match positively."""
    direct_match = any(_shared_locator_value(candidate, existing, key) for key in ("evidence_handle", "chunk_id"))
    candidate_segment = (candidate.get("segment_type"), candidate.get("segment_ordinal"))
    existing_segment = (existing.get("segment_type"), existing.get("segment_ordinal"))
    segment_match = all(candidate_segment) and all(existing_segment) and candidate_segment == existing_segment
    snippet_keys = ("snippet_start", "snippet_end")
    snippet_match = all(candidate.get(key) is not None for key in snippet_keys) and all(
        candidate.get(key) == existing.get(key) for key in snippet_keys
    )
    return any((direct_match, segment_match, snippet_match))


def find_evidence_by_email_quote_impl(db: Any, *, email_uid: str, key_quote: str) -> dict | None:
    """Return an existing evidence item matching one email UID and exact quote."""
    row = db.conn.execute(
        """SELECT *
           FROM evidence_items
           WHERE email_uid = ? AND lower(key_quote) = lower(?)""",
        (email_uid, key_quote),
    ).fetchone()
    return dict(row) if row else None


def find_evidence_by_email_artifact_quote_impl(
    db: Any,
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
    rows = db.conn.execute(
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
