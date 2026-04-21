"""
Chunk emails for embedding.

Strategy:
- Quoted text in replies/forwards is stripped to avoid double-indexing.
- Short emails (< MAX_CHUNK_CHARS): single chunk with full metadata header.
- Long emails: split into overlapping chunks. Only chunk 0 gets the full header;
  continuation chunks get a minimal "[Subject - Part N/M]" reference.
- Each chunk's embedding text captures WHO/WHEN/WHAT context for retrieval quality.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .attachment_identity import attachment_chunk_token
from .formatting import build_email_header


@dataclass
class EmailChunk:
    """A single chunk ready for embedding."""

    uid: str  # Parent email UID
    chunk_id: str  # uid__chunk_N
    text: str  # The text to embed
    metadata: dict  # Stored alongside the vector in ChromaDB
    embedding: list[float] | None = None  # Pre-computed embedding (e.g. image)


# Tuning parameters
# NOTE: CJK characters have ~2-3x higher token density than Latin text.
# A 1500-char CJK chunk may exceed typical embedding model token limits.
# For CJK-heavy corpora, consider lowering MAX_CHUNK_CHARS to ~600-800.
MAX_CHUNK_CHARS = 1500
OVERLAP_CHARS = 200

# Quoted-content separators (multilingual)
_QUOTED_SEPARATORS = [
    # English
    re.compile(r"^-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Forwarded message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # German
    re.compile(r"^-{3,}\s*Urspr[uü]ngliche Nachricht\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Weitergeleitete Nachricht\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # French
    re.compile(r"^-{3,}\s*Message d'origine\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Message transf[ée]r[ée]\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Spanish
    re.compile(r"^-{3,}\s*Mensaje original\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Mensaje reenviado\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Dutch
    re.compile(r"^-{3,}\s*Oorspronkelijk bericht\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Doorgestuurd bericht\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Italian
    re.compile(r"^-{3,}\s*Messaggio originale\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Messaggio inoltrato\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Portuguese
    re.compile(r"^-{3,}\s*Mensagem original\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Mensagem encaminhada\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Swedish
    re.compile(r"^-{3,}\s*Ursprungligt meddelande\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Vidarebefordrat meddelande\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Danish
    re.compile(r"^-{3,}\s*Oprindelig meddelelse\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Videresendt meddelelse\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    # Polish
    re.compile(r"^-{3,}\s*Oryginalna wiadomo[śs][ćc]\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Przekazana wiadomo[śs][ćc]\s*-{3,}", re.IGNORECASE | re.MULTILINE),
]

# "On ... wrote:" / multilingual equivalents
_WROTE_PATTERN = re.compile(
    r"^(On .+ wrote"  # English
    r"|Am .+ schrieb[^:]*"  # German
    r"|Le .+ a [ée]crit"  # French
    r"|El .+ escribi[óo]"  # Spanish
    r"|Op .+ schreef[^:]*"  # Dutch
    r"|Il .+ ha scritto"  # Italian
    r"|Em .+ escreveu"  # Portuguese
    r"|Den .+ skrev"  # Swedish / Danish
    r"|W dniu .+ napisa[łl]"  # Polish
    r")\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# Signature markers
_SIGNATURE_SEPARATOR = re.compile(r"^-- ?\s*$", re.MULTILINE)  # RFC standard: "-- " or "--"
_SENT_FROM = re.compile(
    r"^Sent from my (iPhone|iPad|Samsung|Outlook|Galaxy|Pixel|Android|Huawei|BlackBerry)\b",
    re.IGNORECASE | re.MULTILINE,
)
_GET_OUTLOOK = re.compile(r"^Get Outlook for (iOS|Android)\b", re.IGNORECASE | re.MULTILINE)
_CLOSING_PHRASES = re.compile(
    r"^(Best regards|Kind regards|Regards|Mit freundlichen Gr[uü][ßs]en|"
    r"Cheers|Thanks|Thank you|Viele Gr[uü][ßs]e|Liebe Gr[uü][ßs]e|Sincerely|"
    r"Best wishes|Warm regards|"
    r"Cordialement|Atentamente|Cordiali saluti|Atenciosamente|"
    r"Med v[aä]nliga h[aä]lsningar|Med venlig hilsen|Z powa[żz]aniem),?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_signature(body: str) -> tuple[str, bool]:
    """Detect and strip email signature from body text.

    Args:
        body: The email body text.

    Returns:
        (body_without_signature, had_signature)
    """
    if not body:
        return body, False

    # Try "-- " / "--" separator (RFC standard)
    match = _SIGNATURE_SEPARATOR.search(body)
    if match:
        before = body[: match.start()].rstrip()
        after = body[match.end() :]
        # Only strip if remaining content after separator is short (< 15 lines)
        if before and after.strip().count("\n") < 15:
            return before, True

    # Try "Sent from my ..."
    match = _SENT_FROM.search(body)
    if match:
        before = body[: match.start()].rstrip()
        if before:
            return before, True

    # Try exact Outlook mobile footer
    match = _GET_OUTLOOK.search(body)
    if match:
        before = body[: match.start()].rstrip()
        if before:
            return before, True

    # Try closing phrase followed by name (short tail: <= 8 lines after phrase)
    match = _CLOSING_PHRASES.search(body)
    if match:
        remaining = body[match.end() :]
        remaining_lines = [ln for ln in remaining.splitlines() if ln.strip()]
        if len(remaining_lines) <= 8:
            before = body[: match.start()].rstrip()
            if before:
                return before, True

    return body, False


def strip_quoted_content(body: str, email_type: str = "original") -> tuple[str, int]:
    """Strip quoted content from reply/forward bodies.

    Args:
        body: The email body text.
        email_type: One of "reply", "forward", "original".

    Returns:
        (original_content, quoted_line_count) — the original part and how many
        lines of quoted text were stripped.
    """
    if not body or email_type == "original":
        return body, 0

    # Try separator patterns first (most reliable)
    for pattern in _QUOTED_SEPARATORS:
        match = pattern.search(body)
        if match:
            original = body[: match.start()].rstrip()
            quoted_lines = body[match.start() :].count("\n") + 1
            if original:
                return original, quoted_lines

    # Try "On ... wrote:" / "Am ... schrieb:" pattern
    match = _WROTE_PATTERN.search(body)
    if match:
        original = body[: match.start()].rstrip()
        quoted_lines = body[match.start() :].count("\n") + 1
        if original:
            return original, quoted_lines

    # Try trailing ">" quoted blocks (only if they make up the tail)
    lines = body.split("\n")
    last_non_quoted = len(lines) - 1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() and not lines[i].lstrip().startswith(">"):
            last_non_quoted = i
            break

    tail_lines = lines[last_non_quoted + 1 :]
    quoted_count = sum(1 for line in tail_lines if line.strip())
    tail_start = len(lines) - quoted_count
    tail_has_separator = tail_start > 0 and not lines[tail_start - 1].strip()
    if quoted_count >= 3 or (quoted_count >= 1 and tail_has_separator):
        original = "\n".join(lines[: last_non_quoted + 1]).rstrip()
        if original:
            return original, quoted_count

    return body, 0


def chunk_email(email_dict: dict) -> list[EmailChunk]:
    """
    Convert a parsed email dict into one or more chunks for embedding.

    Args:
        email_dict: Output of Email.to_dict()

    Returns:
        List of EmailChunk objects ready for embedding.
    """
    uid = email_dict["uid"]
    body = email_dict.get("body") or ""
    email_type = email_dict.get("email_type", "original")
    header = build_email_header(email_dict)
    subject = email_dict.get("subject", "")
    sender_name = email_dict.get("sender_name", "")
    sender_email = email_dict.get("sender_email", "")
    date = email_dict.get("date", "")

    # Strip quoted content from replies/forwards
    body, quoted_lines = strip_quoted_content(body, email_type)
    quoted_note = f"\n[Quoted: ~{quoted_lines} lines omitted]" if quoted_lines > 0 else ""

    # Strip signature
    body, had_signature = strip_signature(body)
    sig_note = "\n[Signature stripped]" if had_signature else ""

    # Pre-compute joined strings once for metadata
    to_str = ", ".join(email_dict.get("to", []))
    cc_str = ", ".join(email_dict.get("cc", []))
    bcc_str = ", ".join(email_dict.get("bcc", []))
    att_names = email_dict.get("attachment_names", [])
    att_names_str = ", ".join(att_names)
    body_surface_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()

    # Metadata stored in ChromaDB (not embedded, but returned with results)
    base_metadata = {
        "uid": uid,
        "message_id": email_dict.get("message_id", ""),
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to": to_str,
        "cc": cc_str,
        "date": date,
        "folder": email_dict.get("folder", ""),
        "has_attachments": str(email_dict.get("has_attachments", False)),
        "conversation_id": email_dict.get("conversation_id", ""),
        "in_reply_to": email_dict.get("in_reply_to", ""),
        "email_type": email_type,
        "base_subject": email_dict.get("base_subject", ""),
        "priority": str(email_dict.get("priority", 0)),
        "bcc": bcc_str,
        "attachment_names": att_names_str,
        "attachment_count": str(len(att_names)),
        "has_signature": str(had_signature),
        "categories": ", ".join(email_dict.get("categories", []) or []),
        "is_calendar_message": str(email_dict.get("is_calendar_message", False)),
        "thread_topic": email_dict.get("thread_topic", "") or "",
        "inference_classification": email_dict.get("inference_classification", "") or "",
        "source_scope": "email_body",
        "surface_hash": body_surface_hash,
    }

    if len(body) <= MAX_CHUNK_CHARS:
        text = f"{header}\n\n{body}{quoted_note}{sig_note}" if body else header
        return [
            EmailChunk(
                uid=uid,
                chunk_id=f"{uid}__0",
                text=text,
                metadata={
                    **base_metadata,
                    "chunk_index": "0",
                    "total_chunks": "1",
                    "segment_ordinal": "0",
                    "char_start": 0,
                    "char_end": len(body),
                },
            )
        ]

    # Clamp to avoid negative/zero max_len when headers are unusually long
    max_body_len = max(OVERLAP_CHARS + 100, MAX_CHUNK_CHARS - len(header) - 50)
    body_segments_with_offsets = _split_text_with_offsets(body, max_body_len, OVERLAP_CHARS)
    body_segments = [segment for segment, _start, _end in body_segments_with_offsets]

    chunks: list[EmailChunk] = []
    for i, (segment, start_offset, end_offset) in enumerate(body_segments_with_offsets):
        if i == 0:
            # First chunk gets full header + extra metadata lines
            text = f"{header}\n\n[Part 1/{len(body_segments)}]\n{segment}"
        else:
            # Continuation chunks get context header for embedding quality
            context_parts = []
            if sender_name and sender_email:
                context_parts.append(f"From: {sender_name} <{sender_email}>")
            elif sender_email:
                context_parts.append(f"From: {sender_email}")
            if date:
                context_parts.append(f"Date: {date}")
            if subject:
                context_parts.append(f"Subject: {subject}")
            context_header = f"[{' | '.join(context_parts)}]\n" if context_parts else ""
            text = f"{context_header}[{subject} - Part {i + 1}/{len(body_segments)}]\n{segment}"

        # Append notes to last chunk only
        if i == len(body_segments) - 1:
            text += quoted_note + sig_note

        chunks.append(
            EmailChunk(
                uid=uid,
                chunk_id=f"{uid}__{i}",
                text=text,
                metadata={
                    **base_metadata,
                    "chunk_index": str(i),
                    "total_chunks": str(len(body_segments)),
                    "segment_ordinal": str(i),
                    "char_start": start_offset,
                    "char_end": end_offset,
                },
            )
        )

    return chunks


def _split_text(text: str, max_len: int, overlap: int) -> list[str]:
    """Split text into overlapping segments, preferring to break at paragraph/sentence boundaries."""
    return [segment for segment, _start, _end in _split_text_with_offsets(text, max_len, overlap)]


def _split_text_with_offsets(text: str, max_len: int, overlap: int) -> list[tuple[str, int, int]]:
    """Split text into overlapping segments and return ``(segment, start, end)``."""
    if not text:
        return [(text, 0, len(text))] if text is not None else []
    if max_len <= 0:
        return [(text, 0, len(text))]
    if len(text) <= max_len:
        return [(text, 0, len(text))]

    segments: list[tuple[str, int, int]] = []
    start = 0

    while start < len(text):
        end = start + max_len

        if end >= len(text):
            segment = text[start:]
            if segment.strip():
                segments.append((segment, start, len(text)))
            break

        # Try to break at paragraph boundary
        break_point = text.rfind("\n\n", start + max_len // 2, end)
        if break_point == -1:
            # Try sentence boundary
            break_point = text.rfind(". ", start + max_len // 2, end)
            if break_point != -1:
                break_point += 1  # Include the period
        if break_point == -1:
            # Try any newline
            break_point = text.rfind("\n", start + max_len // 2, end)
        if break_point == -1:
            # Hard break at max_len
            break_point = end

        # Guarantee forward progress even when boundary lands close to the overlap window.
        if break_point <= start:
            break_point = end

        segment = text[start:break_point]
        if segment.strip():  # Skip empty or whitespace-only segments
            segments.append((segment, start, break_point))
        start = max(start + 1, break_point - overlap)

    # Ensure at least one segment is returned
    return segments if segments else [(text, 0, len(text))]


def chunk_attachment(
    email_uid: str,
    filename: str,
    text: str,
    parent_metadata: dict,
    att_index: int = 0,
    attachment_id: str = "",
    content_sha256: str = "",
    normalized_text: str = "",
    extraction_state: str = "text_extracted",
    evidence_strength: str = "strong_text",
    ocr_used: bool = False,
    failure_reason: str | None = None,
    surface_id: str = "",
    surface_kind: str = "",
    surface_origin_kind: str = "",
    surface_locator: dict[str, object] | None = None,
    surface_ocr_confidence: float = 0.0,
) -> list[EmailChunk]:
    """Chunk extracted attachment text for embedding.

    Args:
        email_uid: The parent email's UID.
        filename: The attachment filename.
        text: Extracted text content from the attachment.
        parent_metadata: Metadata from the parent email (subject, date, sender, etc.).
        att_index: Attachment index within the parent email (disambiguates same-name files).
        extraction_state: Normalized extraction outcome for the attachment text.
        evidence_strength: Answer-facing evidence quality label for the attachment text.
        ocr_used: Whether OCR was used to recover the attachment text.
        failure_reason: Optional extraction failure reason for weak attachment references.
        surface_id: Stable attachment-surface identifier propagated into chunk metadata.
        surface_kind: Surface role for retrieval/audit (e.g. verbatim, normalized_retrieval).
        surface_origin_kind: Surface origin label (native, ocr, normalized, reference).
        surface_locator: Structured locator payload associated with the surface.
        surface_ocr_confidence: OCR confidence propagated from the selected surface.

    Returns:
        List of EmailChunk objects for the attachment content.
    """
    if not text or not text.strip():
        return []

    def _normalize_metadata_value(value: object) -> str | int | float | bool:
        if isinstance(value, (str, int, float, bool)):
            return value
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            if all(isinstance(item, (str, int, float, bool)) or item is None for item in items):
                return ", ".join(str(item) for item in items if str(item).strip())
            return json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    subject = parent_metadata.get("subject", "")
    date = parent_metadata.get("date", "")
    filename_hash = attachment_chunk_token(attachment_id=attachment_id, filename=filename, att_index=att_index)
    header = f'[Attachment: {filename} from email "{subject}" ({date})]'
    normalized_parent_metadata = {str(key): _normalize_metadata_value(value) for key, value in parent_metadata.items()}
    source_text = str(text)
    normalized_sidecar = str(normalized_text or "").strip()
    index_text = source_text
    if normalized_sidecar and normalized_sidecar != source_text:
        index_text = f"{source_text}\n\n[Normalized OCR search text]\n{normalized_sidecar}"
    source_surface_hash = hashlib.sha256(source_text.encode("utf-8", errors="ignore")).hexdigest()

    base_metadata = {
        **normalized_parent_metadata,
        "candidate_kind": "attachment",
        "chunk_type": "attachment",
        "is_attachment": "True",
        "parent_uid": email_uid,
        "attachment_name": filename,
        "attachment_filename": filename,
        "attachment_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        "attachment_id": attachment_id,
        "content_sha256": content_sha256,
        "extraction_state": extraction_state,
        "evidence_strength": evidence_strength,
        "ocr_used": str(ocr_used),
        "failure_reason": failure_reason or "",
        "source_scope": "attachment_text",
        "surface_hash": source_surface_hash,
        "locator_version": "2",
        "surface_id": surface_id,
        "surface_kind": surface_kind,
        "origin_kind": surface_origin_kind,
        "surface_locator_json": json.dumps(surface_locator or {}, ensure_ascii=False, sort_keys=True),
        "surface_ocr_confidence": str(float(surface_ocr_confidence or 0.0)),
    }

    if len(index_text) <= MAX_CHUNK_CHARS:
        chunk_id = f"{email_uid}__att_{filename_hash}__0"
        return [
            EmailChunk(
                uid=email_uid,
                chunk_id=chunk_id,
                text=f"{header}\n\n{index_text}",
                metadata={
                    **base_metadata,
                    "chunk_index": "0",
                    "total_chunks": "1",
                    "segment_ordinal": str(att_index),
                    "char_start": 0,
                    "char_end": len(source_text),
                },
            )
        ]

    max_body_len = max(OVERLAP_CHARS + 100, MAX_CHUNK_CHARS - len(header) - 50)
    segments_with_offsets = _split_text_with_offsets(index_text, max_body_len, OVERLAP_CHARS)

    chunks: list[EmailChunk] = []
    for i, (segment, start_offset, end_offset) in enumerate(segments_with_offsets):
        chunk_id = f"{email_uid}__att_{filename_hash}__{i}"
        if i == 0:
            chunk_text = f"{header}\n\n[Part 1/{len(segments_with_offsets)}]\n{segment}"
        else:
            chunk_text = f"[{filename} - Part {i + 1}/{len(segments_with_offsets)}]\n{segment}"

        verbatim_start = min(start_offset, len(source_text))
        verbatim_end = min(end_offset, len(source_text))
        chunks.append(
            EmailChunk(
                uid=email_uid,
                chunk_id=chunk_id,
                text=chunk_text,
                metadata={
                    **base_metadata,
                    "chunk_index": str(i),
                    "total_chunks": str(len(segments_with_offsets)),
                    "segment_ordinal": str(att_index),
                    "char_start": verbatim_start,
                    "char_end": verbatim_end,
                },
            )
        )

    return chunks
