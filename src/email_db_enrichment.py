"""Enrichment helpers for EmailDatabase write paths."""

from __future__ import annotations

import json
import re
import sqlite3

from .parse_olm import Email
from .thread_inference import infer_parent_candidate

_ADDR_RE = re.compile(r"^(.*?)\s*<([^>]+)>$")


def parse_address(raw: str) -> tuple[str, str]:
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
    rows: list[tuple[str, str, str, str]] = []
    seen_addresses: set[str] = set()

    if identities:
        for index, identity in enumerate(identities):
            normalized_identity = identity.strip().lower()
            if not normalized_identity or normalized_identity in seen_addresses:
                continue
            display_name = ""
            if index < len(addresses):
                visible = addresses[index]
                name, parsed_email = parse_address(visible)
                if name:
                    display_name = name
                elif parsed_email:
                    display_name = ""
                elif visible.strip() and "@" not in visible:
                    display_name = visible.strip()
            rows.append((email_uid, normalized_identity, display_name, recipient_type))
            seen_addresses.add(normalized_identity)

    for visible in addresses:
        name, parsed_email = parse_address(visible)
        if identities and not parsed_email and "@" not in visible:
            continue
        address = (parsed_email or visible).strip()
        normalized_address = address.lower() if "@" in address else address
        if not normalized_address or normalized_address in seen_addresses:
            continue
        rows.append((email_uid, normalized_address, name, recipient_type))
        seen_addresses.add(normalized_address)

    return rows


def segment_rows_for_email(email_uid: str, segments: list[object]) -> list[tuple[str, int, str, int, str, str, str]]:
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


def candidate_email_from_row(row: sqlite3.Row) -> Email:
    return Email(
        message_id=row["message_id"] or "",
        subject=row["subject"] or "",
        sender_name=row["sender_name"] or "",
        sender_email=row["sender_email"] or "",
        to=[],
        cc=[],
        bcc=[],
        to_identities=json.loads(row["to_identities_json"] or "[]"),
        cc_identities=json.loads(row["cc_identities_json"] or "[]"),
        bcc_identities=json.loads(row["bcc_identities_json"] or "[]"),
        date=row["date"] or "",
        body_text=row["body_text"] or "",
        body_html=row["body_html"] or "",
        folder=row["folder"] or "",
        has_attachments=bool(row["has_attachments"]),
        conversation_id=row["conversation_id"] or "",
        in_reply_to=row["in_reply_to"] or "",
        references=json.loads(row["references_json"] or "[]"),
        thread_topic=row["thread_topic"] or "",
    )


def persist_inferred_match(cur: sqlite3.Cursor, email_uid: str, match) -> None:
    cur.execute(
        """UPDATE emails
           SET inferred_parent_uid = ?, inferred_thread_id = ?,
               inferred_match_reason = ?, inferred_match_confidence = ?
         WHERE uid = ?""",
        (match.parent_uid, match.thread_id, match.reason, match.confidence, email_uid),
    )
    cur.execute(
        """INSERT INTO conversation_edges(child_uid, parent_uid, edge_type, reason, confidence)
           VALUES(?,?,?,?,?)""",
        (email_uid, match.parent_uid, "inferred", match.reason, match.confidence),
    )


def infer_and_persist_match(cur: sqlite3.Cursor, email: Email) -> tuple[str, str, str, float] | None:
    inferred_parent_uid = getattr(email, "inferred_parent_uid", "") or ""
    if inferred_parent_uid:
        return None
    candidates = [
        candidate_email_from_row(row)
        for row in cur.execute(
            """SELECT message_id, subject, sender_name, sender_email, date, body_text, body_html, folder,
                      has_attachments, conversation_id, in_reply_to, references_json, thread_topic,
                      to_identities_json, cc_identities_json, bcc_identities_json
               FROM emails WHERE uid != ?""",
            (email.uid,),
        ).fetchall()
    ]
    match = infer_parent_candidate(email, candidates)
    if match is None:
        return None
    persist_inferred_match(cur, email.uid, match)
    return (match.parent_uid, match.thread_id, match.reason, match.confidence)


def contact_row(email_address: str, display_name: str, date: str, role: str) -> tuple[str, str, str, str, int, int]:
    return (
        email_address,
        display_name,
        date,
        date,
        1 if role == "sender" else 0,
        1 if role == "recipient" else 0,
    )


def edge_row(sender: str, recipient: str, date: str) -> tuple[str, str, str, str]:
    return (sender, recipient, date, date)


def upsert_contact(cur: sqlite3.Cursor, email_address: str, display_name: str, date: str, role: str) -> None:
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
