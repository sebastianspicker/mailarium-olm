"""Attachment query mixin for EmailDatabase."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from .attachment_record_semantics import enrich_attachment_record
from .attachment_surfaces import build_attachment_surfaces
from .db_schema import _escape_like


def _attachment_filter_conditions(
    filename: str | None,
    extension: str | None,
    mime_type: str | None,
) -> tuple[list[str], list]:
    """Build WHERE conditions and params for attachment filename/extension/mime filters."""
    conditions: list[str] = []
    params: list = []
    if filename:
        conditions.append("a.name LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(filename)}%")
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        conditions.append("LOWER(a.name) LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(ext.lower())}")
    if mime_type:
        conditions.append("a.mime_type LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(mime_type)}%")
    return conditions, params


class AttachmentMixin:
    """Attachment queries: per-email, stats, browse, and search."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

    def attachments_for_email(self, uid: str) -> list[dict]:
        """Get all attachments for a specific email."""
        rows = self.conn.execute(
            "SELECT name, attachment_id, mime_type, size, content_sha256, content_id, is_inline, extraction_state, "
            "evidence_strength, ocr_used, ocr_engine, ocr_lang, ocr_confidence, failure_reason, text_preview, "
            "extracted_text, normalized_text, text_normalization_version, locator_version, text_source_path, "
            "text_locator_json "
            "FROM attachments WHERE email_uid = ?",
            (uid,),
        ).fetchall()
        surface_rows = self.conn.execute(
            "SELECT attachment_id, attachment_name, surface_id, surface_kind, origin_kind, text, normalized_text, "
            "alignment_map_json, language, language_confidence, ocr_confidence, surface_hash, locator_json, quality_json "
            "FROM attachment_surfaces WHERE email_uid = ?",
            (uid,),
        ).fetchall()
        surfaces_by_attachment_id: dict[str, list[dict[str, object]]] = {}
        for row in surface_rows:
            attachment_id = str(row["attachment_id"] or "")
            alignment_map_json = str(row["alignment_map_json"] or "").strip()
            locator_json = str(row["locator_json"] or "").strip()
            quality_json = str(row["quality_json"] or "").strip()
            try:
                alignment_map = json.loads(alignment_map_json) if alignment_map_json else {}
            except json.JSONDecodeError:
                alignment_map = {}
            try:
                locator = json.loads(locator_json) if locator_json else {}
            except json.JSONDecodeError:
                locator = {}
            try:
                quality = json.loads(quality_json) if quality_json else {}
            except json.JSONDecodeError:
                quality = {}
            surfaces_by_attachment_id.setdefault(attachment_id, []).append(
                {
                    "surface_id": str(row["surface_id"] or ""),
                    "surface_kind": str(row["surface_kind"] or ""),
                    "origin_kind": str(row["origin_kind"] or ""),
                    "text": str(row["text"] or ""),
                    "normalized_text": str(row["normalized_text"] or ""),
                    "alignment_map": alignment_map,
                    "language": str(row["language"] or "unknown") or "unknown",
                    "language_confidence": str(row["language_confidence"] or ""),
                    "ocr_confidence": float(row["ocr_confidence"] or 0.0),
                    "surface_hash": str(row["surface_hash"] or ""),
                    "locator": locator,
                    "quality": quality,
                }
            )
        attachments: list[dict] = []
        for row in rows:
            attachment = dict(row)
            raw_locator = str(attachment.get("text_locator_json") or "").strip()
            try:
                attachment["text_locator"] = json.loads(raw_locator) if raw_locator else {}
            except json.JSONDecodeError:
                attachment["text_locator"] = {}
            attachment_id = str(attachment.get("attachment_id") or "")
            attachment["surfaces"] = build_attachment_surfaces(
                attachment_id=attachment_id,
                extracted_text=str(attachment.get("extracted_text") or ""),
                normalized_text=str(attachment.get("normalized_text") or ""),
                text_locator=attachment.get("text_locator") or {},
                extraction_state=str(attachment.get("extraction_state") or ""),
                evidence_strength=str(attachment.get("evidence_strength") or ""),
                ocr_used=bool(attachment.get("ocr_used")),
                ocr_confidence=float(attachment.get("ocr_confidence") or 0.0),
                surfaces=surfaces_by_attachment_id.get(attachment_id),
            )
            attachments.append(enrich_attachment_record(attachment))
        return attachments

    def attachment_stats(self) -> dict:
        """Aggregate attachment statistics: counts, sizes, type distribution."""
        row = self.conn.execute("SELECT COUNT(*) AS total, COALESCE(SUM(size), 0) AS total_size FROM attachments").fetchone()
        total_attachments = row["total"]
        total_size = row["total_size"]

        emails_with = self.conn.execute("SELECT COUNT(DISTINCT email_uid) AS cnt FROM attachments").fetchone()["cnt"]

        # Extension distribution — compute in Python for correct last-dot handling
        all_att_rows = self.conn.execute("SELECT name, COALESCE(size, 0) AS size FROM attachments").fetchall()
        ext_agg: dict[str, dict] = {}
        for r in all_att_rows:
            name = r["name"] or ""
            dot_pos = name.rfind(".")
            ext = name[dot_pos:].lower() if dot_pos > 0 else ""
            if ext not in ext_agg:
                ext_agg[ext] = {"count": 0, "total_size": 0}
            ext_agg[ext]["count"] += 1
            ext_agg[ext]["total_size"] += r["size"]
        by_extension = sorted(
            [{"extension": ext, "count": v["count"], "total_size": v["total_size"]} for ext, v in ext_agg.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:30]

        # Top filenames
        top_rows = self.conn.execute(
            "SELECT name, COUNT(*) AS cnt FROM attachments GROUP BY name ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
        top_filenames = [{"name": r["name"], "count": r["cnt"]} for r in top_rows]

        return {
            "total_attachments": total_attachments,
            "total_size_bytes": total_size,
            "emails_with_attachments": emails_with,
            "by_extension": by_extension,
            "top_filenames": top_filenames,
        }

    def list_attachments(
        self,
        *,
        filename: str | None = None,
        extension: str | None = None,
        mime_type: str | None = None,
        sender: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Browse attachments with optional filters. Joins with emails table."""
        from_managere = " FROM attachments a JOIN emails e ON a.email_uid = e.uid"
        conditions, params = _attachment_filter_conditions(filename, extension, mime_type)
        if sender:
            conditions.append("(e.sender_email LIKE ? ESCAPE '\\' OR e.sender_name LIKE ? ESCAPE '\\')")
            params.extend([f"%{_escape_like(sender)}%", f"%{_escape_like(sender)}%"])
        where_managere = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        # Get total count
        total = self.conn.execute("SELECT COUNT(*) AS cnt" + from_managere + where_managere, params).fetchone()["cnt"]

        rows = self.conn.execute(
            "SELECT a.name, a.mime_type, a.size, a.is_inline,"
            " a.email_uid, e.subject, e.sender_email, e.date"
            + from_managere
            + where_managere
            + " ORDER BY e.date DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return {
            "attachments": [dict(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def search_emails_by_attachment(
        self,
        *,
        filename: str | None = None,
        extension: str | None = None,
        mime_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Find emails with matching attachments. Returns email rows + matching_attachments."""
        query = (
            "SELECT e.uid, e.subject, e.sender_email, e.sender_name, e.date, e.folder,"
            " GROUP_CONCAT(a.name, ', ') AS matching_attachments,"
            " COUNT(a.id) AS match_count"
            " FROM emails e JOIN attachments a ON e.uid = a.email_uid"
        )
        conditions, params = _attachment_filter_conditions(filename, extension, mime_type)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " GROUP BY e.uid ORDER BY e.date DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
