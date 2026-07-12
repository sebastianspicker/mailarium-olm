"""Browse and full-retrieval helpers for ``QueryMixin``."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db_schema import _escape_like, _sql_in_placeholders, _validate_order_by


def safe_json_parse(raw: str | None, default: list | dict | None = None) -> list | dict:
    """Parse a JSON string, returning default (or []) on failure."""
    if not raw or not isinstance(raw, str):
        return default if default is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def format_recipient(name: str | None, addr: str) -> str:
    """Format a recipient as 'Name <addr>' or bare addr."""
    return f"{name} <{addr}>" if name else addr


def hydrate_emails_with_related(
    rows: list[sqlite3.Row],
    *,
    all_recipients: dict[str, dict[str, list[str]]],
    attachments_by_uid: dict[str, list[dict]],
) -> list[dict]:
    """Hydrate email rows with recipients, parsed JSON fields, and attachments."""
    result = []
    for row in rows:
        email = dict(row)
        uid = email["uid"]
        recips = all_recipients.get(uid, {"to": [], "cc": [], "bcc": []})
        email["to"] = recips["to"]
        email["cc"] = recips["cc"]
        email["bcc"] = recips["bcc"]
        email["categories"] = safe_json_parse(email.pop("categories", None))
        email["references"] = safe_json_parse(email.pop("references_json", None))
        email["meeting_data"] = safe_json_parse(email.pop("meeting_data_json", None), default={})
        email["exchange_extracted_links"] = safe_json_parse(email.pop("exchange_extracted_links_json", None))
        email["exchange_extracted_emails"] = safe_json_parse(email.pop("exchange_extracted_emails_json", None))
        email["exchange_extracted_contacts"] = safe_json_parse(email.pop("exchange_extracted_contacts_json", None))
        email["exchange_extracted_meetings"] = safe_json_parse(email.pop("exchange_extracted_meetings_json", None))
        email["attachments"] = attachments_by_uid.get(uid, [])
        result.append(email)
    return result


def attachments_for_uids(conn: sqlite3.Connection, uids: list[str], *, batch_size: int = 900) -> dict[str, list[dict]]:
    """Return attachments keyed by email UID for the given UID list."""
    attachments_by_uid: dict[str, list[dict]] = {}
    if not uids:
        return attachments_by_uid
    for start in range(0, len(uids), batch_size):
        batch = uids[start : start + batch_size]
        placeholders = _sql_in_placeholders(batch)
        att_rows = conn.execute(
            "SELECT name, mime_type, size, content_id, is_inline, email_uid"
            f" FROM attachments WHERE email_uid IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        for attachment in att_rows:
            attachments_by_uid.setdefault(attachment["email_uid"], []).append(
                {
                    "name": attachment["name"],
                    "mime_type": attachment["mime_type"],
                    "size": attachment["size"],
                    "content_id": attachment["content_id"],
                    "is_inline": attachment["is_inline"],
                }
            )
    return attachments_by_uid


def recipients_for_uid_impl(db: Any, uid: str) -> dict[str, list[str]]:
    """Return {to: [...], cc: [...], bcc: [...]} for a single email."""
    rows = db.conn.execute(
        "SELECT address, display_name, type FROM recipients WHERE email_uid = ?",
        (uid,),
    ).fetchall()
    result: dict[str, list[str]] = {"to": [], "cc": [], "bcc": []}
    for row in rows:
        if row["type"] in result:
            result[row["type"]].append(format_recipient(row["display_name"], row["address"]))
    return result


def recipients_for_uids_impl(db: Any, uids: list[str]) -> dict[str, dict[str, list[str]]]:
    """Return {uid: {to: [...], cc: [...], bcc: [...]}} for multiple emails in one query."""
    if not uids:
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    batch_size = 900
    for start in range(0, len(uids), batch_size):
        batch = uids[start : start + batch_size]
        placeholders = _sql_in_placeholders(batch)
        rows = db.conn.execute(
            f"SELECT address, display_name, type, email_uid FROM recipients WHERE email_uid IN ({placeholders})",  # nosec B608
            batch,
        ).fetchall()
        for row in rows:
            uid = row["email_uid"]
            if uid not in result:
                result[uid] = {"to": [], "cc": [], "bcc": []}
            if row["type"] in result[uid]:
                result[uid][row["type"]].append(format_recipient(row["display_name"], row["address"]))
    return result


def get_email_full_impl(db: Any, uid: str) -> dict | None:
    """Get a single email with full body text by UID."""
    row = db.conn.execute("SELECT * FROM emails WHERE uid = ?", (uid,)).fetchone()
    if not row:
        return None
    email = dict(row)
    recipients = db._recipients_for_uid(uid)
    email["to"] = recipients["to"]
    email["cc"] = recipients["cc"]
    email["bcc"] = recipients["bcc"]
    email["categories"] = safe_json_parse(email.pop("categories", None))
    email["references"] = safe_json_parse(email.pop("references_json", None))
    email["meeting_data"] = safe_json_parse(email.pop("meeting_data_json", None), default={})
    email["exchange_extracted_links"] = safe_json_parse(email.pop("exchange_extracted_links_json", None))
    email["exchange_extracted_emails"] = safe_json_parse(email.pop("exchange_extracted_emails_json", None))
    email["exchange_extracted_contacts"] = safe_json_parse(email.pop("exchange_extracted_contacts_json", None))
    email["exchange_extracted_meetings"] = safe_json_parse(email.pop("exchange_extracted_meetings_json", None))
    email["attachments"] = db.attachments_for_email(uid)
    return email


def get_emails_full_batch_impl(db: Any, uids: list[str]) -> dict[str, dict]:
    """Get multiple emails with full body, recipients, and attachments."""
    if not uids:
        return {}

    rows: list[sqlite3.Row] = []
    batch_size = 900
    for start in range(0, len(uids), batch_size):
        batch = uids[start : start + batch_size]
        placeholders = _sql_in_placeholders(batch)
        rows.extend(
            db.conn.execute(
                f"SELECT * FROM emails WHERE uid IN ({placeholders})",  # nosec B608
                batch,
            ).fetchall()
        )

    all_recipients = db._recipients_for_uids(uids)
    attachments_by_uid = attachments_for_uids(db.conn, uids, batch_size=batch_size)

    result: dict[str, dict] = {}
    for email in hydrate_emails_with_related(
        rows,
        all_recipients=all_recipients,
        attachments_by_uid=attachments_by_uid,
    ):
        result[email["uid"]] = email
    return result


def get_thread_emails_impl(db: Any, conversation_id: str) -> list[dict]:
    """Get all emails in a canonical conversation thread, sorted by date ASC."""
    if not conversation_id:
        return []
    rows = db.conn.execute(
        "SELECT * FROM emails WHERE conversation_id = ? ORDER BY date ASC",
        (conversation_id,),
    ).fetchall()
    uids = [row["uid"] for row in rows]
    all_recipients = db._recipients_for_uids(uids) if uids else {}
    attachments_by_uid = attachments_for_uids(db.conn, uids)
    return hydrate_emails_with_related(
        rows,
        all_recipients=all_recipients,
        attachments_by_uid=attachments_by_uid,
    )


def get_inferred_thread_emails_impl(db: Any, inferred_thread_id: str) -> list[dict]:
    """Get all emails linked by inferred thread id, sorted by date ASC."""
    if not inferred_thread_id:
        return []
    rows = db.conn.execute(
        "SELECT * FROM emails WHERE inferred_thread_id = ? ORDER BY date ASC",
        (inferred_thread_id,),
    ).fetchall()
    uids = [row["uid"] for row in rows]
    all_recipients = db._recipients_for_uids(uids) if uids else {}
    attachments_by_uid = attachments_for_uids(db.conn, uids)
    return hydrate_emails_with_related(
        rows,
        all_recipients=all_recipients,
        attachments_by_uid=attachments_by_uid,
    )


def _browse_filter_params(
    *,
    category: str | None,
    folder: str | None,
    sender: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[Any]:
    sender_like = f"%{_escape_like(sender)}%" if sender else None
    start_date = date_from[:10] if date_from else None
    end_date = date_to[:10] if date_to else None
    return [
        category,
        category,
        folder,
        folder,
        sender_like,
        sender_like,
        start_date,
        start_date,
        end_date,
        end_date,
    ]


BROWSE_FROM_WHERE_SQL = (
    " FROM emails"
    " LEFT JOIN email_categories ec ON emails.uid = ec.email_uid"
    " WHERE (? IS NULL OR ec.category = ?)"
    " AND (? IS NULL OR folder = ?)"
    " AND (? IS NULL OR sender_email LIKE ? ESCAPE '\\')"
    " AND (? IS NULL OR SUBSTR(date, 1, 10) >= ?)"
    " AND (? IS NULL OR SUBSTR(date, 1, 10) <= ?)"
)
BROWSE_COUNT_SQL = "SELECT COUNT(DISTINCT emails.uid) AS c" + BROWSE_FROM_WHERE_SQL
BROWSE_SELECT_BASE_SQL = (
    "SELECT DISTINCT emails.uid, subject, sender_name, sender_email, date, folder,"
    " email_type, has_attachments, attachment_count, body_length,"
    " conversation_id" + BROWSE_FROM_WHERE_SQL
)


def list_emails_paginated_impl(
    db: Any,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "date",
    sort_order: str = "DESC",
    folder: str | None = None,
    sender: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Return a page of emails with metadata for browsing."""
    allowed_sort = {"date", "subject", "sender_email", "folder"}
    try:
        sort_by, sort_order = _validate_order_by(sort_by, sort_order, allowed_columns=allowed_sort)
    except ValueError:
        sort_by, sort_order = "date", "DESC"
    offset = max(offset, 0)
    limit = max(limit, 1)

    params = _browse_filter_params(
        category=category,
        folder=folder,
        sender=sender,
        date_from=date_from,
        date_to=date_to,
    )
    # Safe: static query with bound filter parameters.
    total_row = db.conn.execute(  # nosemgrep
        BROWSE_COUNT_SQL,
        params,
    ).fetchone()
    total = total_row["c"]

    # Safe: validated sort column/direction, static filters, bound params.
    rows = db.conn.execute(  # nosemgrep
        f"{BROWSE_SELECT_BASE_SQL} ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?",  # nosec B608
        [*params, limit, offset],
    ).fetchall()

    return {
        "emails": [dict(row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def get_email_for_reembed_impl(db: Any, uid: str) -> dict | None:
    """Read an email from SQLite in the dict format expected by chunk_email()."""
    full = db.get_email_full(uid)
    if not full:
        return None
    body = full.get("body_text") or ""
    if not body.strip():
        return None
    return _reembed_email_payload(full, body)


def _full_value(full: dict, key: str, default: Any) -> Any:
    return full.get(key) or default


def _reembed_email_payload(full: dict, body: str) -> dict:
    attachments = _full_value(full, "attachments", [])
    categories = full.get("categories")
    return {
        "uid": full["uid"],
        "message_id": _full_value(full, "message_id", ""),
        "subject": _full_value(full, "subject", ""),
        "sender_name": _full_value(full, "sender_name", ""),
        "sender_email": _full_value(full, "sender_email", ""),
        "to": _full_value(full, "to", []),
        "cc": _full_value(full, "cc", []),
        "bcc": _full_value(full, "bcc", []),
        "date": _full_value(full, "date", ""),
        "body": body,
        "folder": _full_value(full, "folder", ""),
        "has_attachments": any((full.get("has_attachments"), full.get("attachment_count"))),
        "attachment_names": [a["name"] for a in attachments if a.get("name")],
        "attachments": attachments,
        "attachment_count": _full_value(full, "attachment_count", 0),
        "conversation_id": _full_value(full, "conversation_id", ""),
        "in_reply_to": _full_value(full, "in_reply_to", ""),
        "references": _full_value(full, "references", []),
        "priority": _full_value(full, "priority", 0),
        "is_read": bool(full.get("is_read", True)),
        "email_type": _full_value(full, "email_type", "original"),
        "base_subject": _full_value(full, "base_subject", ""),
        "categories": categories if isinstance(categories, list) else [],
        "thread_topic": _full_value(full, "thread_topic", ""),
        "inference_classification": _full_value(full, "inference_classification", ""),
        "is_calendar_message": bool(full.get("is_calendar_message")),
    }
