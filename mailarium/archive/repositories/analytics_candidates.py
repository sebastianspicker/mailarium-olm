"""Bounded candidate reads for language and sentiment maintenance."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

_MISSING_ANALYTICS = """
    detected_language IS NULL OR sentiment_label IS NULL
    OR detected_language_confidence IS NULL OR detected_language_reason IS NULL
    OR COALESCE(detected_language_source, '') = '' OR detected_language_token_count IS NULL
    OR NOT EXISTS (SELECT 1 FROM language_surface_analytics lsa WHERE lsa.email_uid = emails.uid)
"""
_SEGMENT_GROUPS = {
    "authored_segment": "segment_type = 'authored_body'",
    "quoted_segment": "segment_type IN ('quoted_reply', 'forwarded_message')",
    "forwarded_header": "segment_type = 'header_block'",
    "segment": "1",
}
_CANDIDATE_SELECT = (
    "SELECT uid, subject, forensic_body_text, forensic_body_source, body_text, normalized_body_source, raw_body_text "
    f"FROM emails WHERE ({_MISSING_ANALYTICS})"
)
_FIRST_PAGE = _CANDIDATE_SELECT + " ORDER BY uid LIMIT ?"
_NEXT_PAGE = _CANDIDATE_SELECT + " AND uid > ? ORDER BY uid LIMIT ?"
_SEGMENT_COLUMNS = ", ".join(
    column
    for prefix, condition in _SEGMENT_GROUPS.items()
    for column in (
        f"GROUP_CONCAT(CASE WHEN {condition} THEN text END, '\n') AS {prefix}_text",
        f"MIN(CASE WHEN {condition} THEN ordinal END) AS {prefix}_ordinal",
    )
)
_SEGMENT_SELECT = (
    f"SELECT email_uid, {_SEGMENT_COLUMNS} "
    "FROM (SELECT * FROM message_segments WHERE email_uid IN (SELECT value FROM json_each(?)) "
    "ORDER BY ordinal, id) GROUP BY email_uid"
)


def iter_analytics_candidate_batches(conn: sqlite3.Connection, *, batch_size: int = 256) -> Iterator[list[dict[str, Any]]]:
    """Read each candidate once, aggregating related surfaces once per bounded page."""
    if batch_size < 1 or batch_size > 256:
        raise ValueError("analytics batch size must be between 1 and 256")
    after: str | None = None
    while True:
        parameters = (after, batch_size) if after is not None else (batch_size,)
        rows = conn.execute(_NEXT_PAGE if after is not None else _FIRST_PAGE, parameters).fetchall()
        if not rows:
            return
        candidates = {str(row["uid"]): dict(row) for row in rows}
        _attach_surfaces(conn, candidates)
        after = str(rows[-1]["uid"])
        yield list(candidates.values())


def _attach_surfaces(conn: sqlite3.Connection, candidates: dict[str, dict[str, Any]]) -> None:
    parameters = (json.dumps(list(candidates)),)
    for row in conn.execute(
        "SELECT email_uid, GROUP_CONCAT(COALESCE(normalized_text, extracted_text, text_preview, name), '\n') "
        "AS attachment_text FROM (SELECT * FROM attachments WHERE email_uid IN (SELECT value FROM json_each(?)) ORDER BY id) "
        "GROUP BY email_uid",
        parameters,
    ):
        candidates[str(row["email_uid"])]["attachment_text"] = row["attachment_text"]
    for row in conn.execute(_SEGMENT_SELECT, parameters):
        candidates[str(row["email_uid"])].update(dict(row))
    for candidate in candidates.values():
        candidate.setdefault("attachment_text", None)
        for prefix in _SEGMENT_GROUPS:
            candidate.setdefault(f"{prefix}_text", None)
            candidate.setdefault(f"{prefix}_ordinal", None)
