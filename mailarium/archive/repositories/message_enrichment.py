"""Enrichment helpers for ArchiveDatabase write paths."""

from __future__ import annotations

import json
import re
import sqlite3

from mailarium.model import Message
from mailarium.model.thread_inference import infer_parent_candidate

_ADDR_RE = re.compile(r"^(.*?)\s*<([^>]+)>$")


def parse_address(raw: str) -> tuple[str, str]:
    """Parse a raw email address string into display name and email parts.

    Handles formats like "Name <email>" and bare email addresses.

    Args:
        raw: The raw address string to parse.

    Returns:
        A tuple of (display_name, email_address). Empty strings are used
        for missing parts.
    """
    raw = raw.strip()
    if not raw:
        return ("", "")
    match = _ADDR_RE.match(raw)
    if match:
        return (match.group(1).strip().strip('"'), match.group(2).strip())
    if "@" in raw:
        return ("", raw)
    return (raw, "")


def recipient_rows_for_type(
    email_uid: str,
    addresses: list[str],
    identities: list[str],
    recipient_type: str,
) -> list[tuple[str, str, str, str]]:
    """Build recipient rows for a given recipient type (to/cc/bcc).

    Produces deduplicated rows pairing email UIDs with recipient addresses,
    display names, and the recipient type.

    Args:
        email_uid: The email's unique identifier.
        addresses: List of visible address strings.
        identities: List of identity strings (e.g., from Exchange).
        recipient_type: One of "to", "cc", or "bcc".

    Returns:
        A list of (email_uid, address, display_name, recipient_type) tuples.
    """
    seen_addresses: set[str] = set()
    rows = _identity_recipient_rows(email_uid, addresses, identities, recipient_type, seen_addresses)
    rows.extend(_visible_recipient_rows(email_uid, addresses, identities, recipient_type, seen_addresses))
    return rows


def _identity_recipient_rows(
    email_uid: str,
    addresses: list[str],
    identities: list[str],
    recipient_type: str,
    seen: set[str],
) -> list[tuple[str, str, str, str]]:
    """Create normalized recipient rows from identity fields on an email record."""
    rows: list[tuple[str, str, str, str]] = []
    for index, identity in enumerate(identities):
        normalized_identity = identity.strip().lower()
        if not normalized_identity or normalized_identity in seen:
            continue
        display_name = _visible_display_name(addresses[index]) if index < len(addresses) else ""
        rows.append((email_uid, normalized_identity, display_name, recipient_type))
        seen.add(normalized_identity)
    return rows


def _visible_display_name(visible: str) -> str:
    """Prefer a human display name while rejecting address-shaped placeholders."""
    name, parsed_email = parse_address(visible)
    if name:
        return name
    if parsed_email or "@" in visible:
        return ""
    return visible.strip()


def _visible_recipient_rows(
    email_uid: str,
    addresses: list[str],
    identities: list[str],
    recipient_type: str,
    seen: set[str],
) -> list[tuple[str, str, str, str]]:
    """Merge stored recipient rows with visible fallback identity fields."""
    rows: list[tuple[str, str, str, str]] = []
    for visible in addresses:
        name, parsed_email = parse_address(visible)
        if identities and not parsed_email and "@" not in visible:
            continue
        address = (parsed_email or visible).strip()
        normalized_address = address.lower() if "@" in address else address
        if not normalized_address or normalized_address in seen:
            continue
        rows.append((email_uid, normalized_address, name, recipient_type))
        seen.add(normalized_address)
    return rows


def segment_rows_for_email(email_uid: str, segments: list[object]) -> list[tuple[str, int, str, int, str, str, str]]:
    """Build segment rows for database insertion.

    Converts a list of message segment objects into tuples suitable for
    bulk insert into the message_segments table.

    Args:
        email_uid: The email's unique identifier.
        segments: List of segment objects with ordinal, segment_type,
            depth, text, source_surface, and provenance attributes.

    Returns:
        A list of (email_uid, ordinal, segment_type, depth, text,
        source_surface, provenance_json) tuples.
    """
    rows: list[tuple[str, int, str, int, str, str, str]] = []
    for index, segment in enumerate(segments):
        rows.append(
            (
                email_uid,
                int(getattr(segment, "ordinal", index)),
                getattr(segment, "segment_type", ""),
                int(getattr(segment, "depth", 0)),
                getattr(segment, "text", ""),
                getattr(segment, "source_surface", "body_text"),
                json.dumps(getattr(segment, "provenance", {}) or {}),
            )
        )
    return rows


def candidate_email_from_row(row: sqlite3.Row) -> Message:
    """Reconstruct an Message object from a database row.

    Args:
        row: A sqlite3.Row from the emails table.

    Returns:
        An Message object populated from the row's columns.
    """
    return Message(
        message_id=_row_text(row, "message_id"),
        subject=_row_text(row, "subject"),
        sender_name=_row_text(row, "sender_name"),
        sender_email=_row_text(row, "sender_email"),
        to=[],
        cc=[],
        bcc=[],
        to_identities=_row_json_list(row, "to_identities_json"),
        cc_identities=_row_json_list(row, "cc_identities_json"),
        bcc_identities=_row_json_list(row, "bcc_identities_json"),
        date=_row_text(row, "date"),
        body_text=_row_text(row, "body_text"),
        body_html=_row_text(row, "body_html"),
        folder=_row_text(row, "folder"),
        has_attachments=bool(row["has_attachments"]),
        conversation_id=_row_text(row, "conversation_id"),
        in_reply_to=_row_text(row, "in_reply_to"),
        references=_row_json_list(row, "references_json"),
        thread_topic=_row_text(row, "thread_topic"),
    )


def _row_text(row: sqlite3.Row, key: str) -> str:
    """Return a stripped textual column value from a database row."""
    return str(row[key] or "")


def _row_json_list(row: sqlite3.Row, key: str) -> list[str]:
    """Decode a JSON-list column while tolerating missing or malformed data."""
    value = json.loads(row[key] or "[]")
    return [str(item) for item in value] if isinstance(value, list) else []


def persist_inferred_match(cur: sqlite3.Cursor, email_uid: str, match) -> None:
    """Persist an inferred thread match to the database.

    Updates the emails table with inferred parent UID, thread ID, reason,
    and confidence, and inserts a conversation edge.

    Args:
        cur: An active sqlite3.Cursor.
        email_uid: The child email UID.
        match: A match object with parent_uid, thread_id, reason, and
            confidence attributes.
    """
    cur.execute(
        """UPDATE emails
           SET inferred_parent_uid = ?, inferred_thread_id = ?,
               inferred_match_reason = ?, inferred_match_confidence = ?
         WHERE uid = ?""",
        (match.parent_uid, match.thread_id, match.reason, match.confidence, email_uid),
    )
    cur.execute(
        """INSERT INTO conversation_edges(child_uid, parent_uid, edge_type, reason, confidence)
           VALUES(?,?,?,?,?)
           ON CONFLICT(child_uid, parent_uid, edge_type) DO UPDATE SET
               reason = excluded.reason,
               confidence = MAX(conversation_edges.confidence, excluded.confidence)""",
        (email_uid, match.parent_uid, "inferred", match.reason, match.confidence),
    )


def _candidate_parent_rows(cur: sqlite3.Cursor, email: Message) -> list[sqlite3.Row]:
    """Find likely parent messages using conversation and reply identifiers."""
    manageres = ["uid != ?"]
    params: list[object] = [email.uid]

    conversation_id = getattr(email, "conversation_id", "") or ""
    in_reply_to = getattr(email, "in_reply_to", "") or ""
    base_subject = getattr(email, "base_subject", "") or ""
    parent_filters: list[str] = []
    if conversation_id:
        parent_filters.append("conversation_id = ?")
        params.append(conversation_id)
    if in_reply_to:
        parent_filters.append("message_id = ?")
        params.append(in_reply_to)
    if base_subject:
        parent_filters.append("base_subject = ?")
        params.append(base_subject)
    if parent_filters:
        manageres.append(f"({' OR '.join(parent_filters)})")

    email_date = getattr(email, "date", "") or ""
    if email_date:
        manageres.append("(date = '' OR date < ?)")
        params.append(email_date)

    query = f"""SELECT uid, message_id, subject, sender_name, sender_email, date, body_text, body_html, folder,
                       has_attachments, conversation_id, in_reply_to, references_json, thread_topic,
                       to_identities_json, cc_identities_json, bcc_identities_json
                FROM emails
                WHERE {" AND ".join(manageres)}
                ORDER BY date DESC
                LIMIT 200"""
    return cur.execute(query, params).fetchall()


def infer_and_persist_match(cur: sqlite3.Cursor, email: Message) -> tuple[str, str, str, float] | None:
    """Infer the parent email for an email and persist the match.

    Queries candidate parent rows from the database, runs thread inference,
    and persists the best match if found.

    Args:
        cur: An active sqlite3.Cursor.
        email: The Message object to find a parent for.

    Returns:
        A tuple of (parent_uid, thread_id, reason, confidence) if a match
        was found and persisted, or None if no match or already inferred.
    """
    inferred_parent_uid = getattr(email, "inferred_parent_uid", "") or ""
    if inferred_parent_uid:
        return None
    candidates = [candidate_email_from_row(row) for row in _candidate_parent_rows(cur, email)]
    match = infer_parent_candidate(email, candidates)
    if match is None:
        return None
    persist_inferred_match(cur, email.uid, match)
    return (match.parent_uid, match.thread_id, match.reason, match.confidence)


def contact_row(email_address: str, display_name: str, date: str, role: str) -> tuple[str, str, str, str, int, int]:
    """Build a contact row tuple for upsert.

    Args:
        email_address: The contact's email address.
        display_name: The contact's display name.
        date: The date string for first/last seen.
        role: "sender" or "recipient".

    Returns:
        A tuple of (email_address, display_name, first_seen, last_seen,
        sent_count, received_count).
    """
    return (
        email_address,
        display_name,
        date,
        date,
        1 if role == "sender" else 0,
        1 if role == "recipient" else 0,
    )


def edge_row(sender: str, recipient: str, date: str) -> tuple[str, str, str, str]:
    """Build a communication edge row tuple.

    Args:
        sender: The sender's email address.
        recipient: The recipient's email address.
        date: The date string for first/last contact.

    Returns:
        A tuple of (sender, recipient, first_date, last_date).
    """
    return (sender, recipient, date, date)


def upsert_contact(cur: sqlite3.Cursor, email_address: str, display_name: str, date: str, role: str) -> None:
    """Upsert a single contact row into the contacts table.

    Inserts or updates a contact with the given email, name, date, and role.

    Args:
        cur: An active sqlite3.Cursor.
        email_address: The contact's email address.
        display_name: The contact's display name.
        date: The date string.
        role: "sender" or "recipient".
    """
    cur.execute(
        """INSERT INTO contacts(email_address, display_name, first_seen, last_seen,
           sent_count, received_count)
           VALUES(?, ?, ?, ?, ?, ?)
           ON CONFLICT(email_address) DO UPDATE SET
             display_name = COALESCE(NULLIF(excluded.display_name, ''), contacts.display_name),
             first_seen = CASE
               WHEN excluded.first_seen IS NULL OR excluded.first_seen = '' THEN contacts.first_seen
               WHEN contacts.first_seen IS NULL OR contacts.first_seen = '' THEN excluded.first_seen
               ELSE MIN(contacts.first_seen, excluded.first_seen)
             END,
             last_seen = CASE
               WHEN excluded.last_seen IS NULL OR excluded.last_seen = '' THEN contacts.last_seen
               WHEN contacts.last_seen IS NULL OR contacts.last_seen = '' THEN excluded.last_seen
               ELSE MAX(contacts.last_seen, excluded.last_seen)
             END,
             sent_count = contacts.sent_count + excluded.sent_count,
             received_count = contacts.received_count + excluded.received_count
        """,
        contact_row(email_address, display_name, date, role),
    )


def upsert_communication_edge(cur: sqlite3.Cursor, sender: str, recipient: str, date: str) -> None:
    """Upsert a single communication edge into the communication_edges table.

    Inserts or updates an edge between sender and recipient with date info.

    Args:
        cur: An active sqlite3.Cursor.
        sender: The sender's email address.
        recipient: The recipient's email address.
        date: The date string.
    """
    cur.execute(
        """INSERT INTO communication_edges(sender_email, recipient_email,
           email_count, first_date, last_date)
           VALUES(?, ?, 1, ?, ?)
           ON CONFLICT(sender_email, recipient_email) DO UPDATE SET
             email_count = communication_edges.email_count + 1,
             first_date = CASE
               WHEN excluded.first_date IS NULL OR excluded.first_date = '' THEN communication_edges.first_date
               WHEN communication_edges.first_date IS NULL OR communication_edges.first_date = '' THEN excluded.first_date
               ELSE MIN(communication_edges.first_date, excluded.first_date)
             END,
             last_date = CASE
               WHEN excluded.last_date IS NULL OR excluded.last_date = '' THEN communication_edges.last_date
               WHEN communication_edges.last_date IS NULL OR communication_edges.last_date = '' THEN excluded.last_date
               ELSE MAX(communication_edges.last_date, excluded.last_date)
             END
        """,
        edge_row(sender, recipient, date),
    )


def execute_contact_upserts(cur: sqlite3.Cursor, rows: list[tuple[str, str, str, str, int, int]]) -> None:
    """Bulk-upsert contact rows into the contacts table.

    Args:
        cur: An active sqlite3.Cursor.
        rows: List of contact row tuples as produced by contact_row().
    """
    if not rows:
        return
    cur.executemany(
        """INSERT INTO contacts(email_address, display_name, first_seen, last_seen,
           sent_count, received_count)
           VALUES(?, ?, ?, ?, ?, ?)
           ON CONFLICT(email_address) DO UPDATE SET
             display_name = COALESCE(NULLIF(excluded.display_name, ''), contacts.display_name),
             first_seen = CASE
               WHEN excluded.first_seen IS NULL OR excluded.first_seen = '' THEN contacts.first_seen
               WHEN contacts.first_seen IS NULL OR contacts.first_seen = '' THEN excluded.first_seen
               ELSE MIN(contacts.first_seen, excluded.first_seen)
             END,
             last_seen = CASE
               WHEN excluded.last_seen IS NULL OR excluded.last_seen = '' THEN contacts.last_seen
               WHEN contacts.last_seen IS NULL OR contacts.last_seen = '' THEN excluded.last_seen
               ELSE MAX(contacts.last_seen, excluded.last_seen)
             END,
             sent_count = contacts.sent_count + excluded.sent_count,
             received_count = contacts.received_count + excluded.received_count
        """,
        rows,
    )


def execute_edge_upserts(cur: sqlite3.Cursor, rows: list[tuple[str, str, str, str]]) -> None:
    """Bulk-upsert communication edge rows into the communication_edges table.

    Args:
        cur: An active sqlite3.Cursor.
        rows: List of edge row tuples as produced by edge_row().
    """
    if not rows:
        return
    cur.executemany(
        """INSERT INTO communication_edges(sender_email, recipient_email,
           email_count, first_date, last_date)
           VALUES(?, ?, 1, ?, ?)
           ON CONFLICT(sender_email, recipient_email) DO UPDATE SET
             email_count = communication_edges.email_count + 1,
             first_date = CASE
               WHEN excluded.first_date IS NULL OR excluded.first_date = ''
                 THEN communication_edges.first_date
               WHEN communication_edges.first_date IS NULL
                 OR communication_edges.first_date = ''
                 THEN excluded.first_date
               ELSE MIN(communication_edges.first_date, excluded.first_date)
             END,
             last_date = CASE
               WHEN excluded.last_date IS NULL OR excluded.last_date = ''
                 THEN communication_edges.last_date
               WHEN communication_edges.last_date IS NULL
                 OR communication_edges.last_date = ''
                 THEN excluded.last_date
               ELSE MAX(communication_edges.last_date, excluded.last_date)
             END
        """,
        rows,
    )
