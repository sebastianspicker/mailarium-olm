"""Quote verification and read-query helpers for the evidence repository."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from typing import Any

from ..sql import escape_like as _escape_like

_WS_RE = re.compile(r"\s+")
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
    """Decode a stored JSON object, returning an empty mapping when invalid."""
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
    """Replace stored ``*_json`` fields with decoded public mappings."""
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
    return "".join(character for character in _normalize_ws(text) if character.isascii() and character.isalnum())


def _remove_hyphenated_line_breaks(text: str) -> str:
    """Join word fragments separated by a hyphen and optional line whitespace."""
    hyphens = {"-", "‐", "‑", "‒", "–"}
    output: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character not in hyphens:
            output.append(character)
            index += 1
            continue
        join_target = _hyphen_join_target(text, index, output)
        if join_target is None:
            output.append(character)
            index += 1
            continue
        index = join_target
    return "".join(output)


def _hyphen_join_target(text: str, index: int, output: list[str]) -> int | None:
    """Normalize wrapped hyphenated text so near-exact matching can rejoin words."""
    if not output or not output[-1].isalnum():
        return None
    cursor = index + 1
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    if cursor >= len(text) or text[cursor] not in "\r\n":
        return None
    if text[cursor : cursor + 2] == "\r\n":
        cursor += 1
    cursor += 1
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    return cursor if cursor < len(text) and text[cursor].isalnum() else None


def _normalize_near_exact(text: str) -> str:
    """Return conservative German/OCR-tolerant normalization for near-exact verification."""
    normalized = unicodedata.normalize("NFKC", text).translate(_PUNCT_TRANSLATION)
    normalized = _remove_hyphenated_line_breaks(normalized)
    normalized = normalized.replace("ﬁ", "fi").replace("ﬂ", "fl")
    normalized = normalized.casefold().translate(_GERMAN_TRANSLITERATION)
    normalized = _WS_RE.sub(" ", normalized.strip())
    return normalized


def _normalize_near_exact_alnum(text: str) -> str:
    """Strip non-ASCII alphanumerics after OCR-tolerant quote normalization."""
    return "".join(character for character in _normalize_near_exact(text) if character.isascii() and character.isalnum())


def _match_state_against_surface(quote: str, surface_text: str) -> str:
    """Classify candidate text as exact, normalized, partial, or absent on a surface."""
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
    """Decode the artifact locator stored on an evidence candidate row."""
    return _decode_json_text(row.get("document_locator_json"))


def _candidate_kind_from_row(row: dict[str, Any]) -> str:
    """Normalize the candidate artifact kind used to choose searchable surfaces."""
    return str(row.get("candidate_kind") or "").strip().casefold()


def _surface_rows_for_evidence(
    conn: sqlite3.Connection,
    *,
    email_uid: str,
    candidate_kind: str,
    locator: dict[str, Any],
) -> list[tuple[str, str]]:
    """Load all persisted attachment surfaces relevant to an evidence row."""
    surfaces = [
        *_body_surfaces_for_evidence(conn, email_uid, candidate_kind, locator),
        *_attachment_surfaces_for_evidence(conn, email_uid, candidate_kind, locator),
        *_segment_surfaces_for_evidence(conn, email_uid, candidate_kind, locator),
    ]
    return _deduped_evidence_surfaces(surfaces)


def _body_surfaces_for_evidence(
    conn: sqlite3.Connection, email_uid: str, candidate_kind: str, locator: dict[str, Any]
) -> list[tuple[str, str]]:
    """Expose visible and source body variants as evidence-match surfaces."""
    body_row = conn.execute(
        "SELECT forensic_body_text, body_text, raw_body_text, subject FROM emails WHERE uid = ?",
        (email_uid,),
    ).fetchone()
    if body_row is None or candidate_kind == "attachment":
        return []
    render_source = str(locator.get("body_render_source") or "").strip()
    if render_source in {*_QUOTE_VERIFICATION_FIELDS}:
        return [(render_source, str(body_row[render_source] or ""))]
    return [(field, str(body_row[field] or "")) for field in (*_QUOTE_VERIFICATION_FIELDS, "subject")]


def _attachment_surfaces_for_evidence(
    conn: sqlite3.Connection, email_uid: str, candidate_kind: str, locator: dict[str, Any]
) -> list[tuple[str, str]]:
    """Expose normalized attachment surfaces for evidence matching."""
    if candidate_kind != "attachment":
        return []
    rows = conn.execute(
        """SELECT name, attachment_id, content_sha256, extracted_text, text_preview
               FROM attachments WHERE email_uid = ?""",
        (email_uid,),
    ).fetchall()
    targets = _attachment_surface_targets(locator)
    candidates = _attachment_surface_candidates(rows, targets)
    return _attachment_text_surfaces(candidates)


def _attachment_surface_targets(locator: dict[str, Any]) -> dict[str, str]:
    """Derive locator keys that narrow attachment-surface matching."""
    return {
        "attachment_id": str(locator.get("attachment_id") or "").strip().casefold(),
        "content_sha256": str(locator.get("content_sha256") or "").strip().casefold(),
        "name": str(locator.get("attachment_filename") or "").strip().casefold(),
    }


def _attachment_surface_candidates(rows: list[Any], targets: dict[str, str]) -> list[Any]:
    """Filter attachment surfaces to those compatible with candidate locator data."""
    filtered = [row for row in rows if _attachment_row_matches(row, targets)]
    identity_supplied = any((targets["attachment_id"], targets["content_sha256"]))
    return filtered if filtered else ([] if identity_supplied else rows)


def _attachment_text_surfaces(candidates: list[Any]) -> list[tuple[str, str]]:
    """Return non-empty text variants from an attachment row."""
    return [
        ("attachment", str(row["extracted_text"] or row["text_preview"] or ""))
        for row in candidates
        if str(row["extracted_text"] or row["text_preview"] or "").strip()
    ]


def _attachment_row_matches(row: Any, targets: dict[str, str]) -> bool:
    """Test candidate text and locator data against one attachment record."""
    values = {
        "attachment_id": str(row["attachment_id"] or "").strip().casefold(),
        "content_sha256": str(row["content_sha256"] or "").strip().casefold(),
        "name": str(row["name"] or "").strip().casefold(),
    }
    return all(not target or not values[key] or values[key] == target for key, target in targets.items())


def _segment_surfaces_for_evidence(
    conn: sqlite3.Connection, email_uid: str, candidate_kind: str, locator: dict[str, Any]
) -> list[tuple[str, str]]:
    """Load conversation segments that can substantiate an evidence candidate."""
    if candidate_kind not in {"segment", "body"}:
        return []
    rows = conn.execute(
        """SELECT segment_type, ordinal, text
               FROM message_segments
              WHERE email_uid = ?
              ORDER BY ordinal ASC""",
        (email_uid,),
    ).fetchall()
    segment_type = str(locator.get("segment_type") or "").strip()
    segment_ordinal = _safe_int(locator.get("segment_ordinal"))
    filtered = [row for row in rows if _segment_row_matches(row, segment_type, segment_ordinal)]
    target_supplied = any((segment_type, segment_ordinal))
    candidates = filtered if filtered else ([] if target_supplied and candidate_kind == "segment" else rows)
    return [("segment", str(row["text"] or "")) for row in candidates if str(row["text"] or "").strip()]


def _safe_int(value: Any) -> int:
    """Parse a stored segment ordinal, defaulting malformed values to zero."""
    try:
        return int(str(value or "0").strip())
    except TypeError, ValueError:
        return 0


def _segment_row_matches(row: Any, segment_type: str, segment_ordinal: int) -> bool:
    """Test candidate text and offsets against one conversation segment."""
    type_matches = not segment_type or str(row["segment_type"] or "").strip() == segment_type
    ordinal_matches = not segment_ordinal or int(row["ordinal"] or 0) == segment_ordinal
    return type_matches and ordinal_matches


def _deduped_evidence_surfaces(surfaces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Remove duplicate source surfaces while preserving their first-seen order."""
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
    conn: sqlite3.Connection,
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
        conn,
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


def list_evidence(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
    email_uid: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List evidence items with optional filters."""
    conditions, params = _evidence_filters(category, min_relevance, email_uid=email_uid)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec B608
        params,
    ).fetchone()
    total = total_row["c"]

    rows = conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ? OFFSET ?",  # nosec B608
        [*params, limit, offset],
    ).fetchall()

    return {
        "items": [_decode_evidence_row(dict(r)) for r in rows],
        "total": total,
    }


def get_evidence(conn: sqlite3.Connection, evidence_id: int) -> dict | None:
    """Get a single evidence item by ID."""
    row = conn.execute(
        "SELECT * FROM evidence_items WHERE id = ?",
        (evidence_id,),
    ).fetchone()
    return _decode_evidence_row(dict(row)) if row else None


def verify_evidence_quotes(conn: sqlite3.Connection) -> dict:
    """Verify all evidence quotes against artifact-scoped evidence surfaces."""
    rows = conn.execute(
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
            conn,
            email_uid=email_uid,
            quote=quote,
            candidate_kind=_candidate_kind_from_row(payload),
            document_locator=_candidate_locator_from_row(payload),
        )

        if verification["state"] == "orphaned":
            orphaned_count += 1
            failed_ids.append((payload["id"],))
            failures.append(_quote_failure(payload, quote, email_uid, orphaned=True))
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
            failures.append(_quote_failure(payload, quote, email_uid))

    if verified_ids:
        conn.executemany(
            "UPDATE evidence_items SET verified = 1 WHERE id = ?",
            verified_ids,
        )
    if failed_ids:
        conn.executemany(
            "UPDATE evidence_items SET verified = 0 WHERE id = ?",
            failed_ids,
        )
    conn.commit()
    return {
        "verified": verified_count,
        "failed": failed_count,
        "near_exact": near_exact_count,
        "orphaned": orphaned_count,
        "total": verified_count + failed_count + near_exact_count + orphaned_count,
        "failures": failures,
    }


def evidence_stats(
    conn: sqlite3.Connection,
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

    total_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql}",  # nosec B608
        params,
    ).fetchone()
    total = total_row["c"]

    verified_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql} {'AND' if where_manageres else 'WHERE'} verified = 1",  # nosec B608
        params,
    ).fetchone()
    verified = verified_row["c"]

    cat_rows = conn.execute(
        f"SELECT category, COUNT(*) AS count FROM evidence_items{where_sql} GROUP BY category ORDER BY count DESC",  # nosec B608
        params,
    ).fetchall()

    rel_rows = conn.execute(
        f"SELECT relevance, COUNT(*) AS count FROM evidence_items{where_sql} GROUP BY relevance ORDER BY relevance DESC",  # nosec B608
        params,
    ).fetchall()

    return {
        "total": total,
        "verified": verified,
        "unverified": total - verified,
        "by_category": [dict(r) for r in cat_rows],
        "by_relevance": [dict(r) for r in rel_rows],
    }


def search_evidence(
    conn: sqlite3.Connection,
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

    total_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec B608
        params,
    ).fetchone()

    rows = conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ?",  # nosec B608
        [*params, limit],
    ).fetchall()

    return {
        "items": [_decode_evidence_row(dict(r)) for r in rows],
        "total": total_row["c"],
        "query": query,
    }


def evidence_timeline(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Return evidence items in chronological order for narrative building."""
    conditions, params = _evidence_filters(category, min_relevance)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # B608: `where` is built from hardcoded condition strings; all values are bound as params.
    sql = f"SELECT * FROM evidence_items{where} ORDER BY date ASC"
    if limit is not None and limit >= 0:
        sql += " LIMIT ?"
        params.append(limit)
    elif offset > 0:
        sql += " LIMIT -1"
    if offset > 0:
        sql += " OFFSET ?"
        params.append(offset)

    rows = conn.execute(sql, params).fetchall()
    return [_decode_evidence_row(dict(r)) for r in rows]


def _evidence_filters(
    category: str | None,
    min_relevance: int | None,
    *,
    email_uid: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Build the fixed evidence predicates and their bound parameters."""
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
    return conditions, params


def _quote_failure(payload: dict[str, Any], quote: str, email_uid: str, *, orphaned: bool = False) -> dict[str, Any]:
    """Build the redacted public failure record for one unverified quote."""
    failure = {
        "evidence_id": payload["id"],
        "key_quote_preview": quote[:80] + ("..." if len(quote) > 80 else ""),
        "email_uid": email_uid,
    }
    if orphaned:
        failure["orphaned"] = True
    return failure


def evidence_categories(conn: sqlite3.Connection, suggested: list[str]) -> list[dict]:
    """Return suggested and user-defined categories with current evidence counts."""
    count_rows = conn.execute("SELECT category, COUNT(*) AS count FROM evidence_items GROUP BY category").fetchall()
    counts = {r["category"]: r["count"] for r in count_rows}
    categories = [*suggested]
    categories.extend(sorted(set(counts).difference(categories)))
    return [{"category": cat, "count": counts.get(cat, 0)} for cat in categories]
