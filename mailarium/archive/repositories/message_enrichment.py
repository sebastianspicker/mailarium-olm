"""Enrichment helpers for ArchiveDatabase write paths."""

from __future__ import annotations

import json
import re
import sqlite3

from mailarium.model import Message
from mailarium.model.thread_inference import InferredThreadMatch, infer_parent_candidate

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
    header_match = link_reply_headers(cur, email)
    if header_match is not None:
        return (header_match.parent_uid, header_match.thread_id, header_match.reason, header_match.confidence)
    inferred_parent_uid = getattr(email, "inferred_parent_uid", "") or ""
    if inferred_parent_uid:
        return None
    candidates = [candidate_email_from_row(row) for row in _candidate_parent_rows(cur, email)]
    match = infer_parent_candidate(email, candidates)
    if match is None:
        return None
    persist_inferred_match(cur, email.uid, match)
    _repoint_thread_members(cur, email.uid, match.thread_id)
    return (match.parent_uid, match.thread_id, match.reason, match.confidence)


_HEADER_LINK_COLUMNS = (
    "uid, message_id, conversation_id, thread_topic, in_reply_to, references_json, inferred_parent_uid, inferred_thread_id"
)


def link_reply_headers(cur: sqlite3.Cursor, email: Message) -> InferredThreadMatch | None:
    """Link a newly stored message into a thread through its In-Reply-To/References headers.

    Messages without an Exchange ``conversation_id`` are linked to the parent
    their headers name, and already-stored replies that name this message are
    linked to it. Returns the message's own parent match, if one was found.

    Args:
        cur: An active sqlite3.Cursor.
        email: The Message object that was just inserted.
    """
    row = cur.execute(f"SELECT {_HEADER_LINK_COLUMNS} FROM emails WHERE uid = ?", (email.uid,)).fetchone()  # nosec B608
    if row is None:
        return None
    match, _linked = _link_header_row(cur, row)
    return match


def backfill_header_threads(cur: sqlite3.Cursor) -> int:
    """Apply header-based thread linking to every stored message in date order.

    Already linked messages are left untouched, so repeated runs are idempotent.

    Args:
        cur: An active sqlite3.Cursor.

    Returns:
        The number of messages that received a new header-based parent link.
    """
    uids = [row[0] for row in cur.execute("SELECT uid FROM emails ORDER BY date ASC, uid ASC").fetchall()]
    linked = 0
    for uid in uids:
        row = cur.execute(f"SELECT {_HEADER_LINK_COLUMNS} FROM emails WHERE uid = ?", (uid,)).fetchone()  # nosec B608
        if row is not None:
            match, children = _link_header_row(cur, row)
            linked += children + (1 if match is not None else 0)
    return linked


def _link_header_row(cur: sqlite3.Cursor, row: sqlite3.Row) -> tuple[InferredThreadMatch | None, int]:
    """Link one stored message to its header parent and adopt its unlinked header children."""
    match = None
    if not _row_text(row, "conversation_id") and not _row_text(row, "inferred_parent_uid"):
        match = _link_to_header_parent(cur, row)
    thread_id = match.thread_id if match is not None else _row_thread_id(row)
    children = _link_header_children(cur, row, thread_id)
    if children and match is None:
        _claim_thread_root(cur, row, thread_id)
    return match, children


def _normalized_message_id(value: str) -> str:
    """Strip whitespace and angle brackets so stored Message-ID spellings compare equal."""
    return (value or "").strip().strip("<>").strip()


def _message_id_spellings(value: str) -> tuple[str, str]:
    """Return the bare and bracketed spellings under which a Message-ID may be stored."""
    bare = _normalized_message_id(value)
    return bare, f"<{bare}>"


def _row_thread_id(row: sqlite3.Row) -> str:
    """Choose a header thread id: the row's inferred thread, else its conversation, else its own uid.

    ``thread_topic`` is deliberately skipped: unrelated header threads often share a subject-like topic.
    """
    return _row_text(row, "inferred_thread_id") or _row_text(row, "conversation_id") or _row_text(row, "uid")


def _row_by_message_id(cur: sqlite3.Cursor, message_id: str, exclude_uid: str) -> sqlite3.Row | None:
    """Find one stored message by Message-ID, preferring a copy that already belongs to a thread."""
    bare, bracketed = _message_id_spellings(message_id)
    if not bare:
        return None
    return cur.execute(
        f"""SELECT {_HEADER_LINK_COLUMNS} FROM emails
             WHERE message_id IN (?, ?) AND uid != ?
             ORDER BY (COALESCE(inferred_thread_id, '') = ''), date ASC, uid ASC
             LIMIT 1""",  # nosec B608
        (bare, bracketed, exclude_uid),
    ).fetchone()


def _header_parent(cur: sqlite3.Cursor, row: sqlite3.Row) -> tuple[sqlite3.Row, str] | None:
    """Return the In-Reply-To target, else the last References entry present in the archive."""
    uid = _row_text(row, "uid")
    in_reply_to = _row_text(row, "in_reply_to")
    if in_reply_to:
        parent = _row_by_message_id(cur, in_reply_to, uid)
        if parent is not None:
            return parent, "in_reply_to"
    for reference in reversed(_row_json_list(row, "references_json")):
        parent = _row_by_message_id(cur, reference, uid)
        if parent is not None:
            return parent, "references"
    return None


def _link_to_header_parent(cur: sqlite3.Cursor, row: sqlite3.Row) -> InferredThreadMatch | None:
    """Persist the header parent link for one message and pull its thread members along."""
    found = _header_parent(cur, row)
    if found is None:
        return None
    parent, reason = found
    match = InferredThreadMatch(
        parent_uid=_row_text(parent, "uid"), thread_id=_row_thread_id(parent), reason=reason, confidence=1.0
    )
    _adopt_header_match(cur, _row_text(row, "uid"), match)
    _claim_thread_root(cur, parent, match.thread_id)
    return match


def _link_header_children(cur: sqlite3.Cursor, row: sqlite3.Row, thread_id: str) -> int:
    """Link stored, still unlinked replies whose In-Reply-To names this message."""
    uid = _row_text(row, "uid")
    bare, bracketed = _message_id_spellings(_row_text(row, "message_id"))
    if not bare:
        return 0
    children = cur.execute(
        """SELECT uid FROM emails
            WHERE in_reply_to IN (?, ?) AND uid != ?
              AND COALESCE(inferred_parent_uid, '') = '' AND COALESCE(conversation_id, '') = ''""",
        (bare, bracketed, uid),
    ).fetchall()
    for child in children:
        match = InferredThreadMatch(parent_uid=uid, thread_id=thread_id, reason="in_reply_to", confidence=1.0)
        _adopt_header_match(cur, str(child[0]), match)
    return len(children)


def _adopt_header_match(cur: sqlite3.Cursor, child_uid: str, match: InferredThreadMatch) -> None:
    """Persist a header link and move the child's own thread members into the parent thread."""
    persist_inferred_match(cur, child_uid, match)
    _repoint_thread_members(cur, child_uid, match.thread_id)


def _repoint_thread_members(cur: sqlite3.Cursor, old_thread_id: str, new_thread_id: str) -> None:
    """Move messages that used a now-linked message's uid as their thread id into its new thread."""
    if old_thread_id and old_thread_id != new_thread_id:
        cur.execute(
            "UPDATE emails SET inferred_thread_id = ? WHERE inferred_thread_id = ?",
            (new_thread_id, old_thread_id),
        )


def _claim_thread_root(cur: sqlite3.Cursor, row: sqlite3.Row, thread_id: str) -> None:
    """Give a thread root without an Exchange conversation its own thread id so it joins its thread."""
    if _row_text(row, "conversation_id"):
        return
    cur.execute(
        "UPDATE emails SET inferred_thread_id = ? WHERE uid = ? AND COALESCE(inferred_thread_id, '') = ''",
        (thread_id, _row_text(row, "uid")),
    )


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
