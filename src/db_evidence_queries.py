"""Read/query helpers for evidence management."""

from __future__ import annotations

import re
from typing import Any

from .db_schema import _escape_like

_WS_RE = re.compile(r"[\s\xa0]+")


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace (including nbsp) to single spaces and lowercase."""
    return _WS_RE.sub(" ", text.strip()).lower()


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
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec B608
        params,
    ).fetchone()
    total = total_row["c"]

    rows = db.conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ? OFFSET ?",  # nosec B608
        [*params, limit, offset],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
    }


def get_evidence_impl(db: Any, evidence_id: int) -> dict | None:
    """Get a single evidence item by ID."""
    row = db.conn.execute(
        "SELECT * FROM evidence_items WHERE id = ?",
        (evidence_id,),
    ).fetchone()
    return dict(row) if row else None


def verify_evidence_quotes_impl(db: Any) -> dict:
    """Verify all evidence quotes against actual email body text."""
    rows = db.conn.execute(
        """SELECT ei.id, ei.key_quote, ei.email_uid, e.body_text
           FROM evidence_items ei
           LEFT JOIN emails e ON ei.email_uid = e.uid"""
    ).fetchall()

    verified_count = 0
    failed_count = 0
    orphaned_count = 0
    failures: list[dict] = []
    verified_ids: list[tuple[int]] = []
    failed_ids: list[tuple[int]] = []

    for row in rows:
        body_text = row["body_text"]
        quote = (row["key_quote"] or "").strip()

        if body_text is None:
            orphaned_count += 1
            failed_ids.append((row["id"],))
            failures.append(
                {
                    "evidence_id": row["id"],
                    "key_quote_preview": quote[:80] + ("..." if len(quote) > 80 else ""),
                    "email_uid": row["email_uid"],
                    "orphaned": True,
                }
            )
            continue

        is_verified = 1 if quote and _normalize_ws(quote) in _normalize_ws(body_text) else 0

        if is_verified:
            verified_count += 1
            verified_ids.append((row["id"],))
        else:
            failed_count += 1
            failed_ids.append((row["id"],))
            failures.append(
                {
                    "evidence_id": row["id"],
                    "key_quote_preview": quote[:80] + ("..." if len(quote) > 80 else ""),
                    "email_uid": row["email_uid"],
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
        "orphaned": orphaned_count,
        "total": verified_count + failed_count + orphaned_count,
        "failures": failures,
    }


def evidence_stats_impl(
    db: Any,
    *,
    category: str | None = None,
    min_relevance: int | None = None,
) -> dict:
    """Return evidence collection statistics, optionally filtered."""
    where_clauses: list[str] = []
    params: list[Any] = []
    if category:
        where_clauses.append("category = ?")
        params.append(category)
    if min_relevance is not None:
        where_clauses.append("relevance >= ?")
        params.append(min_relevance)
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql}",  # nosec B608
        params,
    ).fetchone()
    total = total_row["c"]

    verified_row = db.conn.execute(
        f"SELECT COUNT(*) AS c FROM evidence_items{where_sql} {'AND' if where_clauses else 'WHERE'} verified = 1",  # nosec B608
        params,
    ).fetchone()
    verified = verified_row["c"]

    cat_rows = db.conn.execute(
        f"SELECT category, COUNT(*) AS count FROM evidence_items{where_sql} GROUP BY category ORDER BY count DESC",  # nosec B608
        params,
    ).fetchall()

    rel_rows = db.conn.execute(
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
        f"SELECT COUNT(*) AS c FROM evidence_items{where}",  # nosec B608
        params,
    ).fetchone()

    rows = db.conn.execute(
        f"SELECT * FROM evidence_items{where} ORDER BY date ASC LIMIT ?",  # nosec B608
        [*params, limit],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
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

    sql = f"SELECT * FROM evidence_items{where} ORDER BY date ASC"  # nosec B608
    if limit is not None and limit >= 0:
        sql += " LIMIT ?"
        params.append(limit)
    elif offset > 0:
        sql += " LIMIT -1"
    if offset > 0:
        sql += " OFFSET ?"
        params.append(offset)

    rows = db.conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def evidence_categories_impl(db: Any) -> list[dict]:
    """Return all canonical categories with current evidence counts."""
    count_rows = db.conn.execute("SELECT category, COUNT(*) AS count FROM evidence_items GROUP BY category").fetchall()
    counts = {r["category"]: r["count"] for r in count_rows}
    return [{"category": cat, "count": counts.get(cat, 0)} for cat in db.EVIDENCE_CATEGORIES]
