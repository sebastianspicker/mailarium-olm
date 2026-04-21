"""Read/query helpers for evidence management."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .db_schema import _escape_like

_WS_RE = re.compile(r"[\s\xa0]+")
_HYPHENATED_BREAK_RE = re.compile(r"(?<=\w)[\-‐‑‒–]\s*\n\s*(?=\w)")
_PUNCT_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "’": "'",
        "‘": "'",
        "‚": "'",
        "–": "-",
        "—": "-",
        "−": "-",
        "…": "...",
    }
)
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_QUOTE_VERIFICATION_FIELDS = ("forensic_body_text", "body_text", "raw_body_text")
_GERMAN_TRANSLITERATION = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)


def _decode_json_text(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _decode_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for key in ("provenance_json", "document_locator_json", "context_json"):
        decoded[key.removesuffix("_json")] = _decode_json_text(decoded.get(key))
    return decoded


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace (including nbsp) to single spaces and lowercase."""
    normalized = unicodedata.normalize("NFKC", text).translate(_PUNCT_TRANSLATION)
    return _WS_RE.sub(" ", normalized.strip()).casefold()


def _normalize_alnum(text: str) -> str:
    """Return an alphanumeric-only fallback for OCR/punctuation drift."""
    return _NON_ALNUM_RE.sub("", _normalize_ws(text))


def _normalize_near_exact(text: str) -> str:
    """Return conservative German/OCR-tolerant normalization for near-exact verification."""
    normalized = unicodedata.normalize("NFKC", text).translate(_PUNCT_TRANSLATION)
    normalized = _HYPHENATED_BREAK_RE.sub("", normalized)
    normalized = normalized.replace("ﬁ", "fi").replace("ﬂ", "fl")
    normalized = normalized.casefold().translate(_GERMAN_TRANSLITERATION)
    normalized = _WS_RE.sub(" ", normalized.strip())
    return normalized


def _normalize_near_exact_alnum(text: str) -> str:
    return _NON_ALNUM_RE.sub("", _normalize_near_exact(text))


def _match_state_against_surface(quote: str, surface_text: str) -> str:
    normalized_quote = _normalize_ws(quote)
    if not normalized_quote:
        return ""
    normalized_surface = _normalize_ws(surface_text)
    if normalized_quote and normalized_quote in normalized_surface:
        return "exact"

    normalized_quote_alnum = _normalize_alnum(quote)
    normalized_surface_alnum = _normalize_alnum(surface_text)
    if len(normalized_quote_alnum) >= 24 and normalized_quote_alnum in normalized_surface_alnum:
        return "exact"

    near_quote_alnum = _normalize_near_exact_alnum(quote)
    near_surface_alnum = _normalize_near_exact_alnum(surface_text)
    if len(near_quote_alnum) >= 24 and near_quote_alnum in near_surface_alnum:
        return "near_exact_verified"
    return ""


def _candidate_locator_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return _decode_json_text(row.get("document_locator_json"))


def _candidate_kind_from_row(row: dict[str, Any]) -> str:
    return str(row.get("candidate_kind") or "").strip().casefold()


def _surface_rows_for_evidence(
    db: Any,
    *,
    email_uid: str,
    candidate_kind: str,
    locator: dict[str, Any],
) -> list[tuple[str, str]]:
    surfaces: list[tuple[str, str]] = []
    conn = db.conn

    body_row = conn.execute(
        "SELECT forensic_body_text, body_text, raw_body_text, subject FROM emails WHERE uid = ?",
        (email_uid,),
    ).fetchone()
    if body_row:
        body_render_source = str(locator.get("body_render_source") or "").strip()
        if candidate_kind != "attachment":
            if body_render_source == "forensic_body_text":
                surfaces.append(("forensic_body_text", str(body_row["forensic_body_text"] or "")))
            elif body_render_source == "raw_body_text":
                surfaces.append(("raw_body_text", str(body_row["raw_body_text"] or "")))
            elif body_render_source == "body_text":
                surfaces.append(("body_text", str(body_row["body_text"] or "")))
            else:
                for field in (*_QUOTE_VERIFICATION_FIELDS, "subject"):
                    surfaces.append((field, str(body_row[field] or "")))

    if candidate_kind == "attachment":
        rows = conn.execute(
            """SELECT name, attachment_id, content_sha256, extracted_text, text_preview
                   FROM attachments
                  WHERE email_uid = ?""",
            (email_uid,),
        ).fetchall()
        target_attachment_id = str(locator.get("attachment_id") or "").strip().casefold()
        target_content_sha = str(locator.get("content_sha256") or "").strip().casefold()
        target_filename = str(locator.get("attachment_filename") or "").strip().casefold()
        filtered: list[Any] = []
        for row in rows:
            attachment_id = str(row["attachment_id"] or "").strip().casefold()
            content_sha = str(row["content_sha256"] or "").strip().casefold()
            filename = str(row["name"] or "").strip().casefold()
            if target_attachment_id and attachment_id and attachment_id != target_attachment_id:
                continue
            if target_content_sha and content_sha and content_sha != target_content_sha:
                continue
            if target_filename and filename and filename != target_filename:
                continue
            filtered.append(row)
        attachment_rows = filtered if filtered else ([] if (target_attachment_id or target_content_sha) else rows)
        for row in attachment_rows:
            text_value = str(row["extracted_text"] or row["text_preview"] or "")
            if text_value.strip():
                surfaces.append(("attachment", text_value))

    segment_rows = conn.execute(
        """SELECT segment_type, ordinal, text
               FROM message_segments
              WHERE email_uid = ?
              ORDER BY ordinal ASC""",
        (email_uid,),
    ).fetchall()
    if segment_rows and candidate_kind in {"segment", "body"}:
        target_segment_type = str(locator.get("segment_type") or "").strip()
        target_segment_ordinal_raw = locator.get("segment_ordinal")
        target_segment_ordinal_text = str(target_segment_ordinal_raw or "").strip()
        try:
            target_segment_ordinal = int(target_segment_ordinal_text) if target_segment_ordinal_text else 0
        except (TypeError, ValueError):
            target_segment_ordinal = 0
        filtered_segments: list[Any] = []
        for row in segment_rows:
            if target_segment_type and str(row["segment_type"] or "").strip() != target_segment_type:
                continue
            if target_segment_ordinal and int(row["ordinal"] or 0) != target_segment_ordinal:
                continue
            filtered_segments.append(row)
        segment_candidates = (
            filtered_segments
            if filtered_segments
            else ([] if (target_segment_type or target_segment_ordinal) and candidate_kind == "segment" else segment_rows)
        )
        for row in segment_candidates:
            text_value = str(row["text"] or "")
            if text_value.strip():
                surfaces.append(("segment", text_value))

    deduped_surfaces: list[tuple[str, str]] = []
    seen_texts: set[tuple[str, str]] = set()
    for surface_name, text_value in surfaces:
        compact = text_value.strip()
        if not compact:
            continue
        dedupe_key = (surface_name, _normalize_ws(compact))
        if dedupe_key in seen_texts:
            continue
        seen_texts.add(dedupe_key)
        deduped_surfaces.append((surface_name, compact))
    return deduped_surfaces


def quote_verification_state_for_evidence(
    db: Any,
    *,
    email_uid: str,
    quote: str,
    candidate_kind: str = "",
    document_locator: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify one quote against artifact-scoped surfaces and return verification state."""
    compact_quote = str(quote or "").strip()
    if not compact_quote:
        return {"state": "unverified", "matched_surface": "", "has_surfaces": False}

    locator = document_locator if isinstance(document_locator, dict) else {}
    normalized_kind = str(candidate_kind or "").strip().casefold()
    surfaces = _surface_rows_for_evidence(
        db,
        email_uid=email_uid,
        candidate_kind=normalized_kind,
        locator=locator,
    )
    if not surfaces:
        return {"state": "orphaned", "matched_surface": "", "has_surfaces": False}

    near_exact_surface = ""
    for surface_name, surface_text in surfaces:
        state = _match_state_against_surface(compact_quote, surface_text)
        if state == "exact":
            return {
                "state": "exact_verified",
                "matched_surface": surface_name,
                "has_surfaces": True,
            }
        if state == "near_exact_verified" and not near_exact_surface:
            near_exact_surface = surface_name

    if near_exact_surface:
        return {
            "state": "near_exact_verified",
            "matched_surface": near_exact_surface,
            "has_surfaces": True,
        }
    return {"state": "unverified", "matched_surface": "", "has_surfaces": True}


def has_quote_verification_body(
    *,
    forensic_body_text: str | None = None,
    body_text: str | None = None,
    raw_body_text: str | None = None,
    attachment_text: str | None = None,
    segment_text: str | None = None,
) -> bool:
    """Return whether at least one usable stored body source exists."""
    return any(
        str(value or "").strip() for value in (forensic_body_text, body_text, raw_body_text, attachment_text, segment_text)
    )


def quote_matches_email_bodies(
    quote: str,
    *,
    forensic_body_text: str | None = None,
    body_text: str | None = None,
    raw_body_text: str | None = None,
    attachment_text: str | None = None,
    segment_text: str | None = None,
) -> bool:
    """Return whether a quote matches any stored body representation for the email."""
    normalized_quote = _normalize_ws(quote)
    if not normalized_quote:
        return False

    seen_bodies: set[str] = set()
    for field_value in (forensic_body_text, body_text, raw_body_text, attachment_text, segment_text):
        body_text_value = str(field_value or "").strip()
        if not body_text_value:
            continue
        normalized_body = _normalize_ws(body_text_value)
        if normalized_body in seen_bodies:
            continue
        seen_bodies.add(normalized_body)
        if normalized_quote in normalized_body:
            return True
        normalized_quote_alnum = _normalize_alnum(quote)
        normalized_body_alnum = _normalize_alnum(body_text_value)
        if len(normalized_quote_alnum) >= 24 and normalized_quote_alnum in normalized_body_alnum:
            return True
    return False


def list_evidence_impl(
    db: Any,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
    email_uid: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List evidence items with optional filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if min_relevance is not None:
        conditions.append("relevance >= ?")
        params.append(min_relevance)
    if email_uid:
        conditions.append("email_uid = ?")
        params.append(email_uid)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec
        params,
    ).fetchone()
    total = total_row["c"]

    rows = db.conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ? OFFSET ?",  # nosec
        [*params, limit, offset],
    ).fetchall()

    return {
        "items": [_decode_evidence_row(dict(r)) for r in rows],
        "total": total,
    }


def get_evidence_impl(db: Any, evidence_id: int) -> dict | None:
    """Get a single evidence item by ID."""
    row = db.conn.execute(
        "SELECT * FROM evidence_items WHERE id = ?",
        (evidence_id,),
    ).fetchone()
    return _decode_evidence_row(dict(row)) if row else None


def verify_evidence_quotes_impl(db: Any) -> dict:
    """Verify all evidence quotes against artifact-scoped evidence surfaces."""
    rows = db.conn.execute(
        """SELECT ei.id, ei.key_quote, ei.email_uid, ei.candidate_kind, ei.document_locator_json
           FROM evidence_items ei
           LEFT JOIN emails e ON ei.email_uid = e.uid"""
    ).fetchall()

    verified_count = 0
    failed_count = 0
    orphaned_count = 0
    near_exact_count = 0
    failures: list[dict] = []
    verified_ids: list[tuple[int]] = []
    failed_ids: list[tuple[int]] = []

    for row in rows:
        payload = dict(row)
        quote = str(payload.get("key_quote") or "").strip()
        email_uid = str(payload.get("email_uid") or "")
        verification = quote_verification_state_for_evidence(
            db,
            email_uid=email_uid,
            quote=quote,
            candidate_kind=_candidate_kind_from_row(payload),
            document_locator=_candidate_locator_from_row(payload),
        )

        if verification["state"] == "orphaned":
            orphaned_count += 1
            failed_ids.append((payload["id"],))
            failures.append(
                {
                    "evidence_id": payload["id"],
                    "key_quote_preview": quote[:80] + ("..." if len(quote) > 80 else ""),
                    "email_uid": email_uid,
                    "orphaned": True,
                }
            )
            continue

        if verification["state"] == "exact_verified":
            verified_count += 1
            verified_ids.append((payload["id"],))
        elif verification["state"] == "near_exact_verified":
            near_exact_count += 1
            failed_ids.append((payload["id"],))
        else:
            failed_count += 1
            failed_ids.append((payload["id"],))
            failures.append(
                {
                    "evidence_id": payload["id"],
                    "key_quote_preview": quote[:80] + ("..." if len(quote) > 80 else ""),
                    "email_uid": email_uid,
                }
            )

    if verified_ids:
        db.conn.executemany(
            "UPDATE evidence_items SET verified = 1 WHERE id = ?",
            verified_ids,
        )
    if failed_ids:
        db.conn.executemany(
            "UPDATE evidence_items SET verified = 0 WHERE id = ?",
            failed_ids,
        )
    db.conn.commit()
    return {
        "verified": verified_count,
        "failed": failed_count,
        "near_exact": near_exact_count,
        "orphaned": orphaned_count,
        "total": verified_count + failed_count + near_exact_count + orphaned_count,
        "failures": failures,
    }


def evidence_stats_impl(
    db: Any,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
) -> dict:
    """Return evidence collection statistics, optionally filtered."""
    where_manageres: list[str] = []
    params: list[Any] = []
    if category:
        where_manageres.append("category = ?")
        params.append(category)
    if min_relevance is not None:
        where_manageres.append("relevance >= ?")
        params.append(min_relevance)
    where_sql = (" WHERE " + " AND ".join(where_manageres)) if where_manageres else ""

    total_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql}",  # nosec
        params,
    ).fetchone()
    total = total_row["c"]

    verified_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql} {'AND' if where_manageres else 'WHERE'} verified = 1",  # nosec
        params,
    ).fetchone()
    verified = verified_row["c"]

    cat_rows = db.conn.execute(
        f"SELECT category, COUNT(*) AS count FROM evidence_items{where_sql} GROUP BY category ORDER BY count DESC",  # nosec
        params,
    ).fetchall()

    rel_rows = db.conn.execute(
        f"SELECT relevance, COUNT(*) AS count FROM evidence_items{where_sql} GROUP BY relevance ORDER BY relevance DESC",  # nosec
        params,
    ).fetchall()

    return {
        "total": total,
        "verified": verified,
        "unverified": total - verified,
        "by_category": [dict(r) for r in cat_rows],
        "by_relevance": [dict(r) for r in rel_rows],
    }


def evidence_candidate_stats_impl(
    db: Any,
    *,
    run_id: str | None = None,
    phase_id: str | None = None,
) -> dict:
    """Return harvested evidence-candidate statistics, optionally scoped to one run."""
    where_manageres: list[str] = []
    params: list[Any] = []
    if run_id:
        where_manageres.append("run_id = ?")
        params.append(run_id)
    if phase_id:
        where_manageres.append("phase_id = ?")
        params.append(phase_id)
    where_sql = (" WHERE " + " AND ".join(where_manageres)) if where_manageres else ""

    totals = db.conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN candidate_kind = 'body' THEN 1 ELSE 0 END) AS body_total, "
        "SUM(CASE WHEN candidate_kind = 'attachment' THEN 1 ELSE 0 END) AS attachment_total, "
        "SUM(CASE WHEN verified_exact = 1 AND candidate_kind = 'body' THEN 1 ELSE 0 END) AS exact_body_total, "
        "SUM(CASE WHEN status = 'promoted' THEN 1 ELSE 0 END) AS promoted_total "
        f"FROM evidence_candidates{where_sql}",  # nosec
        params,
    ).fetchone()
    wave_rows = db.conn.execute(
        "SELECT wave_id, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'promoted' THEN 1 ELSE 0 END) AS promoted, "
        "SUM(CASE WHEN verified_exact = 1 AND candidate_kind = 'body' THEN 1 ELSE 0 END) AS exact_body_candidates "
        f"FROM evidence_candidates{where_sql} "  # nosec
        "GROUP BY wave_id "
        "ORDER BY wave_id ASC",
        params,
    ).fetchall()
    status_rows = db.conn.execute(
        "SELECT status, COUNT(*) AS count "
        f"FROM evidence_candidates{where_sql} "  # nosec
        "GROUP BY status "
        "ORDER BY count DESC",
        params,
    ).fetchall()
    return {
        "total": int((totals["total"] if totals else 0) or 0),
        "body_candidates": int((totals["body_total"] if totals else 0) or 0),
        "attachments": int((totals["attachment_total"] if totals else 0) or 0),
        "exact_body_candidates": int((totals["exact_body_total"] if totals else 0) or 0),
        "promoted": int((totals["promoted_total"] if totals else 0) or 0),
        "by_wave": [dict(row) for row in wave_rows],
        "by_status": [dict(row) for row in status_rows],
    }


def search_evidence_impl(
    db: Any,
    *,
    query: str,
    category: str | None = None,
    min_relevance: int | None = None,
    limit: int = 50,
) -> dict:
    """Search evidence items by text across key_quote, summary, and notes."""
    conditions = ["(key_quote LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\')"]
    pattern = f"%{_escape_like(query)}%"
    params: list[Any] = [pattern, pattern, pattern]

    if category:
        conditions.append("category = ?")
        params.append(category)
    if min_relevance is not None:
        conditions.append("relevance >= ?")
        params.append(min_relevance)

    where = " WHERE " + " AND ".join(conditions)

    total_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec
        params,
    ).fetchone()

    rows = db.conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ?",  # nosec
        [*params, limit],
    ).fetchall()

    return {
        "items": [_decode_evidence_row(dict(r)) for r in rows],
        "total": total_row["c"],
        "query": query,
    }


def evidence_timeline_impl(
    db: Any,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Return evidence items in chronological order for narrative building."""
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if min_relevance is not None:
        conditions.append("relevance >= ?")
        params.append(min_relevance)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"SELECT * FROM evidence_items{where} ORDER BY date ASC"  # nosec B608 — `where` is built from hardcoded condition strings; all values are bound as params
    if limit is not None and limit >= 0:
        sql += " LIMIT ?"
        params.append(limit)
    elif offset > 0:
        sql += " LIMIT -1"
    if offset > 0:
        sql += " OFFSET ?"
        params.append(offset)

    rows = db.conn.execute(sql, params).fetchall()
    return [_decode_evidence_row(dict(r)) for r in rows]


def evidence_categories_impl(db: Any) -> list[dict]:
    """Return all canonical categories with current evidence counts."""
    count_rows = db.conn.execute("SELECT category, COUNT(*) AS count FROM evidence_items GROUP BY category").fetchall()
    counts = {r["category"]: r["count"] for r in count_rows}
    return [{"category": cat, "count": counts.get(cat, 0)} for cat in db.EVIDENCE_CATEGORIES]
